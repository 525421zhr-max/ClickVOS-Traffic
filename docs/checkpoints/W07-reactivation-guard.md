# 周进度记录：W07 目标重新激活保护

- 实施日期：2026-09-17
- 对应检查点：CP-06 传播异常提示与保守阻断
- 状态：工程实现和 CP-02 真实回归完成；尚未在其他类别上验证

## 问题

CP-02 中原车辆在第 16 帧离场，掩码连续为空 30 帧，但 SAM2 在第 46 帧错误激活到另一辆车。已有异常规则只能报告问题，最终导出的掩码仍包含错误车辆。

## 本轮实现

- 增加有状态的 `ReactivationGuard`。目标曾经可见、连续空掩码达到阈值后，新的非空掩码进入待确认状态。
- Web 默认启用保护，当前阈值为连续空 3 帧。
- 可疑候选原样保存至任务目录的 `review_candidates/masks/` 和 `review_candidates/overlays/`。
- 最终 `masks/` 和预览使用空掩码，避免未经确认的目标直接进入标注结果。
- `result.json` 同时记录模型候选像素、最终像素、触发帧、连续空帧数和保护状态。
- 用户中途修正时，正点表示确认目标重新出现；只有负点时继续保持拦截逻辑。
- 新增纯规则测试和文件级集成测试。

## 可复现命令

```bash
/home/clickvos/.venvs/clickvos/bin/python -m pytest -q

/home/clickvos/.venvs/clickvos/bin/python scripts/verify_reactivation_guard.py \
  --video data/processed/cp02/traffic-sample.mp4 \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  --output outputs/tasks/w07-reactivation-guard-summary.json
```

## 真实 GPU 回归

输入仍为已登记的 `traffic-001` CP-02 公开视频，首帧正点 `(520,370)`，开启最大连通区域和重新激活保护。运行环境与 CP-02 相同。

| 检查项 | 实际值 |
| --- | ---: |
| 模型加载时间 | 1.165237981 秒 |
| 初始传播与保存时间 | 5.433770377 秒 |
| 第 46–49 帧模型候选像素 | 1533、1743、1915、1916 |
| 第 46–49 帧最终输出像素 | 0、0、0、0 |
| 首次触发帧 | 46 |
| 触发前连续空帧 | 30 |
| 被保护抑制的帧数 | 4 |
| 预览视频大小 | 464,711 字节 |
| 自动化测试 | 27 passed in 3.44s |

第 46 帧候选掩码文件实际存在且大小为 903 字节；对应最终空掩码为 583 字节。候选文件没有提交 Git，只在本地任务目录保存。

## 接受结论

工程门通过：已知错误重新激活不会再静默写入最终标注，候选证据得到保留，用户可明确确认或继续否定。

研究结论暂时只限于 CP-02：保护层成功阻断这一例身份漂移，但不能据此宣称适用于所有车辆、行人或非机动车。固定 3 帧阈值可能拦截真实的短时遮挡后重现，需要在更多公开授权样本上比较误拦截率和人工修正成本。

## 遇到的问题

- SAM2 `_C` 可选扩展仍未编译，运行时继续跳过填洞后处理；核心传播成功。
- WSL 仍输出 localhost/NAT 警告乱码，但退出码为 0，未影响运行。
- Windows 没有可用的 `python` 命令，验证继续使用项目固定的 WSL Python 3.12 环境。

## 本地产物

- `outputs/tasks/w07-reactivation-guard-summary.json`
- `outputs/tasks/b438ba06742d/result.json`
- `outputs/tasks/b438ba06742d/review_candidates/`
- `outputs/tasks/b438ba06742d/exports/preview.mp4`

以上产物均被 Git 忽略。

## 下一步

- 在至少一个真实遮挡后同一目标重新出现的公开交通片段上测试误拦截。
- 在 Web 中增加候选帧定位和“确认继续传播”按钮，减少用户查找成本。
- 后续将固定阈值改为配置项，并按 FPS 换算为时间阈值。
