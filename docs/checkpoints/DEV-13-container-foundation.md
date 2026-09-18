# 开发记录：DEV-13 容器部署底座

- 日期：2026-09-18
- 状态：配置与自动测试通过；容器实机验证待完成

## 做了什么

- 新增基于 Ubuntu 24.04、CUDA 12.8、Python 3.12 和 PyTorch 2.11+cu128 的 Dockerfile。
- 固定 Meta SAM2 源码提交，关闭可选 CUDA 扩展构建，与 CP-01 的安装方式保持一致。
- 权重通过只读卷挂载，启动前核对 SHA-256、CUDA 和 FFmpeg。
- 新增 Compose 配置，申请 NVIDIA GPU，并默认只向 `127.0.0.1` 暴露端口。
- Web 启动地址、端口和配置路径改为可通过环境变量设置；本地默认行为不变。
- 修正 Web 抽帧入口，使上传大小和 JPEG 质量真正采用项目配置值。

## 复现命令

```bash
/home/clickvos/.venvs/clickvos/bin/python -m pytest -q

/home/clickvos/.venvs/clickvos/bin/python scripts/verify_deployment.py \
  --config configs/default.json \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt

cp .env.example .env
docker compose build
docker compose up -d
```

前两条命令已在当前 WSL 环境执行。后两条是下一台具备 Docker 与 NVIDIA Container Toolkit 的机器需要执行的命令，不是已经完成的实验。

## 实际结果

| 检查项 | 结果 |
| --- | --- |
| 自动测试 | `39 passed in 6.12s` |
| Python / PyTorch | `3.12.3` / `2.11.0+cu128` |
| CUDA / GPU | CUDA 可用，runtime `12.8`，RTX 5060 Laptop GPU |
| FFmpeg / FFprobe | `/usr/bin/ffmpeg` / `/usr/bin/ffprobe` |
| 权重 SHA-256 | `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`，匹配配置 |
| Docker CLI | 当前 Windows 开发机未安装 |
| 镜像构建 | 未执行 |
| 云 GPU 运行 | 未执行 |

## 遇到的问题

- 当前开发机无法执行 `docker compose build`，因为没有 Docker CLI/Engine。
- Dockerfile 中的基础镜像和外网克隆仍需要在真实构建时验证；此前 GitHub 访问曾发生超时。
- Web 目前使用进程内活动会话，不适合直接扩成多副本并发服务。

## 下一步

- 完成部署前检查脚本的本机实际输出并补录本页。
- 在 Docker 环境完成镜像构建和单视频端到端验证。
- 实现带预览与二次确认的任务过期清理，再进行公网部署。
