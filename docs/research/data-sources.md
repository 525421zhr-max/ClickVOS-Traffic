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

## 候选素材（尚未下载或用于实验）

以下条目只完成了来源页面与许可初筛。下载后必须补充原文件地址、SHA-256、实际内容检查和裁剪信息，才能转为正式实验输入。

### traffic-candidate-pedestrian-001

| 字段 | 记录 |
| --- | --- |
| 文件名 | `People waiting to cross the street.webm` |
| 类别 | 行人 |
| 来源页面 | `https://commons.wikimedia.org/wiki/File:People_waiting_to_cross_the_street.webm` |
| 作者 | Amada44 |
| 许可证 | CC BY-SA 3.0 |
| 来源状态 | 上传者原创；当前仅完成页面核验 |
| 页面规格 | 15.467 秒，1280×720，约 29.76 MB |
| 使用状态 | 候选，未下载、未运行、未报告结果 |

### traffic-candidate-nonmotor-001

| 字段 | 记录 |
| --- | --- |
| 文件名 | `What Bike Lane.webm` |
| 类别 | 非机动车（骑行者） |
| 来源页面 | `https://commons.wikimedia.org/wiki/File:What_Bike_Lane.webm` |
| 作者 | idioterna |
| 许可证 | CC BY 3.0 |
| 来源状态 | 外部来源许可于 2016-02-23 经 Wikimedia 审核 |
| 页面规格 | 25 秒，1920×1080，约 14.67 MB |
| 使用状态 | 候选，未下载、未运行、未报告结果 |

候选筛选规则：许可必须允许项目使用和必要裁剪；来源页面必须能核验作者与许可；排除暴力事故、隐私导向内容和许可待复核素材。视频中即使包含公共场景人物，也只用于交通目标分割，不做人脸识别、身份推断或个人信息处理。
