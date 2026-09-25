# 测试数据来源登记

所有素材在使用前登记来源、许可证和用途。原始媒体、处理后视频及运行产物不提交 Git。

## traffic-001

| 字段 | 记录 |
| --- | --- |
| 文件名 | `Avtocesta.webm` |
| 来源页面 | `https://commons.wikimedia.org/wiki/File:Avtocesta.webm` |
| 原文件地址 | `https://upload.wikimedia.org/wikipedia/commons/6/68/Avtocesta.webm` |
| 作者 | idioterna |
| 许可证 | Creative Commons Attribution 3.0，CC BY 3.0 |
| 许可证地址 | `https://creativecommons.org/licenses/by/3.0` |
| Commons 许可状态 | 来源页面标记为外部来源许可已复核 |
| 原始内容 | 夜间高速公路交通，固定机位，车辆驶入和驶出画面 |
| 原始规格 | VP8 WebM，1920×1080，30 FPS，22.131 秒，10,276,506 字节 |
| 原文件 SHA-256 | `4177A9703553FA3AA67ACBF0CFAAB99B4C8DF360C042A3A26430BD47D2587873` |
| 本项目用途 | CP-02 交通视频传播和失败案例验证 |
| 本地裁剪 | 起始 0 秒，时长 5 秒，960×540，10 FPS，H.264 MP4 |
| 裁剪文件 SHA-256 | `1669f9bee08e29f4e57405f6d5bdd2114501e124236d676167dd26e19ffbf412` |

署名说明：原视频 `Avtocesta` 由 Wikimedia Commons 用户 idioterna 发布，采用 CC BY 3.0。项目报告、演示或公开结果中使用该素材时必须保留作者、来源页面和许可证链接。

## traffic-002

| 字段 | 记录 |
| --- | --- |
| 文件名 | `People waiting to cross the street.webm` |
| 类别 | 行人 |
| 来源页面 | `https://commons.wikimedia.org/wiki/File:People_waiting_to_cross_the_street.webm` |
| 原文件地址 | `https://upload.wikimedia.org/wikipedia/commons/d/d2/People_waiting_to_cross_the_street.webm` |
| 作者 | Amada44 |
| 许可证 | CC BY-SA 3.0 |
| 来源状态 | 上传者原创；2026-09-21 下载并核验页面信息 |
| 原始规格 | 15.467 秒，1280×720，31,210,739 字节 |
| 原文件 SHA-1 | `635373fdb0ccb21b9bd716666893faee18598669`（与 Commons 页面一致） |
| 原文件 SHA-256 | `df6ef7dfbd4033f639d8cebd71cb5af50706b7cc8eb91bc3c836d0c15aeb21ad` |
| 本地裁剪 | 起始 0 秒，时长 5 秒，960×540，10 FPS，H.264 MP4 |
| 裁剪文件 SHA-256 | `461c2fed7d2913100c19d68fe2ec6a958c44498194ed863533eaeada12b7169f` |
| 本项目用途 | 行人类别真实 GPU 回归；无逐帧真值，不计算 J、F 或 IoU |

署名说明：原视频由 Wikimedia Commons 用户 Amada44 发布，采用 CC BY-SA 3.0。公开展示裁剪或叠加结果时保留作者、来源页面、许可证链接，并按相同许可要求处理派生媒体。

## traffic-003

| 字段 | 记录 |
| --- | --- |
| 文件名 | `Dostawca jedzenia i licznik rowerowy w działaniu w Katowicach na ulicy Korfantego.webm` |
| 类别 | 非机动车（骑行者与自行车） |
| 来源页面 | `https://commons.wikimedia.org/wiki/File:Dostawca_jedzenia_i_licznik_rowerowy_w_działaniu_w_Katowicach_na_ulicy_Korfantego.webm` |
| 原文件地址 | `https://upload.wikimedia.org/wikipedia/commons/3/37/Dostawca_jedzenia_i_licznik_rowerowy_w_dzia%C5%82aniu_w_Katowicach_na_ulicy_Korfantego.webm` |
| 作者 | Krzysztof Popławski |
| 许可证 | CC BY-SA 4.0 |
| 来源状态 | 上传者原创；2026-09-21 下载并核验页面信息 |
| 原始规格 | 3.373 秒，720×1280，2,740,611 字节 |
| 原文件 SHA-1 | `a311f8f3d1bf9321fed32747020bb42c1efc2c32`（与 Commons 页面一致） |
| 原文件 SHA-256 | `da9a71b6cafdbb12180f8c913e45b86914c5f1ad60dd13b57b1d9466a33b1404` |
| 本地裁剪 | 起始 0.5 秒，时长 2.8 秒，540×960，10 FPS，H.264 MP4 |
| 裁剪文件 SHA-256 | `8cab22e1e0faad0ccefb2c9b7802517410fca18912c27a0fe3be9cb78441a969` |
| 本项目用途 | 非机动车类别真实 GPU 回归；无逐帧真值，不计算 J、F 或 IoU |

署名说明：原视频由 Wikimedia Commons 用户 Krzysztof Popławski 发布，采用 CC BY-SA 4.0。公开展示裁剪或叠加结果时保留作者、来源页面、许可证链接，并按相同许可要求处理派生媒体。

## davis-001-bike-packing

| 字段 | 记录 |
| --- | --- |
| 数据集 | DAVIS 2017 train/val 480p，`bike-packing` 序列 |
| 官方下载页 | `https://davischallenge.org/davis2017/code.html` |
| 官方压缩包 | `https://data.vision.ee.ethz.ch/csergi/share/davis/DAVIS-2017-trainval-480p.zip` |
| 获取方式 | 2026-09-21 使用 HTTP Range 只提取本序列的 69 张图像和 69 张真值掩码，共 12,937,993 字节 |
| 标注对象 | 对象 1：bicycle；对象 2：person |
| 数据许可 | 压缩包 `DAVIS/README.md` 的 Terms of Use 为 CC BY-NC 4.0；`SOURCES.md` 另列原视频来源，仍需遵守来源条款 |
| 原视频来源 | `https://www.youtube.com/watch?v=2JMcuDkvX8I`（由压缩包 `SOURCES.md` 给出） |
| 评估实现 | 官方 `davis2017-evaluation`，提交 `ac7c43fca936f9722837b7fbd337d284ba37004b` |
| 本项目用途 | 仅用于非商业研究的指标流水线验证，不作为交通场景证据，不随软件或 Git 仓库分发 |

该序列包含自行车，但首段是室内维护场景。因此它可以验证 SAM2 输出与 DAVIS J/F 指标链路，不能据此宣称已经完成“公开交通数据子集”的完整定量评估。

## davis-002-car-roundabout

| 字段 | 记录 |
| --- | --- |
| 数据集 | DAVIS 2017 train/val 480p，验证集 `car-roundabout` 序列 |
| 官方下载页 | `https://davischallenge.org/davis2017/code.html` |
| 官方压缩包 | `https://data.vision.ee.ethz.ch/csergi/share/davis/DAVIS-2017-trainval-480p.zip` |
| 获取方式 | 2026-09-21 使用 HTTP Range 只提取本序列的 75 张图像和 75 张真值掩码，共 9,722,493 字节 |
| 文件集合清单 SHA-256 | `4236e1c7bdad7c99087adb8e97c4d45feca391264ddae35ff691749ecb77ff6d` |
| 标注对象 | 对象 1：car |
| 场景 | 白天城市环岛，目标车辆由侧面驶向远处，背景包含多辆相似车辆 |
| 数据许可 | 压缩包 `DAVIS/README.md` 的 Terms of Use 为 CC BY-NC 4.0；`SOURCES.md` 未为该序列另列外部来源 |
| 评估实现 | 官方 `davis2017-evaluation`，提交 `ac7c43fca936f9722837b7fbd337d284ba37004b` |
| 本项目用途 | 非商业研究的道路交通首帧提示对照实验；不随软件或 Git 仓库分发 |

该序列满足“道路交通画面、逐帧实例真值、目标身份连续”的小样本评估条件。它只包含单个车辆对象，尚不能覆盖行人、非机动车、严重遮挡或多目标交互。

## davis-003-crossing

| 字段 | 记录 |
| --- | --- |
| 数据集 | DAVIS 2017 train/val 480p，`crossing` 序列 |
| 官方下载页 | `https://davischallenge.org/davis2017/code.html` |
| 官方压缩包 | `https://data.vision.ee.ethz.ch/csergi/share/davis/DAVIS-2017-trainval-480p.zip` |
| 获取方式 | 2026-09-23 用 `remotezip==0.12.6` 和 `scripts/fetch_davis_sequence.py` 按 HTTP Range 提取本序列；52 张 RGB 帧与 52 张实例真值完整，854×480，文件合计 10,003,414 字节 |
| 标注对象 | 对象 1、2：行人；对象 3：货车。本轮固定对象 1，即首帧右侧深色衣服行人 |
| 场景 | 城市道路斑马线，两个行人过街，货车和其他车辆在画面中 |
| 数据许可 | 压缩包 `DAVIS/README.md` 的 Terms of Use 为 CC BY-NC 4.0；仅用于本项目非商业研究，不随软件或 Git 仓库分发 |
| 原视频来源 | 压缩包 `DAVIS/SOURCES.md` 为 `crossing` 列出 `https://www.youtube.com/watch?v=YzpkoPGclas`；公开再利用时还需核对原视频来源条款 |
| 本项目用途 | 道路行人逐帧真值质量验证，以及重新激活保护触发条件筛查 |

本序列的同一目标在本轮 SAM2 传播中没有连续空掩码，因此不能用于估计保护规则的误拦截率。

## kitti-mots-annotations-001（只做候选筛选）

| 字段 | 记录 |
| --- | --- |
| 数据集 | KITTI MOTS 官方 train+val TXT 实例标注 |
| 官方项目页 | `https://www.vision.rwth-aachen.de/page/mots` |
| 标注包 | `https://www.vision.rwth-aachen.de/media/resource_files/instances_txt.zip` |
| 获取方式 | 2026-09-23 下载 4,080,394 字节的官方 ZIP，仅本地保存于 `data/raw/kitti-mots/` |
| SHA-256 | `d11c35401be1885d79111f363f861339c733355a776fcd2d9fd095274212049c` |
| 标注许可 | 项目页注明 CC BY-NC-SA 3.0；非商业研究使用，注明来源，不随代码分发 |
| 图像状态 | 尚未下载；原 KITTI 图像网站要求用户注册并说明用途，项目不绕过该要求 |
| 图像许可 | KITTI 官网 `https://www.cvlibs.net/datasets/kitti/` 标明 CC BY-NC-SA 3.0、仅限学术用途；图像下载政策见 `https://www.cvlibs.net/datasets/kitti/user_login.php` |
| 本项目用途 | 只筛选同一对象 ID 的内部无标注区间；不据此认定物理遮挡或 SAM2 误拦截 |

官方页说明对象 ID 在时间上保持一致，类别 1 为车辆、2 为行人。没有图像复核和模型输出时，TXT 的缺席区间仅是后续人工核查候选。2026-09-23 核对图像使用条件后，因尚无项目成员以本人账号完成 KITTI 注册，本项目不获取图像，也不把标注缺席解释为真实遮挡。

## 已拒绝候选

### davis-004-candidate-screen（2026-09-25）

| 字段 | 记录 |
| --- | --- |
| 官方来源 | <https://davischallenge.org/davis2017/code.html>，DAVIS 2017 train/val 480p 压缩包 |
| 语义依据 | 官方 Object categories 包中的 `davis_semantics.json`，本地已核对 bicycle、person、motorcycle ID |
| 获取方式 | 通过 `scripts/fetch_davis_sequence.py` 按 HTTP Range 只取各候选首、中、末三张 RGB 和同名实例真值 |
| 成功样本 | `bmx-trees`：0/40/79；`longboard`：0/26/51；`scooter-black`：0/21/42；共 18 个文件、1,295,157 字节，只在本地保存 |
| 未取得样本 | `bike-trial` 不在本次官方 train/val 480p 包的 JPEGImages 列表内 |
| 许可 | 包内 README 写明 CC BY-NC 4.0，原视频条款另需复核；不上传原始媒体和真值 |
| 筛选结论 | 前两条画面不属于道路交通；后一条属于城市道路，但踏板车是机动车；均不能填补道路非机动车真值缺口 |

画面、标签抽样核查与完整命令见 `docs/checkpoints/DEV-27-nonmotor-gt-source-screen.md`。这是素材筛选，不是新的 J/F 实验。

### bdd100k-candidate（仅来源核查，2026-09-25）

| 字段 | 记录 |
| --- | --- |
| 官方类别与标注格式 | <https://github.com/bdd100k/bdd100k/blob/master/doc/source/format.rst>；bicycle 属于分割跟踪的八类对象，文档描述逐帧实例掩码与 ID |
| 官方数据许可 | <https://github.com/bdd100k/bdd100k/blob/master/doc/source/license.rst>；教育、研究及非营利许可用途与代码仓库的 BSD 许可不同 |
| 官方数据站 | <https://bdd-data.berkeley.edu/>；2026-09-25 在 Windows 和 WSL 均遇到 TLS 证书主机名不匹配，网页抓取为 502 |
| 使用状态 | 未下载任何 BDD100K 数据，未确认某条视频确有可用自行车实例；不会绕过证书校验或访问政策 |

若后续能通过可信官方入口获取数据，还需先核对视频、标注相互对应及具体使用条件，再决定是否作为道路非机动车小样本。


### traffic-candidate-rejected-firstperson-bike

| 字段 | 记录 |
| --- | --- |
| 文件名 | `What Bike Lane.webm` |
| 类别 | 非机动车（骑行者） |
| 来源页面 | `https://commons.wikimedia.org/wiki/File:What_Bike_Lane.webm` |
| 作者 | idioterna |
| 许可证 | CC BY 3.0 |
| 来源状态 | 外部来源许可于 2016-02-23 经 Wikimedia 审核 |
| 页面规格 | 25 秒，1920×1080，约 14.67 MB |
| 原文件 SHA-1 | `233669a4058e1808803893596fbd920807959642`（与 Commons 页面一致） |
| 原文件 SHA-256 | `3afbbfbd0ad124d776839b3f439e1876718fa4d53c17cabbeb7bef0bf486cef3` |
| 使用状态 | 2026-09-21 下载并人工检查后拒绝；第一视角骑行，缺少稳定、完整的外部自行车目标，不进入实验结果 |

候选筛选规则：许可必须允许项目使用和必要裁剪；来源页面必须能核验作者与许可；排除暴力事故、隐私导向内容和许可待复核素材。视频中即使包含公共场景人物，也只用于交通目标分割，不做人脸识别、身份推断或个人信息处理。
