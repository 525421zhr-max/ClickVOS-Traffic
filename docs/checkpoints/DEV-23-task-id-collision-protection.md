# DEV-23：任务编号冲突保护

- 日期：2026-09-23
- 状态：工程实现与自动化测试通过

## 解决的问题

此前 `create_task_layout` 在指定任务编号已存在时仍会复用目录。虽然后续抽帧检测到已有 JPEG 会阻止覆盖，但旧目录若为空或只含其他任务文件，仍可能被混入新任务。现在任务根目录通过一次独占创建建立；只要同名路径已存在，就返回 `TASK_CONFLICT`，不修改原目录。Web 会将其显示为“任务编号已存在，请使用新的任务编号。”

此改动仅影响**新建任务**，不更改现有任务、回收区及 SAM2 推理结果。KITTI 不参与本次验证。

## 可复现命令与实际结果

环境：WSL Ubuntu 24.04，Python 3.12.3，PyTorch 2.11.0+cu128。此次测试没有运行 GPU 推理。

```bash
cd /mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS
/home/clickvos/.venvs/clickvos/bin/python -m pytest tests/test_video_io.py -q
/home/clickvos/.venvs/clickvos/bin/python -m pytest -q
/home/clickvos/.venvs/clickvos/bin/python scripts/check_repository.py
```

- 视频输入测试：6 项通过。
- 全项目测试：58 项通过，6.46 秒。
- 新增回归覆盖已有任务带 `task.json` 和空目录两种冲突；第一种场景核对旧文件内容不变。
- 仓库检查通过：16 份结果摘要、113 个已跟踪文件；没有已跟踪模型或视频文件。没有上传视频、权重或私人照片。

## 限制与下一步

测试验证的是目录冲突保护，不是并发多用户任务队列或完整的上传中断恢复。`prepare_task` 在 FFmpeg 抽帧异常后可能留下不完整的新任务目录；当前历史任务读取会跳过损坏目录，但后续仍应提供明确的失败清理或恢复策略。不要据此宣称任务事务性已经完整实现。
