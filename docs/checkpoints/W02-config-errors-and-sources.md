# 周进度记录：W02 配置、错误模型与素材候选

- 实施日期：2026-09-16
- 计划周：2026-09-28 至 2026-10-04
- 对应检查点：CP-03 前置工程任务，尚未完成整个 CP-03
- 状态：本周任务提前完成

## 实际完成

- 新增 `configs/default.json`，集中记录上传限制、抽帧质量、任务目录、SAM2 Tiny 配置、权重摘要、设备/offload 参数和三类交通对象。
- 新增配置加载与无第三方依赖的严格校验。
- 新增稳定错误代码和中文用户提示，技术细节可单独写入日志。
- 视频输入层已使用统一错误模型；命令行已实际读取默认配置。
- 登记行人、非机动车各一个许可清晰的候选视频；本次没有下载或运行候选素材。

## 可复现命令

```powershell
wsl.exe -d Ubuntu-24.04 --cd "/mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS" -- `
  /home/clickvos/.venvs/clickvos/bin/python -m pytest -q
```

配置驱动的视频检查命令：

```bash
/home/clickvos/.venvs/clickvos/bin/python -m clickvos.video_io \
  --config configs/default.json inspect data/processed/cp02/traffic-sample.mp4
```

## 实际版本与输入

- Python 环境：`/home/clickvos/.venvs/clickvos`。
- pytest：9.1.1（沿用 W01 已记录的实际安装版本）。
- 自动化测试仅使用临时生成的小文件和既有配置，没有新增真实媒体输入。
- 候选来源页面及许可证记录见 `docs/research/data-sources.md`。

## 实际结果

```text
.......                                                                  [100%]
7 passed in 0.19s
```

本次没有运行 SAM2、没有下载候选视频，因此没有新增帧数、推理速度、显存或精度数据。

## 遇到的问题

- 首次组合测试命令被 PowerShell 提前解析了内层 Python `-c` 代码，报错发生在进入 WSL 之前。拆成直接调用 `python -m pytest` 后测试通过。
- WSL 仍输出 localhost/NAT 警告乱码，但实际测试退出码为 0；问题尚未影响当前项目功能。

## 下周任务

- 把 `run_sam2_video.py` 的模型加载、提示输入和传播逻辑封装为单目标 `sam2_engine`，保留 CP-02 脚本作为兼容入口。
