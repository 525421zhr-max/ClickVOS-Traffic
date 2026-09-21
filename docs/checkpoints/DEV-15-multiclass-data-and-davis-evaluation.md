# DEV-15：多类别素材回归与 DAVIS 指标链路

- 日期：2026-09-21
- 状态：行人、非机动车真实回归通过；DAVIS 指标链路通过；道路交通真值评估仍待完成

## 本次完成

- 下载并核验两个 Wikimedia Commons 授权交通视频，分别覆盖行人和非机动车。
- 人工拒绝一个不适合外部目标分割的第一视角骑行候选，没有将其计入实验。
- 对行人 50 帧、非机动车 28 帧运行 SAM2.1 Hiera Tiny，并保存掩码、叠加帧与预览。
- 从 DAVIS 2017 官方压缩包按需提取 `bike-packing` 的 69 帧与真值，避免下载完整 833 MB 文件。
- 增加有序 JPEG 帧目录推理脚本和官方 DAVIS J/F 评估脚本。

素材来源、许可、原文件哈希、裁剪参数和拒绝原因见 `docs/research/data-sources.md` 与 `data/data_report.md`。本次没有使用私人照片。

## 可复现命令

```bash
python scripts/run_sam2_video.py \
  --video data/processed/traffic-002/sample.mp4 \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  --output outputs/tasks/category-pedestrian-001 \
  --positive 530,330 --negative 650,350 \
  --category pedestrian --keep-largest-component

python scripts/run_sam2_video.py \
  --video data/processed/traffic-003/sample.mp4 \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  --output outputs/tasks/category-nonmotor-001 \
  --positive 250,350 --positive 275,580 --negative 350,370 \
  --category non_motorized --keep-largest-component

python scripts/run_sam2_frames.py \
  --frames-dir data/raw/davis2017/trainval-bike-packing/DAVIS/JPEGImages/480p/bike-packing \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  --output outputs/tasks/davis-bike-packing-bicycle \
  --positive 350,300 --negative 520,220 \
  --category non_motorized

python -m venv /home/clickvos/.venvs/davis-eval
/home/clickvos/.venvs/davis-eval/bin/pip install -r requirements-evaluation.txt
/home/clickvos/.venvs/davis-eval/bin/python scripts/evaluate_davis_masks.py \
  --ground-truth-dir data/raw/davis2017/trainval-bike-packing/DAVIS/Annotations/480p/bike-packing \
  --prediction-dir outputs/tasks/davis-bike-packing-bicycle/masks \
  --object-id 1 --sequence bike-packing \
  --output outputs/tasks/davis-bike-packing-bicycle/davis-metrics.json
```

## 实际环境

- WSL Ubuntu 24.04，Python 3.12.3
- PyTorch 2.11.0+cu128，CUDA runtime 12.8
- NVIDIA GeForce RTX 5060 Laptop GPU
- SAM2.1 Hiera Tiny 权重 SHA-256：`7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`
- 官方 `davis2017` 包 0.1.0，评估仓库提交 `ac7c43fca936f9722837b7fbd337d284ba37004b`

## 实际结果

| 任务 | 帧数 | 提示 | 推理时间 | FPS | 峰值 CUDA | 质量指标 |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| 行人交通视频 | 50 | 1 正点 + 1 负点 | 9.4316 s | 5.3013 | 602,537,472 B | 无真值，未计算 |
| 非机动车交通视频 | 28 | 2 正点 + 1 负点 | 6.5287 s | 4.2887 | 601,987,072 B | 无真值，未计算 |
| DAVIS 自行车对象 | 69 | 1 正点 + 1 负点 | 18.3389 s | 3.7625 | 603,464,704 B | 67 帧：J 0.7445，F 0.7796，J&F 0.7620 |

人工查看行人第 0、25、49 帧，目标保持在同一名行人上。人工查看非机动车第 0、14、27 帧，骑行者远离镜头后掩码面积从 61,563 降至 2,085 像素；首帧原始掩码存在多个小连通区域，最大连通区域过滤实际生效。人工检查不能替代真值指标。

DAVIS 指标按官方评估约定排除首尾帧。此次不启用最大连通区域等后处理，测量的是提示后的 SAM2 基线输出。

## 问题与边界

- `bike-packing` 虽有 bicycle 真值，但首段为室内维护，不属于道路交通场景，不能据此验收 CP-07。
- 行人和非机动车交通素材无逐帧真值，只能作为工程回归与失败观察样本。
- DAVIS 压缩包 README 写明 CC BY-NC 4.0，且原视频还有单独条款；数据只在本地用于非商业研究，不进入软件分发包。
- 非机动车远距离阶段只剩小目标轮廓，后续应引入真实交通真值并分析小目标边界质量。

## 回归检查

- `python -m pytest -q`：`42 passed in 5.75s`
- `python -m compileall -q src scripts`：通过
- `python scripts/check_repository.py`：通过；实验摘要、类别配置和 Git 大文件排除规则均有效

## 本地证据

- `outputs/tasks/category-pedestrian-001/result.json`
- `outputs/tasks/category-pedestrian-001/preview.mp4`
- `outputs/tasks/category-nonmotor-001/result.json`
- `outputs/tasks/category-nonmotor-001/preview.mp4`
- `outputs/tasks/davis-bike-packing-bicycle/result.json`
- `outputs/tasks/davis-bike-packing-bicycle/davis-metrics.json`

这些生成物由 `.gitignore` 排除；可提交的核对摘要位于 `docs/research/results/dev15-multiclass-data-and-davis-evaluation.json`。
