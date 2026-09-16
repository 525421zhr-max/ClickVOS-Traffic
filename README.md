# ClickVOS Traffic

基于 SAM2 的交通视频交互式目标分割与半自动标注平台。

项目面向交通视频研究、计算机视觉实验和数据标注场景。用户通过少量正点、负点或框提示选择车辆、行人和非机动车，系统传播逐帧实例掩码，并允许在疑似漂移帧上继续修正和导出标注。

## 当前重建目标

先恢复一条可复现的交通视频标注流程：`MP4 上传 → 目标类别与提示 → SAM2 传播 → 疑似失败帧检查与修正 → 掩码、预览视频和标注导出`。

项目事实、里程碑和已验证结果只记录在 `docs/checkpoints/`；不要以旧申报书中的预期数字替代实际测试数据。

## 测试数据边界

- 禁止使用 `ClickVOS/` 目录之外的个人照片、人像或私人素材进行模型验证，也禁止据此生成视频、掩码、预览或实验记录。
- 只使用用户明确授权的测试素材、许可证清晰的公开数据，或不含真实人物的纯合成样例。
- 新增测试数据时，在 checkpoint 中记录来源、授权或许可证；来源不清晰时不得使用。
- 工程回归可以使用不含真实人物的纯合成视频；交通场景效果结论必须来自许可证清晰的公开数据或明确授权素材。

## 目录约定

- `src/`：应用与算法源码。
- `configs/`：不含密钥的运行配置。
- `tests/`：自动化测试。
- `scripts/`：环境检查、数据处理与实验脚本。
- `docs/checkpoints/`：阶段快照与恢复说明。
- `docs/research/`：实验设计、指标及失败案例。
- `docs/operations/`：安装、运行、演示与发布说明。
- `data/`：本地测试数据；不提交原始视频或受限数据。
- `models/`：模型权重；不提交。
- `outputs/`、`logs/`：运行产物；不提交。

## 当前范围

- 第一阶段目标类别：车辆、行人和非机动车。
- 核心产品价值：降低交通视频逐帧像素级标注成本。
- 核心研究问题：提示策略、传播失败检测、中间帧修正、性能与显存权衡。
- 部署路线：先完成本地单用户版本，再容器化并适配云 GPU。
- 结题底线：可运行软件、软件著作权、实验与十人用户试用、完整结题材料。

不在当前主线内：交通事故预测、自动驾驶决策、车流量业务分析、从零训练基础模型、未经实测的精度承诺。

## 重建顺序

1. 记录硬件、系统、Python、CUDA 与 PyTorch 环境。
2. 验证 SAM2 单帧点击分割。
3. 使用合规交通视频验证传播、修正和掩码保存。
4. 接入 Gradio 上传、点击、目标类别和导出流程。
5. 增加疑似失败帧检测、日志和性能测量。
6. 建立公开数据评估与十人用户试用。
7. 完成容器化、云端部署验证和软件著作权材料。

详见 [项目章程](docs/project-charter.md)、[路线图](docs/roadmap.md)和 [checkpoint 规则](docs/checkpoints/README.md)。

## 视频输入工具

在 WSL 环境中安装项目开发版本后，可统一检查视频并创建任务目录：

```bash
python -m pip install -e . pytest
python -m clickvos.video_io inspect data/processed/cp02/traffic-sample.mp4
python -m clickvos.video_io prepare data/processed/cp02/traffic-sample.mp4 \
  --tasks-root outputs/tasks --task-id cp02-regression
pytest
```

`prepare` 会创建独立的 `frames/`、`masks/`、`overlays/` 和 `exports/` 目录，并把视频元数据写入 `task.json`。为避免混合不同运行结果，已有非空抽帧目录不会被覆盖。

默认限制、SAM2 路径与三类交通对象定义集中在 `configs/default.json`。命令行可通过全局参数 `--config` 指定其他配置，例如：

```bash
python -m clickvos.video_io --config configs/default.json inspect sample.mp4
```

界面与命令行使用稳定错误代码；终端用户看到中文提示，日志可保留不含隐私的技术细节。
