# DEV-29：自行车首帧背景负点修正

- 日期：2026-10-04
- 运行前合同提交：`69710f5`；基于 DEV-28 `b74770e`
- 结果：完成原点基线和 1/2/3 个累计负点的单帧验证；预算用尽，自行车仍未达到 0.7 门槛，不传播

## 这次验证了什么

DEV-28 中自行车轮圈和车架空隙有背景误覆盖。本轮保留原有 3 正点、1 负点，按提前固定的顺序添加最多 3 个背景负点，看能否改善首帧选择。骑行者提示不变，作为同场景的对象稳定性检查。

先检查了现有 Web 实现：首帧补点与撤销已经可用，但补点只在旧叠加图上标出位置，重新推理需要点击重新传播，且会覆盖同任务的全序列结果。因此没有重复实现补点 UI，也没有把旧任务交给重传播入口，而是新增 `scripts/verify_first_frame_negative_correction.py`，复用已有 `Sam2Engine` 和掩码保存函数。

新脚本只复制 `00000.jpg` 到隔离目录，每阶段分别新建会话、一次传入每个对象的完整点集。SAM2 会按目录枚举帧，直接将原目录的帧列表切成一张仍会加载全部帧；同一会话重复补点又会使用旧掩码 logits，因此两者都不能替代这次独立单帧对照。模型只加载一次，全程没有调用传播。

## 冻结提示与预算

合同见 `docs/research/quality-pilot.md`，配置见 `configs/experiments/davis-bmx-trees-first-frame-negative.json`，二者在推理前提交。

| 阶段 | 本次新增负点 | 自行车累计修正点击数 | 自行车总点数 |
| --- | --- | ---: | ---: |
| 0 | 无，复现原提示 | 0 | 4 |
| 1 | `(533,292)`，前轮区域 | 1 | 5 |
| 2 | `(415,317)`，后轮/车架空隙 | 2 | 6 |
| 3 | `(475,282)`，车架空隙 | 3 | 7 |

三个点是在查看原 RGB 和 DEV-28 叠加图后，借助首帧真值和旧误覆盖区域确定的；具体区域与距离变换选点规则保存在配置中。新推理前逐点确认 GT=0 且旧掩码误覆盖。这属于真值辅助修正，不是用户盲点选或十人试用记录。

最多 4 个单帧会话，总进程上限 300 秒，seed=0。每阶段检查两对象 IoU；首次均达到 0.7 即停止，否则用尽 3 点后停止。原点基线与 DEV-28 的 IoU 容差是 0.01，实际两个对象均逐像素完全一致，因此基线可比性检查通过。

## 实测结果

| 累计新增负点 | 自行车 IoU | 误覆盖 FP | 漏分 FN | 正确覆盖 TP | 骑行者 IoU |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0.642685 | 1,832 | 1,133 | 5,333 | 0.878541 |
| 1 | 0.660790 | 1,361 | 1,294 | 5,172 | 0.878541 |
| 2 | 0.656267 | 938 | 1,607 | 4,859 | 0.878541 |
| 3 | 0.645135 | 934 | 1,692 | 4,774 | 0.878541 |

自行车 GT 始终为 6,466 像素。1 个负点有小幅改善，但仍未达标；继续加负点后，误覆盖继续减少，同时更多真实细结构丢失。最终比原点少了 898 个误覆盖像素，却多了 559 个漏分像素，IoU 只提高约 0.00245。不能仅凭绿色覆盖变少就认为选择更准确，也不能事后挑第 1 点结果作为“通过”。

骑行者四个阶段的掩码均与 DEV-28 逐像素相同，IoU=0.8785406753。人工查看了原点、1 点和 3 点自行车叠加图；细车架/轮圈仍有漏分和误覆盖。各阶段仅保存两个对象的一张掩码，共 8 张，另有对应叠加图；没有新的视频、后续 J/F 或重新激活事件评价。

本轮结论为 `budget_exhausted`：这 3 个固定负点不能修复该例的首帧提示失败，不推断其他点法或其他视频也无效。DEV-28 原有失败记录及 80 帧结果完整保留。

## 环境和命令

实际环境仍为 WSL Ubuntu 24.04、Python 3.12.3、PyTorch 2.11.0+cu128、CUDA runtime 12.8、RTX 5060 Laptop GPU；SAM-2 包 1.0，源码提交 `2b90b9f5ceec907a1c18123530e92e794ad901a4`，SAM2.1 Hiera Tiny 配置和权重同 DEV-28。加载器实际核对权重 SHA-256 `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`。

模型加载 1.359466 秒；四阶段含会话初始化和保存分别为 1.748860、0.298754、0.255525、0.381425 秒。峰值 CUDA 分配 626,877,952 字节。这是一次单帧诊断的运行记录，不据此报告视频 FPS 或跨日期速度提升。可选 `_C` 扩展仍未启用，填洞步骤被跳过，与 DEV-28 一致。

以下为项目根目录 PowerShell 中的实际命令。复现须换一个尚不存在的输出目录；脚本拒绝覆盖结果。

```powershell
wsl -d Ubuntu-24.04 --exec timeout 300 /home/clickvos/.venvs/clickvos/bin/python scripts/verify_first_frame_negative_correction.py --frame data/raw/davis2017/trainval-bmx-trees/DAVIS/JPEGImages/480p/bmx-trees/00000.jpg --ground-truth data/raw/davis2017/trainval-bmx-trees/DAVIS/Annotations/480p/bmx-trees/00000.png --baseline-run outputs/tasks/davis-bmx-trees-two-objects-001 --experiment-config configs/experiments/davis-bmx-trees-first-frame-negative.json --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt --output outputs/tasks/davis-bmx-trees-first-frame-negative-001
wsl -d Ubuntu-24.04 --exec /home/clickvos/.venvs/clickvos/bin/python -m pytest -q
wsl -d Ubuntu-24.04 --exec /home/clickvos/.venvs/clickvos/bin/python scripts/check_repository.py
```

完整测试实际为 `107 passed in 6.25s`。新增 16 项测试验证了首帧隔离、新会话完整点集、禁止传播、门槛早停、预算耗尽、基线不匹配停止、错误输入和既有输出保护。实验脚本不依赖 SciPy；运行前选点使用已有独立 `davis-eval` 环境，没有安装新依赖。

本地完整报告为 `outputs/tasks/davis-bmx-trees-first-frame-negative-001/result.json`，逐阶段图像在 `stage_00` 至 `stage_03` 下。公开摘要为 `docs/research/results/dev29-first-frame-negative-correction.json`。只备份脚本、测试、固定提示和核对过的文档/摘要，媒体仍在本地。

## 下一步

优先给现有 Web 首帧复核增加“只更新首帧预览”的入口，并保留每次追加/撤销的点击记录，使用户能看见负点的副作用后撤销，而不必每次重跑整段视频。这个功能本轮尚未实现。再次尝试正负点组合或更多点击前另行固定方案，不因本轮未通过而自动扩大实验预算。

城市道路非机动车真值、真实连续空掩码后同目标重现、十人试用、Docker 实机构建、云部署和软著提交仍未完成。
