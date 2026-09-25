# DEV-28：自行车与骑行者的遮挡诊断

- 日期：2026-09-25
- 基于提交：`d0aeca8`；本记录、提示配置和评价器修复随同一次提交归档
- 结果：80 帧双目标传播完成；自行车未通过首帧门槛，骑行者通过。保留失败，不改点重跑

## 这次想解决什么

DEV-27 没有找到合格的城市道路非机动车真值样本。不过，独立骑行小径上的树木遮挡、细车架和轮圈仍能检验工具的实际弱点。因此在推理前另行冻结了“自行车道遮挡诊断”合同，见 `docs/research/quality-pilot.md`。这不改变 DEV-27 的城市道路筛选结论，也不算补齐城市混合交通评估。

使用 DAVIS 2017 验证集 `bmx-trees` 全部 80 帧，两个实例分别为自行车和骑行者。每对象固定 3 个正点、1 个负点，在推理前用首帧 GT 核对标签。这是有真值辅助的提示，不是用户盲点选试验。只运行一次 SAM2，不训练、不加后处理、不做中途修正。

## 输入与环境

| 项目 | 实际记录 |
| --- | --- |
| 数据 | 80 张 RGB、80 张实例 GT，854×480，共 10,090,841 字节 |
| 帧名 | `00000` 至 `00079`，连续且 RGB/GT 一一对应 |
| GT 标签 | 0、1、2；没有 255 void；两个对象在全部 80 帧均有非空标注 |
| 文件集合摘要 SHA-256 | `97778e38e18a5e50ee488b5c411ef9afab616d5b4f4898cff6a4f9855a7c0286` |
| Python / PyTorch | WSL Ubuntu 24.04，Python 3.12.3，PyTorch 2.11.0+cu128，CUDA runtime 12.8 |
| GPU | NVIDIA GeForce RTX 5060 Laptop GPU |
| SAM2 | SAM-2 包 1.0，SAM2.1 Hiera Tiny；源码提交 `2b90b9f5ceec907a1c18123530e92e794ad901a4` |
| 模型配置 | `configs/sam2.1/sam2.1_hiera_t.yaml`，Torch seed=0 |
| 权重 SHA-256 | `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69` |
| 评价器 | 官方 `davis2017` 0.1.0 的 J/F 函数，独立评价环境；中间 78 帧计主端点 |

文件集合摘要的计算方法：从 `data/raw/davis2017/trainval-bmx-trees` 起按相对路径排序，逐文件计算 SHA-256，再将每行 `相对POSIX路径\t文件SHA256\n` 拼接为 UTF-8 字节后计算 SHA-256。原始媒体与标注留在本地，来源和使用范围见 `docs/research/data-sources.md` 的 `davis-005-bmx-trees`。

## 复现命令

以下在项目根目录的 WSL Bash 中执行。推理脚本拒绝覆盖已有输出；复现时使用新的任务目录名，不删除已有实验。

```bash
cd /mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS
APP_PY=/home/clickvos/.venvs/clickvos/bin/python
EVAL_PY=/home/clickvos/.venvs/davis-eval/bin/python
DATA=data/raw/davis2017/trainval-bmx-trees/DAVIS
RUN=outputs/tasks/davis-bmx-trees-two-objects-001

"$APP_PY" scripts/fetch_davis_sequence.py \
  --sequence bmx-trees --output-root data/raw/davis2017/trainval-bmx-trees
"$APP_PY" scripts/run_sam2_multi_frames.py \
  --frames-dir "$DATA/JPEGImages/480p/bmx-trees" \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  --prompt-config configs/experiments/davis-bmx-trees-two-objects.json \
  --output "$RUN" --seed 0

for id in 1 2; do
  object_dir=$(printf 'object_%03d' "$id")
  for mode in main endpoints; do
    extra=()
    report=davis-metrics.json
    if [ "$mode" = endpoints ]; then
      extra=(--include-endpoints)
      report=endpoint-metrics.json
    fi
    "$EVAL_PY" scripts/evaluate_davis_masks.py \
      --ground-truth-dir "$DATA/Annotations/480p/bmx-trees" \
      --prediction-dir "$RUN/$object_dir/masks" \
      --object-id "$id" --sequence bmx-trees "${extra[@]}" \
      --output "$RUN/$object_dir/$report"
  done
  "$APP_PY" scripts/evaluate_reactivation_guard.py \
    --ground-truth-dir "$DATA/Annotations/480p/bmx-trees" \
    --prediction-dir "$RUN/$object_dir/masks" \
    --object-id "$id" --minimum-empty-frames 3 \
    --output "$RUN/$object_dir/guard-audit.json"
done

ffmpeg -n -v error \
  -framerate 10 -i "$RUN/object_001/overlays/%05d.jpg" \
  -framerate 10 -i "$RUN/object_002/overlays/%05d.jpg" \
  -filter_complex hstack=inputs=2 -vcodec libx264 -crf 20 \
  -pix_fmt yuv420p -movflags +faststart "$RUN/bicycle-rider-preview.mp4"
ffprobe -v error -count_frames \
  -show_entries stream=width,height,nb_read_frames,r_frame_rate:format=duration,size \
  -of json "$RUN/bicycle-rider-preview.mp4"
```

## 实测结果

预先约定：首帧 IoU 至少 0.7，才能把该对象后续 J/F 作为通过初始提示门槛的质量结果。

| 对象 | 保存掩码 | 首帧 IoU | 门槛 | 中间 78 帧 J | F | J&F | J<0.5 帧数 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| ID 1，自行车 | 80 | 0.6427 | 未通过，后续仅作失败诊断 | 0.5516 | 0.9204 | 0.7360 | 20 |
| ID 2，骑行者 | 80 | 0.8785 | 通过 | 0.7759 | 0.9487 | 0.8623 | 7 |

不汇总两对象为一个“通过成绩”。骑行者属于这条骑行场景中的人，不算新增独立行人场景。

- 联合推理及图片输出耗时 22.506393951 秒，80 帧对应 3.55454544 FPS。包含会话初始化、提示、传播及保存，不含模型加载和后续评价/视频编码；不是纯模型 FPS。
- 模型加载 1.392642305 秒；峰值 CUDA 分配 649,034,240 字节，不等于进程总显存。
- 人工检查两个对象的第 0、40、79 帧，并分别检查最低 J 的第 61、68 帧；帧号从 0 开始。
- 自行车最低 J 在 `00061.png`：0.1884；骑行者最低 J 在 `00068.png`：0.3448。
- 两对象均无空预测掩码。保护规则触发、抑制帧数均为 0；自行车审计状态为 `invalid_initial_prompt`，骑行者为 `inconclusive_no_reactivation_event`。不能将此写成零误报率。

### 画面与像素核对

自行车首帧的叠加图覆盖了部分轮圈内部和车架空隙中的背景，同时漏掉部分细结构。像素核对显示 GT 为 6,466 像素，预测为 7,165，正确覆盖 5,333，误覆盖 1,832，漏分 1,133。这解释了为何画面“大致像自行车”，首帧 IoU 仍未达标。

第 61 帧自行车经过枝叶和树干附近时，预测相对可见真值有明显误覆盖：GT 426 像素，预测 1,214，误覆盖 954，漏分 166。第 68 帧骑行者被前景大树干遮挡，只剩部分身体可见；GT 429 像素，预测 784，误覆盖 473，漏分 118。这些是局部遮挡/边界误差，不能据此认定身份切换或完全离场。

预览为左侧自行车、右侧骑行者，1708×480、80 帧、8 秒。10 FPS 仅为人工复核播放速度，不代表原视频采样频率，也不是推理速度。

## 同步修复评价器

`scripts/evaluate_davis_masks.py` 新增全序列输入检查：拒绝不存在的对象 ID、背景/void ID、空评价区间、文件名不一致、尺寸不匹配、多通道或非二值预测。合法的单帧目标缺席仍可评价。失败时不覆盖已有报告，也不输出 NaN 成绩。

GT 中的 255 显式作为 `void_pixels` 传给官方 J/F 函数。需注意：官方函数支持此参数，但其半监督顶层入口并不采用完全相同的 void 传参；本项目报告会写出 `void_policy`。本次 `bmx-trees` 和已有 `crossing` 都没有 void，旧分数不受影响。

```bash
"$APP_PY" -m pytest -q
"$APP_PY" scripts/check_repository.py
```

完整测试实际为 `91 passed in 7.59s`，其中新增评价器测试 24 项。仓库检查通过，共 18 份结果摘要，没有跟踪模型或视频。另用真实官方评价环境重新计算 `crossing` 三对象各两种端点设置，共六份报告：此前所有字段（含逐帧 J/F）逐值相同，只新增 void 策略字段；没有重跑 GPU 或覆盖旧报告。

可在 WSL 项目根目录重做这个 CPU 回归比较，不写入旧报告：

```bash
"$EVAL_PY" - <<'PY'
import json
from pathlib import Path
from scripts.evaluate_davis_masks import evaluate_davis_masks

gt = Path('data/raw/davis2017/trainval-crossing/DAVIS/Annotations/480p/crossing')
for object_id in [1, 2, 3]:
    obj = Path(f'outputs/tasks/davis-crossing-three-objects-001/object_{object_id:03d}')
    for endpoints in [False, True]:
        name = 'endpoint-metrics.json' if endpoints else 'davis-metrics.json'
        previous = json.loads((obj / name).read_text())
        current = evaluate_davis_masks(gt, obj / 'masks', object_id, 'crossing', include_endpoints=endpoints)
        assert all(current[key] == value for key, value in previous.items())
        print(object_id, endpoints, current['mean_j_and_f'], 'all_previous_fields_equal')
PY
```

## 问题与下一步

- SAM2 可选 `_C` 扩展仍不可用，跳过填洞后处理；核心传播完成。
- 记录 seed=0 是为了复现配置，未启用严格确定性 CUDA 算法，不承诺跨硬件逐位一致。
- 一条自行车小径不能代表城市混合交通，城市道路非机动车真值仍缺；十人试用、Docker 实机构建、云部署仍未完成。
- BDD100K 官方下载文档另列 ETH 镜像，但本机访问也遇到 TLS 握手错误；没有下载数据，见素材登记表。
- Windows 直接转发带复杂标签的 FFmpeg 滤镜曾发生参数解析错误；改用 `wsl --exec ffmpeg` 和上面的简单并排滤镜后成功，不影响已有模型结果。
- 下一轮优先做首帧交互修正：为轮圈/车架空隙添加背景负点，先验证首帧，再决定是否传播。另行冻结预算和评价方式，不能把本轮不通过的结果改写成成功。本轮没有执行这项修正。

本地结果在 `outputs/tasks/davis-bmx-trees-two-objects-001/`：`result.json`、逐对象掩码/叠加图、四份 J/F 报告、两份保护审计和预览视频。仓库仅提交提示、代码、测试与摘要 `docs/research/results/dev28-bmx-trees-occlusion-diagnostic.json`，不提交原始媒体、GT 或生成图像。
