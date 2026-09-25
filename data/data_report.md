# 数据与素材汇编记录

更新日期：2026-09-25

本轮目标是补齐车辆、行人、非机动车三类真实素材，并建立一条带逐帧真值的 J/F 评估链路。原始视频、裁剪、帧、掩码和运行日志均由 `.gitignore` 排除；这里仅保留来源、许可、哈希、筛选结论和可复现位置。

| ID | 用途 | 许可与状态 | 实际结果 |
| --- | --- | --- | --- |
| `traffic-001` | 车辆交通回归 | Wikimedia Commons，CC BY 3.0 | 已保留 CP-02 离场后错误重激活案例 |
| `traffic-002` | 行人交通回归 | Wikimedia Commons，CC BY-SA 3.0 | 50 帧真实 GPU 传播；无真值，不报告精度 |
| `traffic-003` | 非机动车交通回归 | Wikimedia Commons，CC BY-SA 4.0 | 28 帧真实 GPU 传播；无真值，不报告精度 |
| `davis-001-bike-packing` | 官方 J/F 流水线 | DAVIS 包 README：CC BY-NC 4.0，另需遵守原视频条款 | 69 帧自行车对象传播，评估中间 67 帧；非交通场景，仅作指标验证 |
| `davis-002-car-roundabout` | 道路交通定量基线 | DAVIS 2017 验证集，包 README：CC BY-NC 4.0 | 75 帧车辆真值；完成单点局部选择与多点整车选择对照 |
| `davis-003-crossing` | 道路行人真值与保护规则筛查 | DAVIS 2017 train/val，包 README：CC BY-NC 4.0；原视频来源另列于 SOURCES.md | 52 帧完整传播；中间 50 帧 J&F=0.9519；没有重新激活事件，误拦截问题信息不足 |
| `traffic-candidate-rejected-firstperson-bike` | 候选筛选 | Wikimedia Commons，CC BY 3.0 | 第一视角且没有稳定完整目标，拒绝进入实验 |
| `davis-004-candidate-screen` | 道路非机动车真值候选 | DAVIS train/val，CC BY-NC 4.0；原视频条款另核 | `bmx-trees`、`longboard`、`scooter-black` 各抽样 3 帧及真值；前两条不是道路交通，后一条是机动车；未运行 SAM2 |
| `davis-005-bmx-trees` | 自行车道遮挡诊断 | DAVIS 验证集，CC BY-NC 4.0；原始媒体仅本地 | 另行冻结合同后完成 80 帧双目标传播；自行车首帧 IoU=0.6427 未通过门槛，骑行者首帧通过、中间 78 帧 J&F=0.8623 |
| `bdd100k-candidate` | 道路自行车真值候选 | 官方数据许可限教育、研究、非营利等许可用途 | 标注格式有 bicycle 和跨帧实例；主站证书不匹配，官方列出的 ETH 镜像也遇 TLS 握手失败，未取得数据 |

详细 URL、作者、哈希、裁剪参数和署名要求见 `docs/research/data-sources.md`。本轮素材均为公开授权内容，没有使用私人照片，也不进行人脸识别、身份推断或与分割任务无关的个人信息处理。

## 覆盖与缺口

- 三个产品目标类别均已有至少一个真实公开视频回归样本。
- Wikimedia Commons 的行人和非机动车回归样本没有逐帧真值；`crossing` 另提供一条有真值的道路行人序列。
- DAVIS `car-roundabout` 已提供第一条带逐帧真值的道路交通车辆基线。
- 仍需补充带真值的道路非机动车，以及真实消失后重现的交通案例；现有车辆和行人单序列结果都不能外推到类别总体性能。
- 2026-09-25 的 DAVIS 候选筛选详见 `docs/checkpoints/DEV-27-nonmotor-gt-source-screen.md`。筛选样本不等于新增分割实验或道路非机动车覆盖。
- 同日另以自行车道诊断范围完成 DEV-28：`bmx-trees` 全 80 帧双目标实验，保留自行车提示失败与树干遮挡问题。它能支撑工具修正测试，仍不替代城市道路非机动车真值评估。
