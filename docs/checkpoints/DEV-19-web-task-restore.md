# DEV-19：Web 回收区任务恢复

- 日期：2026-09-23
- 状态：功能、测试和本机 Web 启动检查通过；未移动真实用户任务

## 完成内容

- 回收区增加任务列表、恢复范围预览、编号确认和恢复按钮。
- 恢复前核对 `.archive.json`、`task.json`、目录名称、原任务根目录和预览时的文件快照。
- 原任务编号已被占用时拒绝覆盖。恢复成功后移回 `outputs/tasks`，移除归档标记，重新显示在历史任务列表。
- 更新操作说明。永久过期清理仍未实现，回收区移动不释放磁盘空间。

## 可复现命令

在仓库根目录的 WSL 环境运行：

```bash
/home/clickvos/.venvs/clickvos/bin/python -m pytest -q
/home/clickvos/.venvs/clickvos/bin/python scripts/check_repository.py
CLICKVOS_PORT=7869 /home/clickvos/.venvs/clickvos/bin/python -m clickvos.web_app
```

另开终端读取 `http://127.0.0.1:7869/config`，检查页面配置是否包含“回收区任务”“恢复范围预览”和“恢复到历史任务”。

## 环境与输入

- WSL Ubuntu 24.04、Python 3.12.3、PyTorch 2.11.0+cu128；SAM2.1 Hiera Tiny 环境沿用现有配置。
- 恢复测试使用 pytest 临时目录中的模拟任务，不涉及真实视频、模型推理或用户现有任务。

## 实际结果

- 自动测试：`51 passed in 5.14s`。
- 仓库检查：`15 result summaries, 101 tracked files, no tracked model/video artifacts`。该命令执行时新增文件尚未提交，因此 tracked files 数字随后会变化。
- 临时任务归档、列表、预览、确认后恢复通过；错误确认、目标编号占用、归档内容变化和记录不一致均有拒绝测试。
- 本机 Web `/config` 返回 HTTP 200，上述三个恢复控件均存在；验证后关闭临时服务。
- 真实用户任务恢复：未执行。

## 遇到的问题

- PowerShell 默认 `ConvertFrom-Json` 无法解析 Gradio `/config` 中的空键名；改用 `ConvertFrom-Json -AsHashtable` 后成功检查控件。这是本次检查脚本的解析问题，Web 服务本身返回 HTTP 200。
- 回收区不释放磁盘空间，未来若增加永久清理，仍需先确定保留期、预览和审计要求。

## 下一步

继续补充带真值的道路行人与非机动车样本，或在真实遮挡场景中检查异常保护的误拦截；不得把单条车辆序列结果外推到所有类别。
