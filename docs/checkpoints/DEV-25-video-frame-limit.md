# DEV-25：视频帧数上限与真实 FFmpeg 检查

- 日期：2026-09-23
- 状态：工程实现、自动化测试和一次真实 FFmpeg 越界检查通过；未运行 SAM2 推理

## 完成内容

配置新增 `video.max_frames`，当前默认 300。`prepare_task` 若从 `ffprobe` 获得超过上限的帧数，会在建任务前拒绝；若帧数未知或元数据不准确，FFmpeg 最多输出上限加 1 帧，并在发现哨兵帧时返回 `VIDEO_TOO_MANY_FRAMES`。既有 DEV-24 失败任务记录会保存这一错误及实际输出帧数，不会默默截断视频并当成完整任务。命令行单目标脚本也改为使用同一配置。

## 可复现命令与实际结果

环境：WSL Ubuntu 24.04，Python 3.12.3，PyTorch 2.11.0+cu128；真实检查只使用 FFmpeg/ffprobe，不加载 SAM2。素材为已登记的授权行人视频 `data/raw/traffic-002-pedestrian.webm`，原文件不提交 Git。该文件的 `ffprobe` 输出为 `avg_frame_rate=30000/1001`、`nb_frames=N/A`。

```bash
cd /mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS
/home/clickvos/.venvs/clickvos/bin/python scripts/verify_video_frame_limit.py \
  --video data/raw/traffic-002-pedestrian.webm --max-frames 3
/home/clickvos/.venvs/clickvos/bin/python -m pytest -q
/home/clickvos/.venvs/clickvos/bin/python scripts/check_repository.py
```

真实 FFmpeg 检查输出：`max_frames=3`，`extracted_before_rejection=4`，`task_status=frame_extraction_failed`，`error_code=video_too_many_frames`。临时任务目录由验证脚本在检查后自动清理；并未删除已有项目任务。全项目测试 65 项通过（6.79 秒）；仓库检查通过，16 份结果摘要、115 个已跟踪文件，无已跟踪模型或视频。

## 边界与后续

当前默认 300 帧主要保护短视频试用；它不是对 60 秒视频的承诺。以 30 FPS 为例，超过约 10 秒就会被拒绝。申报书中的 60 秒等目标仍属待验证，未来如需提高帧数上限，必须先评估 GPU 显存、内存、磁盘占用和端到端耗时。该上限也不能单独防止极高分辨率视频的资源消耗，后续部署前需补充尺寸约束和真实设备压力测试。
