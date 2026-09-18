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

## 推理、异常检查与预览导出

单目标传播脚本已经调用可复用的 `Sam2Engine`。一次运行结束后可生成异常报告和 MP4：

```bash
python scripts/run_sam2_video.py --video sample.mp4 --checkpoint /path/model.pt \
  --output outputs/tasks/demo --positive 520,370 --category vehicle
python -m clickvos.anomaly outputs/tasks/demo/result.json \
  --output outputs/tasks/demo/anomalies.json
python -m clickvos.export outputs/tasks/demo/overlays \
  outputs/tasks/demo/preview.mp4 --fps 10
```

异常规则目前只把“目标连续消失后重新激活”标为待复核，不能替代用户确认或身份识别证据。

Web 默认启用“重新激活保护”：目标连续消失 3 帧后，后续突然出现的候选掩码不会直接进入最终结果，而是暂停并保存到任务目录的 `review_candidates/` 供用户核查。该规则已在 CP-02 第 46 帧错误重识别案例上完成真实 GPU 回归；它是保守的人工复核机制，不是身份识别模型。

传播结束后，“待复核异常帧”会列出对象、帧号和异常类型，可直接定位到修正区域。对于被保护层暂停的重新激活候选，用户可以选择继续负点修正，也可以在确认确为同一目标后点击“确认候选目标重新出现”。多对象掩码重叠达到 10 像素时也会进入待复核列表。

如果候选确认错误，可在保持当前目标和帧不变时点击“撤销本次候选确认”。系统会重新拦截对应候选、恢复待复核异常并保留确认与撤销的审计记录。

## 本地 Web 界面

```bash
python -m pip install -r requirements-app.txt
export CLICKVOS_CHECKPOINT=/absolute/path/to/sam2.1_hiera_tiny.pt
python -m clickvos.web_app
```

浏览器访问 `http://127.0.0.1:7860`，可上传视频、抽帧、新建多个目标并分别添加正负点，然后一次传播全部目标。每个对象使用独立颜色、类别、对象 ID、掩码目录和异常统计；合成 MP4 同时显示全部目标。中间帧修正会作用于“当前目标”，其他对象继续保留在同一 SAM2 会话中。

页面按“准备视频 → 标记目标 → 运行传播 → 复核修正 → 导出标注”组织；传播高级设置和完整 JSON 报告默认折叠，当前状态始终显示在流程顶部。

多目标操作顺序：选择类别并点击“新建目标” → 选择当前目标 → 添加正负点 → 为其他目标重复上述操作 → 运行传播。每个目标必须至少包含一个正点，最多支持 20 个目标。

若掩码覆盖了另一个不相连目标，可启用“只保留最大连通区域”。该选项不会解决相连区域的边界错误或身份漂移；此时应在错误目标内部增加负点，或在后续帧重新修正。叠加预览使用黄色边界显示实际二值掩码边缘，便于区分“显示透明造成的模糊”和“掩码本身不准”。

传播完成后可在“中间帧修正”区域输入帧号、载入对应画面并添加正负点。应用后，系统保留当前 SAM2 会话并从该帧重新传播到结尾，同时更新预览、异常报告和 `result.json`。当前版本限制为本地单用户、单活动任务；启动新传播会释放上一个会话以控制显存。

传播完成后点击“生成标注下载包”，页面会提供 ZIP 下载。压缩包包含逐对象 PNG 掩码、合成预览视频、ClickVOS 项目 JSON 和 COCO uncompressed RLE JSON；不包含原视频、抽帧图片或本机绝对路径。也可以从命令行导出已有任务：

```bash
python -m clickvos.export bundle outputs/tasks/<task-id>
```

格式细节见 [标注导出格式](docs/operations/export-format.md)。

## GitHub 备份与证据

仓库只备份源码、配置、测试、文档和经过检查点确认的实验摘要。模型权重、原始或处理后视频、逐帧掩码、预览视频、运行日志、密钥和私人素材一律留在本地并由 `.gitignore` 拦截。

仓库当前公开用于项目展示和过程留痕，但尚未附加开源许可证；公开可见不表示授予复制、修改或再发布许可。后续会结合软件著作权安排再决定许可方式。

- [GitHub 备份规则](docs/operations/github-backup.md)
- [CP-02 基线摘要](docs/research/results/cp02-baseline.json)
- [W05 掩码质量小试验摘要](docs/research/results/w05-mask-quality-pilot.json)
- [W06 中间帧修正摘要](docs/research/results/w06-midframe-correction.json)
- [W07 重新激活保护摘要](docs/research/results/w07-reactivation-guard.json)
- [W08 Web 多目标分割摘要](docs/research/results/w08-web-multi-object.json)
- [W09 标注导出摘要](docs/research/results/w09-annotation-export.json)
- [W10 异常定位与候选确认摘要](docs/research/results/w10-anomaly-review.json)
- [DEV-11 界面流程与确认撤销摘要](docs/research/results/dev11-interface-and-review-undo.json)

每次推送都会运行轻量仓库检查：解析配置与实验 JSON、检查必需文档、阻止视频或模型权重进入版本控制，并对 Python 源码执行语法编译。完整 GPU/SAM2 回归仍需在项目的 WSL 环境中运行。
