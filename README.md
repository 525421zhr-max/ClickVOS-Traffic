# ClickVOS

基于点击交互的 SAM2 视频对象分割原型工具。

## 当前重建目标

先恢复一条可复现的最小流程：`MP4 上传 → 首帧正/负点 → SAM2 传播 → 绿色掩码视频导出`。

项目事实、里程碑和已验证结果只记录在 `docs/checkpoints/`；不要以旧申报书中的预期数字替代实际测试数据。

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

## 重建顺序

1. 记录硬件、系统、Python、CUDA 与 PyTorch 环境。
2. 验证 SAM2 单帧点击分割。
3. 验证 SAM2 视频传播与掩码保存。
4. 接入 Gradio 上传、点击及导出流程。
5. 增加后处理、日志、性能测量与用户试用记录。

详见 [checkpoint 规则](docs/checkpoints/README.md)。
