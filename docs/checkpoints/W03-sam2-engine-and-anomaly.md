# 周进度记录：W03 SAM2 引擎、异常检测与预览导出

- 实施日期：2026-09-16
- 计划周：2026-10-05 至 2026-10-11，异常规则和导出属于后续任务的提前实现
- 对应检查点：CP-03 单目标部分、CP-05 预览部分、CP-06 基线规则部分；均未宣称整体完成
- 状态：本轮闭环完成

## 实际完成

- 新增 `Sam2Engine`，封装模型加载、权重 SHA-256 校验、提示校验、状态初始化、单目标传播、掩码和叠加图保存。
- 新增对象类别、对象 ID、提示帧、正负点的数据结构，为多目标和中间帧修正保留接口。
- `run_sam2_video.py` 已改为调用引擎，原 CP-02 命令参数继续兼容。
- 新增“连续消失后重新激活”异常规则和 JSON 报告。
- 新增连续叠加帧到 H.264 MP4 的导出功能。
- 新增 9 个测试；完整测试总数从 7 增至 16。

## 可复现命令

```bash
/home/clickvos/.venvs/clickvos/bin/python -m pytest -q

/home/clickvos/.venvs/clickvos/bin/python scripts/run_sam2_video.py \
  --video data/processed/cp02/traffic-sample.mp4 \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  --output outputs/tasks/w03-engine-cp02 \
  --positive 520,370 --category vehicle

/home/clickvos/.venvs/clickvos/bin/python -m clickvos.anomaly \
  outputs/cp02/result.json --minimum-empty-frames 3 \
  --output outputs/cp02/anomalies.json

/home/clickvos/.venvs/clickvos/bin/python -m clickvos.export \
  outputs/tasks/w03-engine-cp02/overlays \
  outputs/tasks/w03-engine-cp02/preview.mp4 --fps 10
```

## 实际环境与输入

- 输入仍为已登记的 `traffic-001` CP-02 裁剪，没有新增或使用私人素材。
- PyTorch：2.11.0+cu128；CUDA runtime：12.8。
- GPU：NVIDIA GeForce RTX 5060 Laptop GPU。
- 模型：SAM2.1 Hiera Tiny；权重 SHA-256 与默认配置一致。
- 提示：对象 1、类别 `vehicle`、首帧正点 `(520, 370)`。

## 实际结果

自动化测试最终结果：

```text
................                                                         [100%]
16 passed in 2.93s
```

真实 GPU 回归：

| 检查项 | 实际值 |
| --- | --- |
| 抽取帧数 | 50 |
| 保存掩码 | 50 |
| 保存叠加帧 | 50 |
| 模型加载时间 | 1.226395746 秒 |
| 推理段时间 | 8.329664258 秒 |
| 含状态初始化折算速度 | 6.002642898 FPS |
| 峰值 CUDA 已分配显存 | 602,537,472 字节 |
| 与 CP-02 每帧前景像素序列比较 | 完全一致 |
| 预览视频时长 | 5.000000 秒 |
| 预览视频大小 | 461,206 字节 |

本次是同机回归，不把与 CP-02 的耗时差异解释为性能提升或下降。

异常检测报告实际命中 1 项：第 16 帧开始连续空掩码 30 帧，第 46 帧以 1,552 像素重新激活，严重级别为 `high`。这与 CP-02 人工视觉检查记录一致，但该规则只表示“待复核”，不能独立证明身份漂移。

## 遇到的问题

- 首次视频导出测试结果为 `15 passed, 1 failed`。原因是测试错误地要求参数列表中存在纯 `%05d.jpg`，实际传入的是完整路径；修正为检查路径结尾后，16 项全部通过。
- SAM2 仍提示可选 `_C` 扩展未编译，因此跳过填洞后处理；核心传播正常，结果与 CP-02 一致。
- WSL localhost/NAT 警告乱码仍存在，但未影响本轮退出码和产物。

## 本地产物

- `outputs/tasks/w03-engine-cp02/result.json`
- `outputs/tasks/w03-engine-cp02/masks/`
- `outputs/tasks/w03-engine-cp02/overlays/`
- `outputs/tasks/w03-engine-cp02/preview.mp4`
- `outputs/cp02/anomalies.json`

以上运行产物被 Git 忽略，只在本机保存；代码、测试和本记录进入 Git。

## 下一步

- 在引擎中增加多对象状态和中间帧追加提示，再接入第一版 Gradio 上传、点击与播放界面。
