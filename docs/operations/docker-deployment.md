# Docker 与云 GPU 部署准备

当前容器方案用于运行完整的 Python、PyTorch、SAM2 和 Gradio 应用。模型权重不写入镜像，也不上传 GitHub；启动时从宿主机目录只读挂载。

## 前置条件

- Linux 或 WSL 2 主机
- NVIDIA 驱动
- Docker Engine 与 Compose 插件
- NVIDIA Container Toolkit，容器内必须能够执行 `nvidia-smi`
- 与配置文件摘要一致的 `sam2.1_hiera_tiny.pt`

## 本地构建和启动

复制环境变量示例并填写权重所在目录：

```bash
cp .env.example .env
docker compose build
docker compose run --rm clickvos \
  python scripts/verify_deployment.py \
  --config /app/configs/default.json \
  --checkpoint /models/sam2.1_hiera_tiny.pt
docker compose up -d
docker compose ps
docker compose logs --tail=100 clickvos
```

浏览器访问 `http://127.0.0.1:7860`。Compose 默认只绑定宿主机回环地址，不会直接暴露到公网。

## 云端接入边界

云 GPU 上仍使用同一镜像和只读模型挂载。公网访问应经过 HTTPS 反向代理，并在代理层设置请求体大小、超时和访问控制；不要直接开放 Gradio 的 7860 端口。ChatGPT Sites 或其他前端只能通过受控 HTTPS 接口访问推理服务。

正式部署前还需要完成：

1. 在真实 Docker/NVIDIA Container Toolkit 环境构建镜像。
2. 跑通一个合规交通短视频并保留容器日志、耗时和显存记录。
3. 验证上传限制、任务目录隔离和过期清理。
4. 决定是否增加队列；当前应用仍是单活动推理会话。

## 当前验证状态

仓库已具备 Dockerfile、Compose 配置、环境变量入口、存活检查和部署前检查脚本。开发机尚未安装 Docker，因此尚未声称镜像已成功构建，也没有云端运行数据。详见 `docs/checkpoints/DEV-13-container-foundation.md`。
