# 开发环境

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
| SAM2 | Meta SAM2 提交 `2b90b9f5ceec907a1c18123530e92e794ad901a4` |
| 模型权重 | SAM2.1 Hiera Tiny；来自 ModelScope `facebook/sam2.1-hiera-tiny` 镜像 |
| 权重 SHA-256 | `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69` |

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

## SAM2 安装说明

安装时 GitHub 主站、Raw 和 Hugging Face 均出现过 HTTPS 超时，因此源码通过可达代理从 Meta 官方仓库稀疏克隆，并固定到上表提交。权重改从 ModelScope 镜像下载，文件大小和 SHA-256 与 Git LFS 元数据一致。

SAM2 的可选 `_C` 扩展未编译。核心提示分割和视频传播仍使用 CUDA；运行时会出现一条跳过孔洞后处理的警告。完整安装与验证命令见 [CP-01](../checkpoints/CP-01-sam2-minimum-validation.md)。
