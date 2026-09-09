# 环境清单（待填写）

| 项目 | 实际值 |
| --- | --- |
| Windows 版本 | Windows 10 家庭中文版 25H2，内部版本 26200.9168 |
| GPU 与显存 | NVIDIA GeForce RTX 5060 Laptop GPU，8151 MiB |
| NVIDIA 驱动 | 591.97；驱动报告最高 CUDA 13.1 |
| WSL 发行版 | WSL 2.7.13；Ubuntu 24.04.4 LTS；内核 6.18.33.2-microsoft-standard-WSL2 |
| Linux 用户 | `clickvos`（默认普通用户） |
| Python | 3.12.3；虚拟环境 `/home/clickvos/.venvs/clickvos` |
| PyTorch / CUDA | PyTorch 2.11.0+cu128；CUDA runtime 12.8；torchvision 0.26.0+cu128 |
| ffmpeg | 6.1.1-3ubuntu5 |
| SAM2 提交版本与权重来源 | 待从 Meta 官方仓库固定提交；权重不纳入 Git |

填完此表、附上环境检测命令输出后，创建 CP-01 的前置提交。

## 版本选择依据

- SAM2 官方建议 Windows 用户使用 WSL + Ubuntu，并要求 Python >= 3.10、PyTorch >= 2.5.1。
- RTX 5060 属于新架构，采用 PyTorch 官方提供的 CUDA 12.8 wheel，避免旧版 wheel 缺少对应 GPU 内核。
- Windows 中的 NVIDIA 驱动由 WSL 共享；当前不在 WSL 内重复安装 NVIDIA 驱动。

## 验证结果

- `torch.cuda.is_available()`：`True`
- GPU：NVIDIA GeForce RTX 5060 Laptop GPU
- CUDA compute capability：`12.0`
- 2048×2048 CUDA 矩阵乘法：成功
- 可重复验证命令：`~/.venvs/clickvos/bin/python scripts/verify_environment.py`

## 当前未完成项

Meta SAM2 官方 Git 仓库的直连在当前网络下失败；codeload 压缩包也发生提前断流，损坏文件未用于安装。SAM2 尚未计入本环境 checkpoint。
