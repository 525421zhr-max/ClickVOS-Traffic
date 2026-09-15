# 周进度记录：W01 视频输入工程底座

- 实施日期：2026-09-15
- 计划周：2026-09-21 至 2026-09-27
- 对应检查点：CP-03 的视频输入子任务，尚未完成整个 CP-03
- 状态：本周任务提前完成

## 实际完成

- 新增可安装的 `clickvos-traffic` Python 包配置。
- 新增 `clickvos.video_io`，统一实现视频存在性、扩展名和 200 MiB 默认上限校验。
- 使用 `ffprobe` 读取宽、高、帧率、帧数、时长、编码和文件大小。
- 建立隔离的任务目录：`source/`、`frames/`、`masks/`、`overlays/`、`exports/`。
- 使用 `ffmpeg` 抽取按五位数字排序的 JPEG 帧，并生成 `task.json`。
- `run_sam2_video.py` 已改为复用统一抽帧函数。
- 新增 4 个视频输入单元测试和周记录模板。

## 可复现命令

```bash
cd '/mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS'
/home/clickvos/.venvs/clickvos/bin/python -m pip install -e . pytest
/home/clickvos/.venvs/clickvos/bin/python -m pytest -q
/home/clickvos/.venvs/clickvos/bin/python -m clickvos.video_io inspect \
  data/processed/cp02/traffic-sample.mp4
/home/clickvos/.venvs/clickvos/bin/python -m clickvos.video_io prepare \
  data/processed/cp02/traffic-sample.mp4 \
  --tasks-root outputs/tasks --task-id w1-cp02-video-io
```

## 实际版本与输入

- Python：3.12 环境 `/home/clickvos/.venvs/clickvos`；本次命令未重新输出补丁版本，沿用 CP-02 已确认的 3.12.3。
- pytest：9.1.1，本次实际安装输出确认。
- 输入：`traffic-001` 的 5 秒 CP-02 裁剪，来源与 CC BY 3.0 许可见 `docs/research/data-sources.md`。
- 没有使用个人照片、人像或私人素材。

## 实际结果

单元测试实际输出：

```text
....                                                                     [100%]
4 passed in 0.14s
```

真实视频输入工具实际输出：

| 字段 | 实际值 |
| --- | --- |
| 宽 × 高 | 960 × 540 |
| 帧率 | 10.0 FPS |
| 容器报告帧数 | 50 |
| 时长 | 5.0 秒 |
| 编码 | H.264 |
| 文件大小 | 459,423 字节 |
| 实际抽取帧数 | 50 |

生成的本地任务目录为 `outputs/tasks/w1-cp02-video-io/`，该目录被 Git 忽略。此次只验证视频输入层，没有运行 SAM2，因此没有新增推理速度、显存或分割精度数据。

## 遇到的问题

- Windows PowerShell 中没有全局 `python` 命令，所以测试必须从 WSL 虚拟环境运行。
- 第一次调用 `clickvos-video` 失败，因为虚拟环境未激活且其 `bin` 不在当前 PATH。文档已统一改成明确解释器调用 `python -m clickvos.video_io`。
- WSL 启动时输出了一段 localhost/NAT 警告乱码，但本次命令退出码为 0，ffprobe 和 ffmpeg 均正常完成；暂不将其判定为项目故障。

## 下一周任务

- 登记车辆、行人、非机动车三类素材候选，并建立可机器读取的配置与用户错误模型。

