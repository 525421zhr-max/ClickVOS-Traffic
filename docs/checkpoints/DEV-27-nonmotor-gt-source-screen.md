# DEV-27：道路非机动车真值素材筛选

- 日期：2026-09-25
- 状态：三条 DAVIS 候选完成抽样核查，均未进入道路非机动车定量评估；未运行 SAM2

## 目的与筛选标准

DEV-26 已有道路车辆和行人真值，但缺带逐帧实例真值的道路非机动车。本轮按事先写入 `docs/research/quality-pilot.md` 的筛选合同，只核对候选素材是否同时具备：明确来源与使用条件、道路交通画面、自行车或骑行者目标、同名 RGB/实例真值。未达到标准者不计算 J/F，也不改称“道路非机动车”。

## 来源与复现

- DAVIS 官方下载与 480p 评价说明：<https://davischallenge.org/davis2017/code.html>
- 数据：DAVIS 2017 train/val 480p 官方压缩包；许可按包内 README 的 CC BY-NC 4.0 和各原视频来源条款执行，原始媒体不公开分发。
- 语义候选：已有官方语义包 `data/raw/davis2017/semantics-480p/DAVIS/davis_semantics.json`。
- 环境：WSL Ubuntu 24.04，Python 3.12.3，现有项目虚拟环境含 `remotezip`、Pillow。本轮只下载抽样 RGB/真值，不用 GPU。

```bash
cd /mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS
PY=/home/clickvos/.venvs/clickvos/bin/python
$PY scripts/fetch_davis_sequence.py --sequence bmx-trees \
  --output-root data/raw/davis2017/screen-20260925 --frame 0 --frame 40 --frame 79
$PY scripts/fetch_davis_sequence.py --sequence longboard \
  --output-root data/raw/davis2017/screen-20260925 --frame 0 --frame 26 --frame 51
$PY scripts/fetch_davis_sequence.py --sequence scooter-black \
  --output-root data/raw/davis2017/screen-20260925 --frame 0 --frame 21 --frame 42
```

另尝试对 `bike-trial` 抽取第 0、20、40 帧，脚本回报 `sequence not found in official archive: bike-trial/JPEGImages`；没有绕过官方压缩包去取未知来源的副本。成功抽取三条候选各 3 张 RGB 与 3 张同名实例真值，共 18 个文件、1,295,157 字节，均只在本地 `data/raw/` 下。Pillow 读取的抽样真值标签：`bmx-trees` 三帧均有 1、2；`longboard` 前两帧有 1–5，末帧只有 1、4；`scooter-black` 三帧均有 1、2。该标签检查只验证文件内容与 ID，不能替代完整序列的标注质量审查。

| 候选 | 抽样画面与标注 | 判定 |
| --- | --- | --- |
| `bmx-trees` | 骑行者在独立小径、草地和涂鸦墙旁骑行；自行车和人有实例标签 | 可作自行车分割技术样本，但不是道路交通片段，本轮拒绝 |
| `longboard` | 林间步道上的滑板者与远处骑行者；末帧抽样已无自行车 ID 2/3 | 不是城市道路交通，且自行车目标并非稳定主目标，本轮拒绝 |
| `scooter-black` | 城市道路上有骑乘者和踏板车，真值标签为 person、motorcycle | 道路场景成立，但踏板车是机动车类别，不能充当非机动车，本轮拒绝 |
| `bike-trial` | 官方 train/val 480p 包内找不到该序列 | 未获得样本，不作画面或标注结论 |

## 后续来源核查与障碍

BDD100K 官方标注格式包含 bicycle，且分割跟踪任务有实例掩码/跨帧 ID；官方数据许可允许教育、研究及非营利用途，但与代码仓库 BSD 许可不同。参见 <https://github.com/bdd100k/bdd100k/blob/master/doc/source/format.rst> 和 <https://github.com/bdd100k/bdd100k/blob/master/doc/source/license.rst>。2026-09-25 从 Windows 与 WSL 对 `https://bdd-data.berkeley.edu/` 做证书校验，均返回主机名不匹配（`SEC_E_WRONG_PRINCIPAL` / `SSL: no alternative certificate subject name matches target host name`）；网页抓取还返回 502。未关闭证书校验、未下载 BDD 数据，也未核对具体可用视频。

结论：**道路非机动车逐帧真值仍缺失**，本轮没有新增质量指标。下一步需取得来源可靠、能安全访问的 BDD100K 视频与分割跟踪标注，或继续寻找更小且许可清楚的道路自行车实例视频；先筛画面与目标 ID，再冻结一次小规模 GPU 合同。不把 DAVIS 林间骑行或道路机动踏板车改名计入该类。
