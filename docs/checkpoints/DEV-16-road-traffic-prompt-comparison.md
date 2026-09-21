# DEV-16：道路车辆首帧提示对照

- 日期：2026-09-21
- 状态：首条道路交通真值小样本完成；CP-07 尚未完成多类别覆盖

## 研究问题

在同一辆道路车辆上，单个正点落在车门区域与多个正点覆盖整车时，SAM2 会传播同一个实例，还是传播不同的对象粒度？

## 输入与环境

- DAVIS 2017 验证集 `car-roundabout`，75 帧，854×480，逐帧对象 1 真值为 `car`。
- 许可、获取方式和文件清单哈希见 `docs/research/data-sources.md` 的 `davis-002-car-roundabout`。
- WSL Ubuntu 24.04，Python 3.12.3，PyTorch 2.11.0+cu128，CUDA runtime 12.8。
- NVIDIA GeForce RTX 5060 Laptop GPU。
- SAM2.1 Hiera Tiny 权重 SHA-256：`7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`。
- 官方 `davis2017` 0.1.0，评估仓库提交 `ac7c43fca936f9722837b7fbd337d284ba37004b`。
- 两组均不启用最大连通区域等 ClickVOS 后处理。

## 可复现命令

单正点加背景负点：

```bash
python scripts/run_sam2_frames.py \
  --frames-dir data/raw/davis2017/trainval-road-cars/DAVIS/JPEGImages/480p/car-roundabout \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  --output outputs/tasks/davis-car-roundabout-baseline \
  --positive 430,270 --negative 155,235 --category vehicle
```

多正点覆盖整车并保留同一个背景负点：

```bash
python scripts/run_sam2_frames.py \
  --frames-dir data/raw/davis2017/trainval-road-cars/DAVIS/JPEGImages/480p/car-roundabout \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  --output outputs/tasks/davis-car-roundabout-multipoint \
  --positive 305,270 --positive 430,270 --positive 560,285 --positive 320,320 \
  --negative 155,235 --category vehicle
```

两次运行分别使用 `scripts/evaluate_davis_masks.py`，真值目录为 `DAVIS/Annotations/480p/car-roundabout`，对象 ID 为 1。评估排除首尾帧，与官方 DAVIS 评估约定一致。

## 实际结果

| 提示策略 | 评估帧 | J | F | J&F | 推理时间 | FPS | 峰值 CUDA |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 正点（车门）+ 1 负点（背景车） | 73 | 0.1424 | 0.0459 | 0.0942 | 10.6722 s | 7.0276 | 602,774,016 B |
| 4 正点（覆盖整车）+ 1 负点（背景车） | 73 | 0.9807 | 0.9693 | 0.9750 | 17.0182 s | 4.4070 | 602,774,016 B |

多点组相对单点组的 J&F 绝对差为 0.8808。多点组最低 J 为 0.9705（第 22 帧），最低 F 为 0.9302（第 28 帧）。

## 视觉检查与解释

- 单点组在首帧只分出了前车门附近区域，并在后续帧稳定传播这一局部区域。它没有主要串到背景车辆，但对象粒度从一开始就错了。
- 多点组首帧覆盖车尾、车门、车头和车轮附近；人工检查第 0、22、37、74 帧，掩码保持在同一辆灰色汽车上并覆盖完整车体。
- 因此本序列支持的结论是：对具有可分割部件的大型对象，仅在局部点击可能稳定得到“部件级”而非“实例级”传播；界面需要引导用户检查首帧完整性。
- 两次运行速度差异来自单次实测，未做重复计时，不能据此声称多点一定降低吞吐率。

## 遇到的问题

- DAVIS 官方 ZIP 支持 Range，但逐个小文件提取速度较慢；本轮只保存完整的 `car-roundabout`，没有把不完整下载计入实验。
- 当前 SAM2 环境缺少可选原生扩展 `sam2._C`，运行时跳过孔洞填充后处理。官方警告说明核心推理仍可使用；两组在相同环境运行，因此对照条件一致，但后续应单独修复并复测。
- 该序列只有单个车辆对象，结果不能外推到行人、非机动车、遮挡和多目标场景。

## 本地证据

- `outputs/tasks/davis-car-roundabout-baseline/result.json`
- `outputs/tasks/davis-car-roundabout-baseline/davis-metrics.json`
- `outputs/tasks/davis-car-roundabout-multipoint/result.json`
- `outputs/tasks/davis-car-roundabout-multipoint/davis-metrics.json`
- `outputs/tasks/davis-car-roundabout-multipoint/preview.mp4`

预览视频是 10 FPS 的检查用可视化，不表示原视频真实帧率。生成物不提交 Git；核对摘要位于 `docs/research/results/dev16-road-traffic-prompt-comparison.json`。
