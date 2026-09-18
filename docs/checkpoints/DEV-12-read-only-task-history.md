# 开发记录：DEV-12 只读历史任务

- 日期：2026-09-18
- 状态：实现完成，自动测试和本地真实任务验证通过

## 做了什么

- 新增 `task_store`，从配置中的任务目录读取 `task.json`、`result.json` 和预览视频。
- Web 增加“历史任务（只读）”区域，可刷新列表、查看任务摘要和预览、重新生成标注包。
- 历史列表按最近更新时间排序，最多读取 200 个有效任务。
- 任务 ID 使用白名单校验，解析后的路径必须直接位于任务根目录下，防止目录穿越。
- 单个损坏或不完整目录不会拖垮列表；系统会跳过并显示数量。
- 历史任务不会恢复 SAM2 内存会话，也不会改写掩码。继续补点仍需重新运行传播。

## 复现命令

```bash
/home/clickvos/.venvs/clickvos/bin/python -m pytest -q

/home/clickvos/.venvs/clickvos/bin/python scripts/verify_task_history.py \
  --output outputs/tasks/dev12-task-history-summary.json

CLICKVOS_CHECKPOINT=/home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  /home/clickvos/.venvs/clickvos/bin/python -m clickvos.web_app
```

## 实际结果

| 检查项 | 结果 |
| --- | ---: |
| 识别出的有效任务 | 13 |
| 跳过的无效目录 | 3 |
| 打开的任务 | `7e3d167b0b81` |
| 视频帧数 | 50 |
| 对象数 | 1 |
| 待复核异常数 | 5 |
| 历史预览 | 存在 |
| 重新生成 ZIP | 486645 字节，53 个条目 |
| ZIP 包含原视频 | 否 |
| ZIP 包含抽帧图片 | 否 |
| 自动测试 | 36 passed in 6.32s |
| Web 启动 | HTTP 200 |

## 遇到的问题

- 本地任务目录中有 3 个不满足完整任务格式的目录。列表按设计跳过，并保留计数，没有删除这些目录。
- Gradio 6 的 `/config` JSON 包含空字符串键，PowerShell 默认 `ConvertFrom-Json` 无法解析；验证时改用 `-AsHashtable`，页面本身不受影响。
- WSL 仍显示 localhost 代理提示，不影响本地网页访问。

## 本地产物

- `outputs/tasks/dev12-task-history-summary.json`
- `outputs/tasks/7e3d167b0b81/exports/clickvos-7e3d167b0b81.zip`

运行产物继续由 `.gitignore` 排除。

## 下一步

- 设计需要二次确认的任务清理流程，先预览目标，再允许删除。
- 评估是否值得恢复可继续修正的 SAM2 会话；这需要重新加载模型并重放提示历史。
- 补充行人和非机动车的授权视频。
