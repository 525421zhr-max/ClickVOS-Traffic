# DEV-26：DAVIS crossing 三目标联合传播

- 日期：2026-09-24
- 状态：一条完整道路交通序列的三目标联合传播与逐对象真值评估完成；不是 DAVIS 全集评估

## 为什么不跑完整 DAVIS

DEV-16 的 75 帧是 `car-roundabout` 一条序列的全部帧，不是从更长序列里截取的 75 帧。ClickVOS 的研究对象是交通视频，把整个包含大量非交通场景的 DAVIS 跑完，不能直接填补当前缺少多目标道路真值和非机动车道路真值的证据缺口。本轮先复用已登记的 `crossing` 全 52 帧，验证同一会话中的两名行人与一辆货车。

## 运行前冻结的合同

提示、预算、0.7 首帧 IoU 门槛、官方 DAVIS J/F 端点和结论边界先记录于 `docs/research/quality-pilot.md`。首帧 GT 标签核对：三个对象的 3 个正点分别落在对象 ID 1、2、3 上，各自负点落在另一对象上。没有在看到模型输出后改提示或重跑。

## 输入与复现命令

- 数据：DAVIS 2017 `crossing`，52 张 854×480 RGB 和 52 张逐帧实例真值；来源与许可见 `docs/research/data-sources.md`。
- 环境：WSL Ubuntu 24.04，Python 3.12.3，PyTorch 2.11.0+cu128，NVIDIA GeForce RTX 5060 Laptop GPU。
- 模型：SAM2.1 Hiera Tiny，权重 SHA-256 `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`。官方 DAVIS 评价包版本 0.1.0。

```bash
cd /mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS
/home/clickvos/.venvs/clickvos/bin/python scripts/run_sam2_multi_frames.py \
  --frames-dir data/raw/davis2017/trainval-crossing/DAVIS/JPEGImages/480p/crossing \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  --prompt-config configs/experiments/davis-crossing-three-objects.json \
  --output outputs/tasks/davis-crossing-three-objects-001

for id in 1 2 3; do
  object_dir=$(printf 'object_%03d' "$id")
  /home/clickvos/.venvs/davis-eval/bin/python scripts/evaluate_davis_masks.py \
    --ground-truth-dir data/raw/davis2017/trainval-crossing/DAVIS/Annotations/480p/crossing \
    --prediction-dir "outputs/tasks/davis-crossing-three-objects-001/$object_dir/masks" \
    --object-id "$id" --sequence crossing \
    --output "outputs/tasks/davis-crossing-three-objects-001/$object_dir/davis-metrics.json"
  /home/clickvos/.venvs/davis-eval/bin/python scripts/evaluate_davis_masks.py \
    --ground-truth-dir data/raw/davis2017/trainval-crossing/DAVIS/Annotations/480p/crossing \
    --prediction-dir "outputs/tasks/davis-crossing-three-objects-001/$object_dir/masks" \
    --object-id "$id" --sequence crossing --include-endpoints \
    --output "outputs/tasks/davis-crossing-three-objects-001/$object_dir/endpoint-metrics.json"
done
```

首帧 IoU 取各对象 `endpoint-metrics.json` 的第一条 `per_frame.j`；三个值均超过预定 0.7 门槛。表中的 J/F 只取不带 `--include-endpoints` 的标准输出，按 DAVIS 约定汇总中间 50 帧。

## 实际结果

| 目标 | 保存掩码 | 首帧 IoU | J | F | J&F |
| --- | ---: | ---: | ---: | ---: | ---: |
| ID 1，深色衣服行人 | 52 | 0.8762 | 0.9154 | 0.9868 | 0.9511 |
| ID 2，浅色衣服行人 | 52 | 0.9222 | 0.9372 | 0.9944 | 0.9658 |
| ID 3，货车 | 52 | 0.9803 | 0.9615 | 0.9862 | 0.9739 |

联合会话推理及输出耗时 19.8770 秒，52 帧对应 2.6161 FPS；峰值 CUDA 分配 651,203,584 字节。人工查看三目标各自的第 25 帧和第 51 帧绿色叠加图，掩码仍覆盖原先的两名行人与同一辆货车。对象 1 的联合 J&F=0.9511；DEV-20 同提示单目标 J&F=0.9519。差值仅是同序列观察，不构成多目标对精度影响的普遍结论。

## 问题与边界

- SAM2 的可选 `_C` 扩展仍不可用，运行时跳过填洞后处理；核心传播成功。
- 同一段视频里的三个对象不能当作三个独立交通场景。还没有道路非机动车逐帧真值、多视频泛化或异常保护误拦截统计。
- 本次只跑一次，耗时不能与不同日期的单目标运行做可靠速度比较。
- 原始媒体、GT、掩码和叠加图只保存在本地，不上传 Git；公开展示画面前仍须复核 DAVIS 原视频来源条款。

本地原始结果：`outputs/tasks/davis-crossing-three-objects-001/result.json`，逐对象目录下有 `masks/`、`overlays/`、`davis-metrics.json`。仓库保留可复现提示和摘要，不把本结果称作完整 DAVIS 基准。

回归检查：WSL 项目环境 `python -m pytest -q` 为 67 项通过（6.37 秒）；`scripts/check_repository.py` 通过，17 份结果摘要，未跟踪原始媒体或模型文件。
