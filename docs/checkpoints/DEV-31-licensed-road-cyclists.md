# DEV-31：新增授权道路骑行素材与双目标功能测试

- 日期：2026-10-06
- 基于：`f9f7076`；开始时工作区干净。
- 状态：取得并筛选一个新视频，完成一次 30 帧双目标 GPU 功能测试；没有新增 GT 质量成绩。

## 来源与筛选

[Commons 来源页](https://commons.wikimedia.org/wiki/File:Bloody_Cyclists.webm)记录作者 idioterna、CC BY 3.0，以及 2016-02-22 对原 YouTube 来源的许可审核。原文件 42,786,147 字节、1920×1080、29.934 秒、30000/1001 FPS；本地 SHA-1 与页面一致。原片 SHA-256 为 `8ee81fdaadec916f7b109c1e954d0b22c7cc420f0f8f6e65a53346d2b18af75a`。

下载前在 `quality-pilot.md` 固定一次、50 MiB/120 秒预算；实际下载约 11 秒。按每 2.5 秒一张生成 12 格缩略图，看到公共道路路口、相邻自行车道、机动车与外部骑行者；抽样中未见事故。虽然摄像机为第一视角，画面中存在可单独选取的其他骑行者，因此不同于先前没有完整外部目标的 `What Bike Lane` 候选。这里不声称已人工逐帧审核整个原片。

固定 12–15 秒，10 FPS、960×540，共 30 帧；近处与远处骑行者的人体为对象 1/2，期望排除自行车本体。提示只看首帧 RGB，写入 `configs/experiments/traffic-004-cyclists.json` 后再推理。不能将本次人体掩码称为自行车整车分割验证。

## 实际结果

一次现有 SAM2.1 Hiera Tiny 双对象传播，seed=0，无额外后处理或补点重跑。

| 检查 | 结果 |
| --- | --- |
| 对象 1 / 对象 2 | 各 30 张掩码 |
| 帧名、尺寸、二值格式、报告面积 | 全部核对通过 |
| 空掩码帧 | 两对象均为 0 |
| 对象 1 面积范围 | 3,599–18,906 像素 |
| 对象 2 面积范围 | 1,855–5,947 像素 |
| 模型加载 | 1.3613 秒 |
| 推理及输出（含会话初始化） | 11.8058 秒，2.5411 FPS |
| 峰值 CUDA allocated | 650,166,784 字节 |

人工检查每个对象第 0、15、29 帧叠加，未见明显换到其他骑行者，人体与自行车基本分开；细边界没有真值可量化，不能据此判为质量通过。连续空掩码条件未触发，保护误拦截仍信息不足。单次速度不用于跨任务性能排名。

环境：Torch `2.11.0+cu128`、CUDA runtime `12.8`、NVIDIA GeForce RTX 5060 Laptop GPU。SAM2 源码仍为 `2b90b9f5ceec907a1c18123530e92e794ad901a4`，权重 SHA-256 `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`。可选 `_C` 扩展仍缺失，运行有相同警告，核心传播完成。

原片：`data/raw/traffic-004-candidate.webm`；帧：`data/processed/traffic-004-cyclists/`；输出：`outputs/tasks/traffic-004-two-riders-001/`。`inspection.jpg` 为两行三列复核图；`verification.json` 为逐文件核验摘要。所有媒体留在本地。

## 复现命令

在 Windows 项目根目录运行。下载和推理输出使用未占用路径，勿覆盖已有证据。

```powershell
curl.exe --fail --location --max-time 120 --max-filesize 52428800 --output data/raw/traffic-004-candidate.webm https://upload.wikimedia.org/wikipedia/commons/2/24/Bloody_Cyclists.webm
Get-FileHash data/raw/traffic-004-candidate.webm -Algorithm SHA1
Get-FileHash data/raw/traffic-004-candidate.webm -Algorithm SHA256
New-Item -ItemType Directory -Path data/processed/traffic-004-cyclists -ErrorAction Stop
wsl -d Ubuntu-24.04 --exec ffmpeg -hide_banner -loglevel error -ss 12 -i data/raw/traffic-004-candidate.webm -t 3 -an -vf fps=10,scale=960:540 -start_number 0 data/processed/traffic-004-cyclists/%05d.jpg
wsl -d Ubuntu-24.04 --exec timeout 300 /home/clickvos/.venvs/clickvos/bin/python scripts/run_sam2_multi_frames.py --frames-dir data/processed/traffic-004-cyclists --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt --prompt-config configs/experiments/traffic-004-cyclists.json --output outputs/tasks/traffic-004-two-riders-001
wsl -d Ubuntu-24.04 --exec /home/clickvos/.venvs/clickvos/bin/python scripts/summarize_traffic_smoke.py --run outputs/tasks/traffic-004-two-riders-001 --frames data/processed/traffic-004-cyclists
```

输入集合摘要：按文件名字典序，将每个 UTF-8 文件名、一个 NUL 字节、该文件 SHA-256 原始 32 字节依次送入 SHA-256，得到 `7ed1b8a59e29f0f1a39f3c19235ef6d80cf819a3f9e26c25401b77cdccd1abef`。

## 真值资源核查与后续

- [BDD100K 官方下载文档](https://github.com/bdd100k/bdd100k/blob/master/doc/source/download.rst)仍列出 ETH 的 MOTS 2020 图像和标签；[数据许可](https://github.com/bdd100k/bdd100k/blob/master/doc/source/license.rst)与代码 BSD 许可不同。2026-10-06 Windows `curl.exe --head --location --max-time 20 https://dl.cv.ethz.ch/bdd100k/data/` 返回 curl 35 TLS handshake failure，网页工具为 502；未下载数据，未关闭证书验证。
- [OVOS 大学资源条目](https://research-repository.uwa.edu.au/en/datasets/ovos-occluded-video-object-segmentation-dataset/)指向 IEEE DataPort，但本轮未取得可核验下载许可，未下载。[SegTrack v2 页面](https://web.engr.oregonstate.edu/~lif/SegTrack2/dataset.html)也未建立符合本项目要求的使用条款，不进入测试。
- KITTI RGB 注册门槛未改变，本轮未获取图像。城市道路自行车逐帧 GT、真实连续消失后重现仍待补齐。
- 用户确认将来展示位置为 **Codex Sites**。先完成浏览器完整回归，再制作作品介绍、功能截图及真实证据说明；展示站点与需要 GPU 的推理服务分别规划。现有媒体本地保存约束继续有效，本轮没有上传媒体或发布站点。

这不是 Web 浏览器端到端测试、十人试用、全数据集评价或新增分割精度成绩。

## 代码与仓库核验

新增 `scripts/summarize_traffic_smoke.py` 可从原始掩码重新核对帧名、尺寸、二值取值及面积，并生成仅保存在本地的抽样叠加图。实际执行通过；`python -m pytest -q` 为 `122 passed in 6.98s`，仓库完整性检查通过（21 份结果摘要）。本轮没有修改应用推理或 Web 行为。
