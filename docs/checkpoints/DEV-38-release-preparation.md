# DEV-38：部署核查与软著材料准备

日期：2026-10-10。应用基线 `60f72860f1968d3ce714d728eead90bac7dc2a3a`，包版本 `0.1.0`。本轮是文档与归档工作，不修改应用、Docker/Compose 配置、正式试用协议或参与者记录，不启动 GPU 推理和外网部署。

## 实际完成

- 检查现有 Dockerfile、Compose、忽略文件、依赖和部署预检脚本。Windows `Get-Command docker` 与 WSL `shutil.which('docker')` 均未找到命令；没有 Docker CLI 语义校验、镜像构建或容器 GPU 运行。
- `pip check` 返回 `No broken requirements found.`；读取现有源码位置并核对 SAM2 提交、模型 SHA-256，与既有配置一致。
- Compose YAML 可解析；端口只发布到宿主机 127.0.0.1、模型只读挂载、输出持久化、GPU 请求及健康检查存在。静态解析不等于真实 Compose 验收。
- 识别部署覆盖缺口：现有容器入口是 `clickvos.web_app`，未复制统一网站静态文件，不具备完整统一网站网关的容器配置。
- 整理 `docs/release/`：软件使用说明书、功能证据表、部署验收步骤、软著待确认与结题清单、准备报告。
- 本机生成 7 页软件说明书与 4 页准备报告，已渲染逐页检查。按应用提交提取 21 个源码/配置文件，共 5188 行、248151 字节，ZIP 内逐文件哈希验证通过。
- 同步 README 全量测试日期，修正路线图中与回收区功能矛盾的旧描述，补齐 DEV-36/37/38 索引。

## 本轮检查

```powershell
wsl -d Ubuntu-24.04 --exec /home/clickvos/.venvs/clickvos/bin/python -m pip check
wsl -d Ubuntu-24.04 --exec /home/clickvos/.venvs/clickvos/bin/python -m pytest -q tests/test_config.py tests/test_task_store.py tests/test_export.py
wsl -d Ubuntu-24.04 --exec /home/clickvos/.venvs/clickvos/bin/python scripts/check_repository.py
```

定向测试实际结果：`18 passed in 0.74s`。仓库检查通过。152 项全量通过是 DEV-37 的历史记录，本轮不重复宣称全量测试已运行。没有新增视频实验、质量指标或真人样本。

## 版本和本地证据

环境：Python 3.12.3；torch 2.11.0+cu128；torchvision 0.26.0+cu128；Gradio 6.27.0；FastAPI 0.141.1；Uvicorn 0.53.0。SAM2 源码提交 `2b90b9f5ceec907a1c18123530e92e794ad901a4`；权重 SHA-256 `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`。

本机 `outputs/tasks/dev38-release-preparation/` 保存 `audit_environment.py`、`environment-audit.json`、PDF 构建脚本、构建摘要、页面复核图片、打包校验及 deliverables。源码 ZIP 摘要在本地构建清单中；文件内容由 `source-manifest.csv` 和 ZIP 内清单独立追溯到应用提交。生成的 PDF/ZIP 不进入公开仓库。

## 遇到的问题和边界

查询发行包名 `sam2` 时没有 distribution metadata；模块仍可从已有源码目录定位，Git 提交一致。修正审计方式后继续，没有重装模型或把该情况写成 SAM2 不可用。Docker 缺失使构建与云端执行仍待安排；未因材料整理而安装系统组件、调整代理/账号或购买算力。

源码快照不包含上游 SAM2、安装依赖、字体图标、媒体、权重或试用产物；它不是完整安装包或已按正式格式排版的源码鉴别材料。软著名称、权利人、实际日期和渠道信息待用户确认；最终截图待版本冻结后补齐。正式申报、云部署与真实试用统计尚未完成，CP-09/CP-10 不标完成。

下一步在独立 Docker/NVIDIA 环境完成短片构建与运行验收，同时收取真实试用记录；实际云端运行另落实预算和环境。统一网站的容器化作为独立后续实现，不改动本轮正式 Gradio 试用。
