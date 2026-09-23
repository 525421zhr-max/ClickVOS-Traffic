# Checkpoint 规则

每完成一个可独立验证的成果，就创建一个 checkpoint：提交代码、记录环境和测试证据，并同步推送到 GitHub。不要按日历机械提交；以“可复现的工作状态”为单位。

## 必做 checkpoint

| 编号 | 完成条件 | 证据 |
| --- | --- | --- |
| CP-00 | 仓库与目录已建立 | 环境清单、项目结构 |
| CP-01 | SAM2 可加载，单帧正/负点出掩码 | 命令、截图、版本信息 |
| CP-02 | 合规交通视频可逐帧传播并保存 | 数据来源、提示、帧数、掩码与失败帧 |
| CP-03 | 统一推理服务支持多目标与中间帧修正 | 自动化测试、对象 ID 与状态记录 |
| CP-04 | Gradio 上传、点击、修正及下载闭环可运行 | 操作录屏、输入与输出样例 |
| CP-05 | 导出掩码、叠加视频和标准标注 | 可重读的导出文件与格式校验 |
| CP-06 | 疑似传播失败帧检测完成基线验证 | 规则、阈值、命中与误报记录 |
| CP-07 | 公开交通数据子集完成定量评估 | 数据许可证、J&F、速度、显存与失败案例 |
| CP-08 | 十名用户完成规定标注任务 | 匿名任务记录、点击次数、时间和满意度 |
| CP-09 | 容器化和云 GPU 部署验证完成 | 镜像、部署文档、安全与清理检查 |
| CP-10 | 软件著作权和结题材料齐备 | 版本归档、说明书、源码文档、报告和演示 |

## 每次记录格式

新建 `CP-xx-简短主题.md`，填写：日期、Git 提交号、完成内容、运行命令、环境版本、输入样例、输出位置、已知问题、下一步。禁止写入 API Key、账号令牌、个人隐私或原始受限视频。

## 节奏

- 开发中：每次功能闭环即 checkpoint；至少每周一次可运行提交。
- 实验中：每组实验结束即记录配置、数据版本、指标与失败样例。
- 推送前：确认 `.gitignore` 生效，尤其是模型、视频、日志和 `.env` 未被纳入提交。

## 开发记录

以下 `W01–W10` 是早期沿用的开发迭代编号，不等于十二周计划中的自然周完成度。从后续记录开始改用 `DEV-xx`，十二周进度单独按计划验收项统计。

- [W01：视频输入工程底座](W01-video-input-foundation.md)（2026-09-15）
- [W02：配置、错误模型与素材候选](W02-config-errors-and-sources.md)（2026-09-16）
- [W03：SAM2 引擎、异常检测与预览导出](W03-sam2-engine-and-anomaly.md)（2026-09-16）
- [W04：多对象、中间帧修正与 Web 界面](W04-multi-object-correction-web.md)（2026-09-16）
- [W05：掩码清晰度与串目标诊断](W05-mask-quality-pilot.md)（2026-09-17）
- [W06：Web 中间帧修正闭环](W06-web-midframe-correction.md)（2026-09-17）
- [W07：目标重新激活保护](W07-reactivation-guard.md)（2026-09-17）
- [W08：Web 多目标交互式分割](W08-web-multi-object.md)（2026-09-17）
- [W09：多目标标注下载与 COCO RLE 导出](W09-annotation-export.md)（2026-09-17）
- [W10：异常帧定位、候选确认与重叠提示](W10-anomaly-review.md)（2026-09-18）
- [DEV-11：操作流程界面与候选确认撤销](DEV-11-interface-and-review-undo.md)（2026-09-18）
- [DEV-12：只读历史任务](DEV-12-read-only-task-history.md)（2026-09-18）
- [DEV-15：多类别素材回归与 DAVIS 指标链路](DEV-15-multiclass-data-and-davis-evaluation.md)（2026-09-21）
- [DEV-16：道路车辆首帧提示对照](DEV-16-road-traffic-prompt-comparison.md)（2026-09-21）
- [DEV-17：首帧对象完整性复核](DEV-17-first-frame-completeness-review.md)（2026-09-21）
- [DEV-18：结果区首帧补点与同任务重新传播](DEV-18-inplace-first-frame-rerun.md)（2026-09-22）
- [DEV-19：Web 回收区任务恢复](DEV-19-web-task-restore.md)（2026-09-23）
- [DEV-20：道路行人真值验证与重新激活保护筛查](DEV-20-road-pedestrian-gt-and-guard-audit.md)（2026-09-23）

新记录从 [模板](WEEKLY-TEMPLATE.md) 复制。实验数字必须能回到命令输出或原始文件。
