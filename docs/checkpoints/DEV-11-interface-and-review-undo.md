# 开发记录：DEV-11 操作流程界面与候选确认撤销

- 实施日期：2026-09-18
- 对应计划：第一阶段界面可用性完善、CP-06 人工复核安全性
- 状态：工程实现、自动化测试和 CP-02 真实 GPU 回归通过

> `DEV-11` 是第十一次开发迭代，不代表十二周计划的第十一周。从本记录开始使用 `DEV` 前缀，避免与自然周混淆。

## 完成内容

- Web 页面按“准备视频 → 标记目标 → 运行传播 → 复核修正 → 导出标注”重新组织。
- 当前状态固定在主流程顶部；完整运行 JSON 和传播高级参数改为折叠展示。
- 增加克制的青绿色状态色、键盘焦点、移动端换行和危险操作样式。
- “确认候选目标重新出现”增加配对的“撤销本次候选确认”。
- 撤销后重新写入空掩码、恢复待复核状态和异常列表，并重建合成预览。
- 确认与撤销写入 `review_actions`，项目 JSON 导出会保留动作记录。

## 可复现命令

```bash
/home/clickvos/.venvs/clickvos/bin/python -m pytest -q

/home/clickvos/.venvs/clickvos/bin/python scripts/verify_anomaly_review.py \
  --video data/processed/cp02/traffic-sample.mp4 \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  --output outputs/tasks/dev11-review-undo-summary.json

CLICKVOS_CHECKPOINT=/home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  /home/clickvos/.venvs/clickvos/bin/python -m clickvos.web_app
```

## 实际结果

输入仍为已登记的 `traffic-001`，共 50 帧，首帧车辆正点 `(520,370)`。

| 检查项 | 实际值 |
| --- | ---: |
| 初始第 46 帧最终掩码像素 | 0 |
| 确认后第 46 帧掩码像素 | 1533 |
| 撤销后第 46 帧掩码像素 | 0 |
| 确认/撤销影响帧 | 46、47、48、49 |
| 待复核异常数变化 | 5 → 4 → 5 |
| 最终活动确认数 | 0 |
| 审计动作数 | 2 |
| 模型加载时间 | 1.286260195 秒 |
| 初始传播时间 | 7.042569919 秒 |
| 峰值 CUDA 分配 | 646017024 字节 |
| 自动化测试 | 32 passed in 5.99s |
| Web 启动检查 | HTTP 200 |

第 46 帧候选仍是已知的错误车辆。本轮先确认再撤销是为了验证误操作恢复能力，不代表该候选分割正确，也不构成精度提升证据。

## 遇到的问题

- Gradio 6.27.0 已将 `css` 参数从 `Blocks` 构造函数移到 `launch()`；已按新接口调整，测试不再产生弃用警告。
- 第一次启动验证命令因 PowerShell 嵌套引号解析失败，改用正式模块入口后正常启动。
- PowerShell 不能直接读取摘要中的 `/mnt/c/...` 路径，详细结果通过任务 ID 映射到 Windows 工作区读取。
- SAM2 `_C` 可选扩展警告和 WSL NAT 提示仍存在，但没有影响本轮退出码或记录结果。

## 本地产物

- `outputs/tasks/dev11-review-undo-summary.json`
- `outputs/tasks/7e3d167b0b81/result.json`
- `outputs/tasks/7e3d167b0b81/exports/preview.mp4`

以上运行产物被 Git 忽略。

## 下一步

- 增加任务列表、历史任务恢复和安全清理。
- 引入许可证明确的行人和非机动车短视频。
- 用真实遮挡后同一目标重新出现的样本验证正确确认与误拦截。
