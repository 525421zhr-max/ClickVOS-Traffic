# ClickVOS 版本归档与结题准备

整理日期：2026-10-10。对应应用源码提交 `60f72860f1968d3ce714d728eead90bac7dc2a3a`，包内版本 `0.1.0`。本目录是审阅工作稿，未声明软件著作权申报完成、容器部署成功或十人试用完成。

## 已整理材料

- [软件使用说明书](software-manual.md)：分别说明原 Gradio 与统一网站，涵盖选择目标、修正、下载、历史任务和错误处理。
- [功能与证据对应表](feature-evidence.md)：把已实现功能、实现位置、验证记录和边界放在同一张表里。
- [部署核查与验收步骤](deployment-readiness.md)：记录本轮实际检查，以及 Docker/云端尚需执行的步骤。
- [软著与结题材料清单](registration-preparation.md)：区分现有工程材料与待确认的申报信息，不预填权利归属或日期。

本机方便阅读的 PDF、TXT、来源说明、源码归档及 SHA-256 清单位于 `outputs/tasks/dev38-release-preparation/deliverables/`。源码归档按上述 Git 提交取内容，保留路径及逐文件散列；不含 SAM2 上游源码、权重、视频、任务输出、反馈、访问码或第三方字体图标。该归档用于审阅与追溯，不是完整可安装的发行包，也未按申报页数规则生成最终鉴别材料。

## 版本与记录规则

正式试用仍使用原 Gradio、`clickvos-user-trial-v1` 协议和原来的三项任务。本文档整理不改变其界面、默认配置、计时或统计规则。正式说明书定稿、源码鉴别材料和截图应最终指向同一冻结版本；后续应用修改需要另行核对。

本轮不读取或汇总个人试用结果，不将文件夹数量或待测表格当作完成样本。真实试用情况以后续主持人提供的原始记录为准。

原始运行日志和本机检查脚本保存在 `outputs/tasks/dev38-release-preparation/`；可公开核对的摘要为 `docs/research/results/dev38-release-preparation.json`，开发记录见 [DEV-38](../checkpoints/DEV-38-release-preparation.md)。
