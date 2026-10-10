# 功能、源码与证据对应表

核对日 2026-10-10；应用提交 `60f72860f1968d3ce714d728eead90bac7dc2a3a`。以下记录是工程或有限序列证据，未转换为真人试用成绩。

| 功能 | 主要实现 | 已有证据 | 使用边界 / 待补 |
| --- | --- | --- | --- |
| 视频上传与抽帧 | src/clickvos/video_io.py | DEV-25、DEV-37；tests/test_video_io.py | 两入口限制不同；VFR 预览不保留逐帧时间戳 |
| 目标类别、ID 和正负点 | src/clickvos/web_app.py；sam2_engine.py | DEV-32、DEV-36 | 操作者创建 ID；不自动识别所有交通目标 |
| 多对象传播 | src/clickvos/sam2_engine.py | DEV-26 crossing 三对象；DEV-31 双骑行者 | 有限序列，不能代表全数据集精度 |
| 首帧补点、预览、撤销 | src/clickvos/first_frame_review.py；web_app.py | DEV-29、DEV-30、DEV-32 | 需初次传播；负点可能降低细结构质量 |
| 中间帧修正 | src/clickvos/sam2_engine.py；web_app.py | DEV-32、DEV-36、DEV-37 | 从修正帧向后更新；不恢复已关闭的内存会话 |
| 异常与重新激活复核 | src/clickvos/anomaly.py；web_app.py | CP-02、DEV-22、DEV-28 | 真实消失后同一目标重现正例仍不足 |
| 标注 ZIP 导出 | src/clickvos/export.py | DEV-32、DEV-36、DEV-37；scripts/verify_downloaded_bundle.py | 实际下载需核验；文件一致不等于语义正确 |
| 历史任务与回收恢复 | src/clickvos/task_store.py；web_app.py | DEV-12、DEV-14、DEV-19、DEV-24 | 原 Gradio；只读打开，无编辑会话恢复和永久清理 |
| 统一网站与访问控制 | src/clickvos/site_api.py；web/site/ | DEV-36、DEV-37；tests/test_site_api.py | 本机 GPU、临时 HTTPS、单操作者；手机完整流程未验收 |
| 长视频资源控制 | src/clickvos/lazy_frames.py；site_api.py | DEV-37；tests/test_long_video.py | 30 秒有资源条件；工程容量不等于持续跟踪精度 |
| 容器部署准备 | Dockerfile；compose.yaml；scripts/verify_deployment.py | DEV-13；DEV-38 静态核对 | 仅 Gradio 容器入口；尚未实际构建或云端验收 |
| 十人试用材料 | docs/trials/；scripts/prepare_user_trial.py | DEV-33 与本机试用包 | 材料、待测编号不算真实参加人数；统计待原始记录 |

## 可用的报告表述

可写“已完成本机短视频交互分割、首帧与中间帧修正及标注包导出闭环，并保留浏览器和文件一致性验证记录”。可以按对应序列引用已记录的指标，明确数据范围与失败门槛。

目前不能写“已完成十人试用”“云平台已稳定部署”“30 秒任意交通视频均稳定”“遮挡重现问题已解决”或“完成完整 DAVIS/城市非机动车基准”。后续达到条件再补真实证据，不提前填入结论。
