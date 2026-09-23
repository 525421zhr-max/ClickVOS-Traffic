# DEV-20：道路行人真值验证与重新激活保护筛查

- 日期：2026-09-23
- 状态：完整序列和官方 J/F 评估完成；误拦截主问题因无重现触发而信息不足

## 预先约定

试验端点、单次运行预算、提示门槛和判定规则先写入 `docs/research/quality-pilot.md`，随后执行推理。首帧真值检查时发现原拟第三个正点落在背景，于运行前改为同一目标腿部的 `(375,355)`，并在合同中记录。没有依据模型输出调整提示。

## 输入与环境

- `davis-003-crossing`：DAVIS 2017 480p 城市道路斑马线片段，52 帧，854×480；来源与许可见 `docs/research/data-sources.md`。图像与实例真值各 52 张，文件名一一对应。
- 实例 1：首帧右侧深色衣服行人；正点 `(370,300)`、`(365,270)`、`(375,355)`；负点 `(285,285)` 位于另一名行人。
- WSL Ubuntu 24.04，Python 3.12.3，PyTorch 2.11.0+cu128，RTX 5060 Laptop GPU；SAM2.1 Hiera Tiny 权重 SHA-256 `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`。
- 官方 `davis2017` 评估包版本 0.1.0；不启用最大连通区域过滤。

## 可复现命令

```bash
python -m pip install -r requirements-data.txt
python scripts/fetch_davis_sequence.py \
  --sequence crossing \
  --output-root data/raw/davis2017/trainval-crossing

python scripts/run_sam2_frames.py \
  --frames-dir data/raw/davis2017/trainval-crossing/DAVIS/JPEGImages/480p/crossing \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  --output outputs/tasks/davis-crossing-person-001 \
  --positive 370,300 --positive 365,270 --positive 375,355 \
  --negative 285,285 --category pedestrian --object-id 1

python scripts/evaluate_reactivation_guard.py \
  --ground-truth-dir data/raw/davis2017/trainval-crossing/DAVIS/Annotations/480p/crossing \
  --prediction-dir outputs/tasks/davis-crossing-person-001/masks \
  --object-id 1 --minimum-empty-frames 3 \
  --output outputs/tasks/davis-crossing-person-001/guard-audit.json

# 使用单独的 DAVIS 官方评估环境
/home/clickvos/.venvs/davis-eval/bin/python scripts/evaluate_davis_masks.py \
  --ground-truth-dir data/raw/davis2017/trainval-crossing/DAVIS/Annotations/480p/crossing \
  --prediction-dir outputs/tasks/davis-crossing-person-001/masks \
  --object-id 1 --sequence crossing \
  --output outputs/tasks/davis-crossing-person-001/davis-metrics.json
```

## 实际结果

| 项目 | 实测 |
| --- | ---: |
| 保存掩码 / 叠加帧 | 52 / 52 |
| 首帧 IoU | 0.8750 |
| 官方 DAVIS J（中间 50 帧） | 0.9164 |
| 官方 DAVIS F（中间 50 帧） | 0.9873 |
| 官方 DAVIS J&F（中间 50 帧） | 0.9519 |
| 推理时间 | 8.5690 秒 |
| 推理速度（含状态初始化） | 6.0684 FPS |
| 峰值 CUDA 分配 | 602,774,016 字节 |
| 连续 3 帧空掩码后重现触发 | 0 次 |

人工查看首帧、第 25 帧和末帧叠加图，掩码保持在同一名深色衣服行人上。首帧 IoU 超过预定的 0.7 门槛。由于 52 帧模型掩码均非空，本序列无法验证真实目标重现时保护规则是否误拦；结果状态是 `inconclusive_no_reactivation_event`，不是“误拦截率为 0”。J/F 数值仅对应这一个行人实例和这组固定提示，不代表行人类别总体性能。

## 问题与限制

- 官方 ZIP 的逐文件 Range 下载在 40 多个文件后出现一次 `SSL: UNEXPECTED_EOF_WHILE_READING`；脚本加入有限重试并从已下载文件续传，最终 104 个文件完整。
- SAM2 可选 `_C` 扩展仍缺失，运行时跳过填洞后处理；核心推理成功。
- 片段含部分遮挡与邻近目标，但未出现本规则所需的连续空掩码。真实重现误拦截问题仍需另选有明确事件的交通素材。
- 该片段的原视频在 DAVIS `SOURCES.md` 中有单独来源，公开展示前仍需复核来源条款。

## 本地证据

- `outputs/tasks/davis-crossing-person-001/result.json`
- `outputs/tasks/davis-crossing-person-001/guard-audit.json`
- `outputs/tasks/davis-crossing-person-001/davis-metrics.json`
- `outputs/tasks/davis-crossing-person-001/overlays/`

原始媒体、真值、掩码和叠加图均不上传 Git。
