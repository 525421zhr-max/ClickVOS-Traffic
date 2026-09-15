# CP-01：SAM2 最小视频验证

- 日期：2026-09-14
- 状态：完成。
- 闭环：`生成小样本 MP4 → ffmpeg 抽帧 → 首帧正/负点提示 → SAM2 视频传播 → 二值 PNG 掩码保存`。
- 验证脚本：`scripts/verify_sam2_video.py`。
- 机器可读结果：`outputs/cp01/result.json`。

## 实际环境与版本

| 项目 | 实际值 |
| --- | --- |
| WSL | Ubuntu 24.04，发行版名 `Ubuntu-24.04` |
| Python | 3.12.3 |
| 虚拟环境 | `/home/clickvos/.venvs/clickvos` |
| GPU | NVIDIA GeForce RTX 5060 Laptop GPU |
| PyTorch | `2.11.0+cu128` |
| torchvision | `0.26.0+cu128` |
| PyTorch CUDA runtime | 12.8 |
| SAM-2 包 | 1.0，可编辑安装 |
| Meta SAM2 源码提交 | `2b90b9f5ceec907a1c18123530e92e794ad901a4` |
| 模型 | SAM2.1 Hiera Tiny |
| 权重字节数 | 156,008,466 |
| 权重 SHA-256 | `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69` |
| ffmpeg | `6.1.1-3ubuntu5` |
| git-lfs | `3.4.1` |

本次新增运行依赖的实际版本：`tqdm 4.70.1`、`hydra-core 1.3.6`、`omegaconf 2.3.1`、`iopath 0.1.10`、`PyYAML 6.0.3`、`portalocker 4.3.2`。已有 `numpy 2.5.2`、`Pillow 12.3.0` 保持不变。

## 安装与下载命令

GitHub 主站、Raw 和 Hugging Face 在 Windows 与 WSL 中均发生 HTTPS 超时。因此源码仍取自 Meta 官方 GitHub 仓库，但通过可达代理进行稀疏克隆；检出的提交号与此前直接获取的 Git 元数据一致。

```bash
git clone --depth 1 --filter=blob:none --sparse \
  https://gh-proxy.com/https://github.com/facebookresearch/sam2.git \
  /home/clickvos/sam2-official-2b90b9f
git -C /home/clickvos/sam2-official-2b90b9f sparse-checkout set sam2
git -C /home/clickvos/sam2-official-2b90b9f rev-parse HEAD
```

权重来自可达的 ModelScope `facebook/sam2.1-hiera-tiny` 镜像。Git LFS 指针声明的 SHA-256 和大小均与下载后的文件一致。

```bash
sudo apt-get update
sudo apt-get install -y git-lfs
git clone --depth 1 --filter=blob:none --no-checkout \
  https://www.modelscope.cn/models/facebook/sam2.1-hiera-tiny.git \
  /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914
git -C /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914 lfs install --local
git -C /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914 \
  lfs pull --include=sam2.1_hiera_tiny.pt
sha256sum \
  /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt
```

直接执行普通可编辑安装时，pip 构建隔离会再次访问不可达的 PyPI 并尝试下载 Torch。解决方式是从可达的清华镜像补齐小依赖，然后关闭构建隔离和依赖解析，复用现有 PyTorch：

```bash
/home/clickvos/.venvs/clickvos/bin/python -m pip install \
  tqdm hydra-core iopath \
  -i https://pypi.tuna.tsinghua.edu.cn/simple

SAM2_BUILD_CUDA=0 /home/clickvos/.venvs/clickvos/bin/python -m pip install \
  --no-build-isolation --no-deps -e /home/clickvos/sam2-official-2b90b9f
```

`SAM2_BUILD_CUDA=0` 仅关闭可选的 connected-components CUDA 后处理扩展；本次核心提示分割和视频传播均在 CUDA 上实际运行。

## 可复现验证命令

从 Windows PowerShell 执行：

```powershell
wsl -d Ubuntu-24.04 -- /home/clickvos/.venvs/clickvos/bin/python `
  "/mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS/scripts/verify_sam2_video.py" `
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt `
  --output "/mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS/outputs/cp01"
```

脚本先生成 256×256、4 FPS、8 帧的移动红色方块视频，然后以 ffmpeg 从 MP4 抽取 JPEG；首帧提示为正点 `(80, 120)` 和负点 `(210, 30)`。脚本在推理前强制核验权重 SHA-256，结果直接写入 JSON，避免手工抄写实验数字。

## 实际结果

| 检查项 | 实际结果 |
| --- | --- |
| SAM2 导入 | 成功，`SAM-2==1.0` |
| 权重加载 | 成功，SHA-256 匹配 |
| 抽取帧数 | 8 |
| 传播迭代返回次数 | 8 |
| 保存掩码数 | 8 |
| 峰值 CUDA 已分配显存 | 598,046,208 字节 |
| 样例 MP4 SHA-256 | `1E50130F6AD260A3B1A9E54C501DE397AA86B8CDE3A69278356EA849CA403302` |

各帧掩码前景像素数依次为：`6400, 6418, 6400, 6400, 6400, 6433, 6400, 6400`。末帧视觉抽查显示掩码随方块移动到正确位置。该合成样例的目标真实面积是 6,400 像素；这里只记录观察值，不据此宣称真实视频上的精度。

## 输出位置

- `outputs/cp01/sample-moving-square.mp4`：实际测试视频。
- `outputs/cp01/generated_source_frames/`：用于编码样例视频的源帧。
- `outputs/cp01/extracted_frames/`：从 MP4 实际抽取的 8 张 JPEG。
- `outputs/cp01/masks/`：SAM2 保存的 8 张二值 PNG 掩码。
- `outputs/cp01/result.json`：版本、哈希、提示、帧数、掩码像素数和显存数据。

## 遇到的问题及处理

1. GitHub、GitHub Raw 和 Hugging Face HTTPS 超时；GitHub codeload 归档多次提前中断。处理：官方仓库经代理稀疏克隆，权重改用 ModelScope 的 facebook 镜像，并通过提交号/LFS SHA-256 核验。
2. WSL 启动时持续提示 localhost 代理无法在 NAT 模式镜像，但 Windows 系统代理配置实际为空；问题表现为部分境外域名不可达。当前没有修改 WSL 网络模式。
3. pip 构建隔离试图从不可达 PyPI 重新下载 Torch。处理：清华镜像安装缺失依赖，`--no-build-isolation --no-deps` 复用现有 Torch。
4. 初始环境缺少 Git LFS。处理：安装 Ubuntu `git-lfs 3.4.1`。
5. 未编译可选 `sam2._C` CUDA 扩展，运行中出现跳过填洞后处理的警告。实际核心推理成功；若后续需要该后处理，再单独验证 CUDA toolkit 编译链。

## 结论与下一步

CP-01 的“首帧正/负点产生掩码”条件已满足，同时最小视频传播和逐帧保存也已成功，可作为 CP-02 的起点。下一步应换成一个有纹理、存在遮挡或形变的真实小视频，记录传播质量和失败帧；当前合成样例只证明工程链路可运行。
