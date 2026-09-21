# ClickVOS Traffic

这是一个正在开发中的大创项目，尝试把 SAM2 做成一套更适合交通视频的交互式标注工具。

现在可以上传短视频，在首帧用正点和负点选择车辆、行人或非机动车，再把掩码传播到后续帧。如果传播过程中出现目标丢失、错误重现或多个掩码重叠，界面会把相应帧列出来，用户可以检查并补点修正。

项目仍处于原型阶段。功能已经可以完整跑通，但公开数据评估、十人试用和云端部署还没有完成。Docker 配置已经加入仓库，尚未完成实机镜像构建验证。

## 已实现

- MP4 上传、抽帧和视频信息检查
- 多目标正负点提示，最多 20 个对象
- SAM2.1 视频掩码传播
- 指定中间帧补点并继续传播
- 目标消失后异常重现保护
- 异常帧定位、候选确认及撤销
- 多目标掩码重叠提示
- 本地历史任务预览和再次导出
- 历史任务占用预览、精确确认和可恢复清理
- 逐对象 PNG 掩码、预览视频、项目 JSON 和 COCO RLE 导出

目前主要在 WSL 24.04、Python 3.12、PyTorch 2.11.0+cu128 和 RTX 5060 Laptop GPU 上开发。模型使用 SAM2.1 Hiera Tiny，权重不会提交到仓库。

## 运行 Web 界面

先准备好项目环境和 SAM2 权重，然后在 WSL 中执行：

```bash
python -m pip install -r requirements-app.txt
python -m pip install -e .

export CLICKVOS_CHECKPOINT=/absolute/path/to/sam2.1_hiera_tiny.pt
python -m clickvos.web_app
```

浏览器打开 `http://127.0.0.1:7860`。基本操作顺序是：

1. 上传交通视频并抽帧。
2. 选择类别，新建目标。
3. 在目标内部添加正点；必要时在邻近物体上添加负点。
4. 运行传播，查看预览和异常列表。
5. 在错误帧补点修正，确认或撤销可疑候选。
6. 生成标注下载包。

每个目标至少需要一个正点。当前版本是本地单用户程序，同时只保留一个活动推理会话。

## Docker（待实机验证）

仓库已经提供 `Dockerfile`、`compose.yaml` 和 `.env.example`。权重从宿主机只读挂载，不会写入镜像：

```bash
cp .env.example .env
# 编辑 .env 中的 CLICKVOS_MODEL_DIR
docker compose build
docker compose up -d
```

当前开发机没有安装 Docker，因此这里只表示部署配置已经准备好，不表示镜像已经构建成功。完整前置条件和验证步骤见 [`docs/operations/docker-deployment.md`](docs/operations/docker-deployment.md)。

## 命令行示例

检查和抽取视频：

```bash
python -m clickvos.video_io inspect sample.mp4
python -m clickvos.video_io prepare sample.mp4 \
  --tasks-root outputs/tasks --task-id demo
```

运行单目标传播：

```bash
python scripts/run_sam2_video.py \
  --video sample.mp4 \
  --checkpoint /absolute/path/to/model.pt \
  --output outputs/tasks/demo \
  --positive 520,370 \
  --category vehicle
```

导出已有任务：

```bash
python -m clickvos.export bundle outputs/tasks/<task-id>
```

## 当前验证情况

仓库中的数字都来自实际运行记录，没有真值的视频不报告 IoU、J 或 F。

- CP-02 使用一段 CC BY 3.0 的夜间高速公路视频完成了 50 帧传播。
- 单目标推理耗时 7.46 秒，有效速度约 6.70 FPS，峰值 CUDA 分配约 575 MiB。
- 原目标离场后，SAM2 在第 46 帧错误激活到了另一辆车。这一案例现在用于回归测试异常保护和人工复核流程。
- 双车辆任务已经验证独立掩码与合成预览；行人 50 帧和非机动车 28 帧也已完成授权公开视频的真实 GPU 回归。两者没有逐帧真值，因此不报告精度。
- DAVIS `bike-packing` 自行车对象已跑通官方指标链路：中间 67 帧实测 J=0.7445、F=0.7796、J&F=0.7620。该片段不是合格的交通场景评估样本，只作为指标流水线验证。
- DAVIS 验证集 `car-roundabout` 已完成第一条道路交通真值对照：单个正点只选中车门局部，J&F=0.0942；覆盖整车的 4 个正点加 1 个背景负点达到 J&F=0.9750。该结果只适用于这一条序列。
- 最近一次自动化测试结果为 `42 passed`（2026-09-21）。

详细数据在 [`docs/research/results/`](docs/research/results/)，对应的命令、环境和问题记录在 [`docs/checkpoints/`](docs/checkpoints/)。

## 已知限制

- 重新激活保护只是保守规则，不具备身份识别能力，也可能拦截真正重新出现的目标。
- 最大连通区域过滤只能去掉不相连的小碎片，不能修复相连区域的边界错误。
- 当前测试素材较少，异常规则的命中率和误报率还不能下结论。
- 已完成一条车辆道路交通真值基线，但尚无带真值的道路行人、非机动车和多目标交通评估。
- 历史任务目前只能预览和再次导出，尚不能恢复成可继续补点的 SAM2 会话。
- 清理只会把任务移入项目回收区，不释放空间；Web 恢复和永久过期清理尚未实现。
- 尚未完成自动清理、Docker 实机构建和云端部署。

## 数据使用

项目不使用私人照片或来源不明的视频做测试。新增素材必须是自有、明确授权或许可证清晰的交通视频，并在 [`docs/research/data-sources.md`](docs/research/data-sources.md) 中登记。

视频、模型权重、逐帧掩码和运行日志只保存在本地，由 `.gitignore` 排除。仓库只提交源码、配置、测试、文档和经过核对的实验摘要。

## 项目结构

```text
src/clickvos/       应用和算法代码
configs/            运行配置
scripts/            环境检查和实验脚本
tests/              自动化测试
docs/checkpoints/   可复现的阶段记录
docs/research/      数据来源与实验摘要
docs/operations/    环境、导出和仓库说明
```

接下来的工作见 [`docs/roadmap.md`](docs/roadmap.md)。标注导出格式见 [`docs/operations/export-format.md`](docs/operations/export-format.md)。

## 许可说明

仓库目前用于项目展示和过程备份，尚未添加开源许可证。公开可见不等于允许复制、修改或再发布，后续会结合软件著作权安排决定许可方式。
