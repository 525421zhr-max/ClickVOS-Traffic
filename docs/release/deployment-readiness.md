# 部署核查与验收步骤

2026-10-10；应用基线 `60f72860f1968d3ce714d728eead90bac7dc2a3a`。本轮执行 CPU 侧只读核查，无 GPU 推理、容器构建、服务重启或付费云任务。

## 当前检查结果

| 检查项 | 实际结果 |
| --- | --- |
| Windows / WSL 的 docker 命令 | 均未找到，无法执行真实 Compose 校验和构建 |
| 现有 Python 依赖 | pip check：No broken requirements found. |
| Python / PyTorch / torchvision | 3.12.3 / 2.11.0+cu128 / 0.26.0+cu128 |
| Gradio / FastAPI / Uvicorn | 6.27.0 / 0.141.1 / 0.53.0，与 requirements-app.txt 一致 |
| SAM2 源码 | 2b90b9f5ceec907a1c18123530e92e794ad901a4，与 Docker/Compose 固定提交一致 |
| 权重 SHA-256 | 7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69，与配置一致 |
| FFmpeg / FFprobe | 现有 WSL 路径可找到 |
| Compose 内容 | YAML 可解析，宿主机端口只绑定 127.0.0.1，模型只读挂载，输出持久化，声明 GPU |
| 容器入口 | verify_deployment.py 后启动 clickvos.web_app，即原 Gradio |
| 统一网站静态文件 | Dockerfile 未复制 web/site，现有镜像方案不包含统一网站交付 |

SAM2 在本机从已配置的源码目录可定位，Git 提交已核对；本轮查询发行包名 sam2 未找到 metadata，不据此误判模型缺失或重装环境。核对脚本使用模块位置和 Git 提交判断源码身份。

YAML 解析只验证结构可读取，不等于 Docker Compose 完整语义校验。当前 gpus 属性要求 Compose 2.30.0 或更新版本，依据 [Docker 服务属性文档](https://docs.docker.com/reference/compose-file/services/#gpus)。[docker compose config](https://docs.docker.com/reference/cli/docker/compose/config/) 才是后续真实环境的配置解析和校验入口。

## 明确的部署缺口

1. **没有构建证据。** 未执行镜像拉取、构建、容器内 CUDA 预检和视频运行，因此不能写部署成功。
2. **部署对象需区分。** 当前容器覆盖原 Gradio。统一网站还需静态文件、网关配置、访问码、受控 HTTPS 入口及相应测试，不能简单把现有 7860 端口公开即称统一站点上线。
3. **构建尚非完整锁定。** SAM2 提交和主要 Python 包已有固定版本；基础镜像使用 tag，系统包、构建工具及部分传递依赖未完整固定。待真实构建后记录镜像 digest 和实际依赖，不凭空填写 digest。
4. **当前只有单活动推理。** 多用户队列、可编辑会话恢复、永久过期清理仍需独立设计验证；不增加 worker 或副本来假装获得隔离能力。

## 下一台有 Docker 的机器如何验收

使用单独检出目录和空的输出目录，避免把当前十人试用的 outputs 挂入测试容器。先准备正确权重，确认 GPU 空闲。以下步骤尚未执行，不是本轮日志：

```bash
docker version
docker compose version
docker compose config --quiet
docker compose build
docker compose run --rm clickvos python scripts/verify_deployment.py \
  --config /app/configs/default.json \
  --checkpoint /models/sam2.1_hiera_tiny.pt
docker compose up -d
docker compose ps
docker compose logs --tail=100 clickvos
```

使用 .env.example 在该独立目录准备私有 .env，填写 Linux/WSL 权重目录；不要将本机 .env 或访问码提交。端口仍只绑定 127.0.0.1。命令在新部署主机执行，不直接在当前主持人试用服务旁启动第二个 GPU 任务。

先用已有授权 T1 短片完成上传、整车提示、传播与 ZIP 下载；记录 task ID、版本、总耗时、峰值显存、实际下载哈希、PNG/RLE 核验、首中尾人工复核以及完整错误日志。随后用 T3 检查两对象及第 15 帧修正；达到原任务预算即停止，不扩大成全量数据集运行。

检查重启后任务文件可读取、再次导出可核验；这只验证文件持久化，不声称恢复可编辑会话。受控 HTTPS、上传限制、身份访问和隔离测试必须在真实云端另留记录。源视频、权重、掩码和含权限配置不进入公开镜像。

## 容器/云端验收记录模板

| 字段 | 待实测填写 |
| --- | --- |
| 日期、操作者、主机/GPU | 待执行 |
| 应用提交、镜像 ID/digest、Compose 版本 | 待执行 |
| 构建退出码、日志路径、依赖清单 | 待执行 |
| CUDA/权重/FFmpeg 预检 | 待执行 |
| 视频来源、SHA-256、帧数、目标数、提示 | 待执行 |
| 推理耗时、显存、任务与 ZIP 路径 | 待执行 |
| PNG/RLE 核验、首中尾目标人工复核 | 待执行 |
| 重启持久化、故障、资源限制、访问控制 | 待执行 |
| 云 GPU 使用时长和实际费用（若有） | 待执行 |

环境审计原始输出位于本机 outputs/tasks/dev38-release-preparation/environment-audit.json；它不包含访问码，也未读取个人反馈。
