# CP-02：合规交通视频传播与失败案例

- 日期：2026-09-15
- 状态：完成。
- 目标：在许可证清晰的自然拍摄交通视频上完成抽帧、首帧提示、SAM2 传播、掩码保存，并记录失败帧。

## 输入与许可

使用 Wikimedia Commons 视频 `Avtocesta.webm`，作者 idioterna，许可证为 CC BY 3.0。完整来源、许可、文件哈希和署名要求见 `docs/research/data-sources.md` 的 `traffic-001`。

原视频为夜间高速公路固定机位画面，包含强反光、多个相似车辆、小目标和目标驶出画面。本次截取前 5 秒并转换为 960×540、10 FPS、50 帧 H.264 MP4。原始媒体和裁剪不提交 Git。

## 实际命令

```powershell
curl.exe -fL --connect-timeout 15 --max-time 180 `
  -o "C:\Users\ASUS\Desktop\科研项目\大创\ClickVOS\data\raw\Avtocesta.webm" `
  "https://upload.wikimedia.org/wikipedia/commons/6/68/Avtocesta.webm"

wsl -d Ubuntu-24.04 -- ffmpeg -y -ss 0 -t 5 `
  -i "/mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS/data/raw/Avtocesta.webm" `
  -an -vf "scale=960:-2,fps=10" -vcodec libx264 -pix_fmt yuv420p `
  "/mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS/data/processed/cp02/traffic-sample.mp4"

wsl -d Ubuntu-24.04 -- /home/clickvos/.venvs/clickvos/bin/python `
  "/mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS/scripts/run_sam2_video.py" `
  --video "/mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS/data/processed/cp02/traffic-sample.mp4" `
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt `
  --output "/mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS/outputs/cp02" `
  --positive 520,370
```

## 配置

- SAM2：SAM-2 1.0，官方提交 `2b90b9f5ceec907a1c18123530e92e794ad901a4`。
- 模型：SAM2.1 Hiera Tiny。
- PyTorch：`2.11.0+cu128`，CUDA runtime 12.8。
- GPU：NVIDIA GeForce RTX 5060 Laptop GPU。
- 提示：首帧单个正点 `(520, 370)`，对象 ID 为 1；没有负点、框或中间帧修正。
- 视频和推理状态均 offload 到 CPU，以降低显存占用。
- 可选 `sam2._C` 扩展未编译，运行时跳过填洞后处理。

## 实际结果

| 检查项 | 实际值 |
| --- | --- |
| 抽取帧数 | 50 |
| 传播 yield 次数 | 50 |
| 保存二值掩码 | 50 |
| 保存叠加预览 | 50 |
| 抽帧时间 | 0.587657951 秒 |
| 模型加载时间 | 1.090924864 秒 |
| 推理段时间 | 7.463497327 秒 |
| 含状态初始化的折算速度 | 6.699272179 FPS |
| 峰值 CUDA 已分配显存 | 602,537,472 字节 |

结果来自 `outputs/cp02/result.json`，没有手工补写。由于没有逐帧真值，本检查点不报告 IoU、J、F 或 J&F。

## 失败案例

- 第 0 帧正确选中了画面中央偏下、驶向镜头的车辆。
- 车辆逐渐接近画面下沿，第 15 帧仅剩部分目标，第 16 帧掩码变为零，与目标驶出画面一致。
- 第 16–45 帧掩码前景像素数均为零。
- 第 46 帧掩码重新出现，但视觉检查表明它落在另一辆新进入相似位置的车辆上。这是错误重识别，不是原目标重新出现。
- 第 46–49 帧前景像素数为 `1552, 1747, 1915, 1915`。

该失败说明“掩码重新出现”不能直接解释为目标重现。后续失败检测需要结合目标消失时长、重新出现位置、外观或用户确认，至少应把这种帧标记为待复核，而不是静默接受。

## 输出

- `data/raw/Avtocesta.webm`：原始 CC BY 3.0 视频，仅本地保存。
- `data/processed/cp02/traffic-sample.mp4`：5 秒测试片段。
- `outputs/cp02/frames/`：50 张抽帧 JPEG。
- `outputs/cp02/masks/`：50 张二值 PNG。
- `outputs/cp02/overlays/`：50 张绿色叠加预览。
- `outputs/cp02/result.json`：实际配置和测量结果。

## 下一步

CP-03 将把脚本拆分为可复用模块，并优先实现“目标消失后异常重新激活”的检测信号。单正点结果保留为后续正负点、框和中间帧修正实验的基线。
