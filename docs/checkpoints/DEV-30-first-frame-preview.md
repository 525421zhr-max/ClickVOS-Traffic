# DEV-30：Web 首帧预览与补点记录

- 日期：2026-10-05
- 基于：DEV-29 `b44d52f`
- 状态：已完成；122 项自动化测试、两帧 GPU 回调闭环和桌面/手机宽度检查通过

## 本轮范围与验证预算

在已有首帧复核区增加“仅更新首帧预览”，并记录追加、撤销、预览和正式传播。预览复用已加载的模型，使用只含一张图像的全新会话，保存到任务内独立目录；原始全视频掩码、报告、视频和活动传播会话不应改变。提示未应用到全视频时禁止将旧结果当成新标注导出。

先用 CPU 测试确认独立会话、单帧隔离、原输出保护、日志记录、过期任务状态拒绝、导出范围和 Gradio 回调接线。随后只做一次本地 GPU 工程 smoke：已有 DAVIS `bmx-trees` 前 2 帧，DEV-28 原双对象提示，按原配置和 seed=0；在新任务上完成一次 2 帧初始传播、添加 DEV-29 第一个固定负点、仅预览首帧、撤销该点、再预览首帧，必要的应用验证限一次 2 帧重新传播。最多两次 2 帧传播和两次单帧预览，总进程上限 300 秒。不增加点法、模型、种子、GT 调参或质量评估；这是新增交互的工程回归，不改变 DEV-29 的 `budget_exhausted` 结论。

检查首帧预览前后正式文件和活动会话保持一致，点击记录跨预览和重新传播保留，导出只包含已应用的正式掩码及日志，不包含预览目录/源图像。未完成项写 `TBD (pending)`。

## 已实现

- 在现有首帧复核区增加“仅更新首帧预览”。复用已加载模型，使用新的单帧会话，完全不调用传播；当前选定的最大连通区域选项同样作用于预览。
- 预览保存到 `first_frame_previews/<preview_id>/`，包含唯一的首帧副本、逐对象掩码、彩色叠加图和 `preview.json`。不改写正式 `masks/`、`overlays/`、`result.json`、`exports/`，也不替换正在使用的传播会话。
- `first_frame_review.json` 持久记录 `add`、`undo`、`preview`、`propagate`，每条记录含顺序编号、UTC 时间、完整提示快照和动作详情。预览不会清掉撤销栈，重新传播也不会清空历史；记录文件损坏时拒绝覆盖。
- 补点后明确提示预览/完整视频的状态；提示或传播选项尚未应用到整段视频时，当前任务的 Web 导出会拒绝继续。重新传播成功后可导出，ZIP 额外包含补点记录，不包含预览目录或源帧。
- 换视频成功后清空旧结果、下载、首帧补点和活动会话引用；旧任务图像不能用于修改新任务。涉及模型和提示的主要 Web 回调共用同一队列，避免边传播边变更提示。

首帧预览入口目前用于已有活动传播会话的复核。首次传播前的预览、从历史任务恢复可编辑会话，仍未实现。此功能不自动判断质量是否达标；用户需检查遗漏、误覆盖以及负点对细结构的影响。

## 验证结果

自动化测试实际为 `122 passed in 4.80s`，较 DEV-29 新增 15 项：包括预览状态隔离、正式输出不变、后处理开关、错误提示点、日志连续追加/并发与坏文件保护、换任务隔离、导出状态和范围，以及 Gradio 回调接线与共用队列。

一次真实 GPU 工程 smoke 严格按上面的预算完成，输出为 `outputs/tasks/dev30-first-frame-preview-001/`：

1. 原双目标提示传播 2 帧，每对象保存 2 张正式掩码。
2. 为自行车追加固定负点 `(533,292)`，仅预览第 0 帧；正式文件的摘要、原会话对象和原提示张量均保持一致。
3. 尚未正式传播的补点被 Web 导出检查拒绝。
4. 撤销补点，再次仅预览第 0 帧；正式文件和原提示继续保持一致。
5. 使用恢复后的提示重新传播 2 帧，导出 ZIP；日志保留全部六个动作，源帧和试看的掩码未进入导出包。

实际动作序列为 `propagate → add → preview → undo → preview → propagate`，两次单帧预览的 `temporal_propagation_count` 均为 0。没有加载 GT 或生成新的 IoU/J/F 成绩；DEV-29 的未通过结论保持不变。完整检查在 `preview-smoke-result.json`，经过核对的公开摘要在 `docs/research/results/dev30-first-frame-preview.json`。

环境沿用 Python 3.12.3、PyTorch 2.11.0+cu128、RTX 5060 Laptop GPU、SAM2.1 Hiera Tiny，配置和权重校验同 DEV-29。可选 `_C` 扩展仍未启用。

界面使用本机 Edge 无头浏览器检查了 1440×1100 与 390×844 两种视口：新按钮和记录折叠区可见，手机端按列排列，没有横向溢出。机械 UI 检查返回空问题列表。截图和检查 JSON 仅在 `outputs/tasks/dev30-ui-inspection-001/` 本地保存。这次浏览器检查覆盖布局和初始状态；真实 GPU 流程通过 Web 的 Python 回调执行，不冒充浏览器内上传到下载的完整端到端测试或真人试用。

## 复现命令

项目根目录 PowerShell 中执行；复现时换用不存在的输出目录：

```powershell
wsl -d Ubuntu-24.04 --exec /home/clickvos/.venvs/clickvos/bin/python -m pytest -q
wsl -d Ubuntu-24.04 --exec timeout 300 /home/clickvos/.venvs/clickvos/bin/python scripts/verify_first_frame_preview.py --frames-dir data/raw/davis2017/trainval-bmx-trees/DAVIS/JPEGImages/480p/bmx-trees --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt --output outputs/tasks/dev30-first-frame-preview-001
wsl -d Ubuntu-24.04 --exec /home/clickvos/.venvs/clickvos/bin/python scripts/check_repository.py
```

运行 Web 后，在“3. 传播结果”选择目标，补点 → 仅更新首帧预览 → 检查/撤销 → 满意后用补点重新传播 → 导出标注。

## 后续

下一步应以实际使用流程做浏览器内上传、点选、预览与下载的完整回归，再整理十人试用任务和记录表。任何新提示质量实验继续单独冻结；城市道路非机动车 GT、真实重现片段、Docker/云部署与软著提交仍待完成。
