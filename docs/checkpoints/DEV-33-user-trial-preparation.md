# DEV-33：十人试用材料准备

- 日期：2026-10-06
- 应用基线：DEV-32 `b971298d375866191359425005e4dd4db57fea49`
- 状态：材料和空记录准备完成；真实参与者 0 人，试用未开始。

## 交付内容

`docs/trials/README.md` 固定三个任务、主持人说明、帮助判定、时间/运行上限、成功条件、匿名字段和统计规则。不是招募记录或试用结论。`record-template.json` 的时间、点击、分数和结果均为空，不能把占位记录当完成样本。

`scripts/prepare_user_trial.py` 使用已有素材生成本地试用包，输出目录必须处于被 Git 忽略的 `outputs/tasks/`，存在时拒绝覆盖。没有下载、模型加载或推理。本轮不改应用行为，沿用 DEV-32 的 122 项通过记录，不把它写成新增测试数量。

本地包：`outputs/tasks/user-trial-v1/`。

| 任务 | 内容 | 规格 | 时间上限 |
| --- | --- | --- | --- |
| T1 | DAVIS car-roundabout 的单辆车 | 854×480，75 帧，10 FPS | 8 分钟 |
| T2 | traffic-002 的两名行人 | 960×540，50 帧，10 FPS | 10 分钟 |
| T3 | traffic-004 的两名骑行者及预览/撤销/修正 | 960×540，30 帧，10 FPS | 12 分钟 |

T1 的 10 FPS 是回放设置，不是原始视频采样时间。三项固定顺序用于逐级上手，不能用完成时间差推断类别难度。预计每人 35–45 分钟只是安排建议，没有真实计时数据。

## 实际检查

- 三段 MP4 均经 ffprobe 核对尺寸/帧数/10 FPS；FFmpeg 完整解码全部成功。
- 十份记录编号 P01–P10，共 30 个任务状态全部为 pending，参与标记 false，时间/点击/分数均未填。
- P01–P10 配置均能由应用读取，指向十个不同任务目录。主持人换人时停止并重启服务，避免沿用上一位的任务和答案；不据此宣称多用户服务安全。
- 重复执行准备命令被拒绝，所有已生成文件哈希保持不变。
- 真实参与者 0、GPU 运行 0、新增质量成绩 0；仅准备 CPU 媒体和记录。

```powershell
wsl -d Ubuntu-24.04 --exec /home/clickvos/.venvs/clickvos/bin/python scripts/prepare_user_trial.py --output outputs/tasks/user-trial-v1
wsl -d Ubuntu-24.04 --exec ffmpeg -hide_banner -loglevel error -i outputs/tasks/user-trial-v1/T1-car.mp4 -f null -
wsl -d Ubuntu-24.04 --exec ffmpeg -hide_banner -loglevel error -i outputs/tasks/user-trial-v1/T2-pedestrians.mp4 -f null -
wsl -d Ubuntu-24.04 --exec ffmpeg -hide_banner -loglevel error -i outputs/tasks/user-trial-v1/T3-riders.mp4 -f null -
```

第二次执行第一条命令应返回拒绝覆盖，不删除目录重试。`assets.json` 保存来源、许可署名、视频哈希与规格；公共仓库只保存核对过的材料摘要，媒体与反馈留本地。

下一步由真实参与者在主持人陪同下进行试用，先观察首位用户是否能理解任务；如需改协议或应用版本，保留原记录并建立新版本，不将准备过程或开发者代操作计入十人。
