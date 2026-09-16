# 周进度记录：W04 多对象、中间帧修正与 Web 界面

- 实施日期：2026-09-16
- 对应检查点：CP-03 多对象与修正接口、CP-04 单目标 Web 闭环
- 状态：工程接口与本地页面骨架完成；CP-03/CP-04 尚需完整交互回归后再整体验收

## 实际完成

- 新增有状态 `Sam2Session`，同一推理状态可登记多个对象，并在任意已跟踪帧继续添加提示。
- 支持指定起始帧、最大传播帧数和正向/反向传播参数。
- 新增真实 GPU 会话验证脚本，验证两个车辆对象和第 3 帧追加修正点。
- 安装并锁定 Gradio 6.27.0。
- 新增本地 Web 页面：上传、抽帧、首帧正负点、类别、权重路径、运行、MP4 预览和异常 JSON。
- 禁用 Gradio 遥测，避免测试结束后网络线程挂起。

## 可复现命令

```bash
python -m pip install -r requirements-app.txt
python -m pytest -q

python scripts/verify_sam2_session.py \
  --frames outputs/cp02/frames \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  --output outputs/tasks/w04-session/result.json

export CLICKVOS_CHECKPOINT=/home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt
python -m clickvos.web_app
```

## 实际结果

- Gradio：6.27.0，实际安装成功。
- 页面实际监听 `http://127.0.0.1:7860`，本地请求返回 HTTP 200；验证后正常关闭服务。
- 自动化测试在关闭遥测后正常退出：`18 passed in 5.77s`。
- 真实多对象结果：第一个提示后对象 ID 为 `[1]`；第二个提示后为 `[1, 2]`。
- 初始传播实际输出帧 0–5；两个对象每帧均得到非空掩码。
- 第 3 帧用三个车辆内部正点修正后，对象 1 即时掩码为 2,475 像素，对象 2 为 6,613 像素；随后从第 3 帧继续传播到第 6 帧。

本验证只证明多对象状态与追加提示链路可以运行。没有逐帧真值，因此不报告修正后的精度提升，也不宣称三个点优于一个点。

## 遇到的问题

- WSL 未安装 `rg`，检查 Meta SAM2 源码签名时改用系统已有的 `grep` 和 `sed`，没有额外安装工具。
- 第一次中间帧单正点 `(530,390)` 和第二次 `(545,390)` 均返回对象 1 空掩码；改为车辆内部三个正点 `(545,390)`、`(530,380)`、`(550,410)` 后得到 2,475 像素。该现象说明夜间反光场景对单点位置敏感，应保留为提示策略实验问题。
- Gradio 测试最初显示 18 项通过但进程未退出，原因是默认遥测线程等待网络；关闭遥测后解决。
- SAM2 `_C` 可选扩展仍未编译，警告继续存在。

## 本地产物

- `outputs/tasks/w04-session/result.json`：多对象和修正的实际数值。
- Web 页面本轮没有保存私人上传内容；验证只启动空页面并检查 HTTP 状态。

## 下一步

- 把 `Sam2Session` 的多对象选择、帧切换和修正操作接入 Web 页面，并给不同对象使用不同叠加颜色。
- 增加浏览器端完整操作回归，再决定 CP-03 和 CP-04 是否达到整体完成条件。
