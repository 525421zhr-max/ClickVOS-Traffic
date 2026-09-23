# DEV-24：抽帧失败任务保留与回收闭环

- 日期：2026-09-23
- 状态：工程实现与自动化测试通过；未进行真实损坏视频的端到端 FFmpeg 测试

## 完成内容

`prepare_task` 现在在新建任务后先写 `preparing` 状态，再调用 FFmpeg 抽帧。成功后改为 `frames_extracted` 并记录实际帧数；异常时改为 `frame_extraction_failed`，保存错误代码、面向用户的错误信息和已生成 JPEG 数量。任务信息使用临时 JSON 文件后替换，避免正常写入过程留下半份记录。已生成的帧不会自动删除。

历史任务列表会标出“抽帧失败”或“抽帧未完成”。打开失败任务能看到原因和可恢复清理提示；用户仍需预览占用、输入完整任务编号，才能将其移入回收区。回收区支持恢复，未加入自动永久删除。

## 可复现命令与实际结果

环境：WSL Ubuntu 24.04、Python 3.12.3、PyTorch 2.11.0+cu128。此次没有运行 SAM2 或 GPU 推理。

```bash
cd /mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS
/home/clickvos/.venvs/clickvos/bin/python -m pytest \
  tests/test_video_io.py tests/test_task_store.py tests/test_web_app.py -q
/home/clickvos/.venvs/clickvos/bin/python -m pytest -q
/home/clickvos/.venvs/clickvos/bin/python scripts/check_repository.py
```

- 定向测试：35 项通过，6.75 秒。
- 全项目测试：62 项通过，6.71 秒。
- 仓库检查：16 份结果摘要、114 个已跟踪文件，无已跟踪模型或视频文件。
- 工程夹具模拟“已生成 1 张 JPEG 后抽帧失败”，核对失败记录、错误信息、帧文件保留、历史列表和可恢复归档；成功路径也核对状态转换。这些不是视频分割实验数据。

## 已知限制

- 系统进程被强制终止时，只能保留最后成功写入的 `preparing` 状态，不会自动判断是否可以续传；用户可将其归档后重新建任务。
- 本轮未用真实损坏视频触发 FFmpeg，也未验证停电或磁盘写满情形。元数据首次写入本身失败时，目录可能仍无有效记录，现有历史列表会跳过该目录。
- 保留的是错误代码和用户提示，不把底层异常详情或完整 FFmpeg 输出写入任务记录。
