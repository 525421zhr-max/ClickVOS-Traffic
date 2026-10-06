# DEV-32：浏览器完整流程回归

- 日期：2026-10-06
- 基于：DEV-31 `a6c7b80`
- 状态：桌面浏览器核心流程通过；实际下载 ZIP 校验通过，122 项自动化测试通过。

## 固定范围与预算

使用已登记的 traffic-004 原片 12–15 秒对应的 30 张 960×540 帧，编码为 10 FPS MP4；目标及初始正负点沿用 DEV-31。独立本地 Gradio 服务、独立任务根目录和 Edge 测试配置，不使用日常浏览器资料。

在真实浏览器通过文件上传、按钮、下拉框和图像坐标点击完成：抽帧、创建两对象、正负点、初始传播、首帧补点、仅首帧预览、未应用提示时导出拒绝、撤销、重新传播、中间帧修正、下载 ZIP，以及换视频后的旧状态清除。补点固定对象 1 背景负点 (450,250)，中间帧 15 固定背景负点 (480,400)。这是工程验证，不进行质量调参或新 J/F 评价。

GPU 预算：初始传播一次、首帧重新传播一次、中间帧到结尾修正一次，至多两次单帧预览；每个操作上限 120 秒。只在工程故障导致流程无法完成时，修复后进行一次确认回归，保留失败证据。没有错误不追加 GPU 运行。检查浏览器实际下载文件、ZIP 内容和日志、预览前后正式输出保护；按钮调用经浏览器触发，不用直接 Python 回调代替。

## 实际浏览器路径

使用本机 Edge headless、1440×1100 视口、独立临时 profile，通过 CDP 上传本地文件并发送鼠标事件；操作页面为 `http://127.0.0.1:7866`。没有直接调用 Gradio 预测 API 或 Python 业务回调代替点击。读取 DOM、临时给图像容器添加测试定位属性，仅用于定位与核验。

| 操作 | 实际结果 |
| --- | --- |
| 上传 MP4、抽帧 | 视频可播放；创建 `bf3e81f09121`，30 帧 |
| 新建两对象、切换正负点 | 均为非机动车，各 2 正点、2 负点 |
| 运行 SAM2 | 首帧彩色结果、完整视频和异常列表显示；各对象 30 张掩码 |
| 对象 1 首帧追加负点、单帧预览 | 完成；122 个正式文件哈希全部保持一致 |
| 带待应用补点点击导出 | 显示“尚未应用到整段视频”错误，下载链接数为 0 |
| 撤销、再次首帧预览、重新传播 | 全部完成；六个首帧事件连续保留 |
| 选择对象 1、载入第 15 帧、负点修正 | 重新传播 15 帧，修正记录保留 |
| 生成 ZIP、点击浏览器下载链接 | 实际下载 1,147,134 字节；与服务器生成包哈希一致 |
| 换成 traffic-003 授权视频、重新抽帧 | 新任务 `0a7ab402038b`，101 帧，仅抽帧、无新推理 |
| 换视频后状态检查 | 目标列表空；旧结果图/预览视频/修正图/下载链接数均为 0，修正帧号归零 |
| 新任务直接点击首帧预览 | 正确要求先为当前视频运行传播，没有复用旧会话 |
| 历史列表打开旧任务并重新导出 | 历史视频和下载链接出现，新任务仍保持空提示/无旧结果 |

保留界面默认最大连通区域及重新激活保护。初次传播报告 22 个待复核异常；修正后历史列表为 23 个。异常数量不是错误率，也不代表这次验证了真实重新激活候选的确认/撤销。

GPU 实际执行两次完整 30 帧传播、两次单帧预览及一次第 15 帧到末尾的修正传播，没有追加质量重跑。中间帧传播记录为 15 帧、4.4558 秒，不用于性能比较。

浏览器缩放及点击取整使应用记录坐标与计划坐标有 0–2 像素差异；本轮按浏览器实际记录保存，不声称逐像素复现 DEV-31。对象 1 正点 `(393,147),(379,197)`，负点 `(348,145),(433,215)`；对象 2 正点 `(350,142),(341,176)`，负点 `(393,147),(318,210)`。中间帧负点为 `(480,399)`，首帧补点坐标见 JSON 摘要。这也包含 MP4 编码/解码差异，不能把两个任务当作质量对照。

## 下载内容独立核验

新增 `scripts/verify_downloaded_bundle.py` 对实际下载文件执行检查：

- ZIP 与生成文件 SHA-256 一致：`51e91393bef3124f5d0c078b1bc7eca82e799fca06fc80849a69567358d6ed55`。
- 共 64 项：60 张逐对象掩码、项目 JSON、COCO RLE JSON、预览 MP4、首帧补点日志。没有源视频、抽帧图或单帧临时预览。
- 每张 PNG 与任务文件逐字节一致，尺寸、二值格式、报告面积一致。
- 独立展开全部 60 条 COCO RLE，逐像素对照 PNG，并核对 area/bbox；全部一致。
- 六个事件顺序为 `propagate/add/preview/undo/preview/propagate`，项目包含对象 1 第 15 帧的修正记录。

## 复现入口与本地证据

工程环境沿用 DEV-31；Node `v24.19.0` 用于 CDP 控制。没有安装额外浏览器自动化依赖。本轮主应用代码未修改。

本地根目录：`outputs/tasks/dev32-browser-e2e-001/`。`driver.cjs`、`actions.jsonl` 保留实际控制器与操作输入；其中包含最初定位适配失败的记录，不把这些记录描述为产品错误。Gradio 当前没有旧脚本假设的 `component-N` DOM ID，下拉选项文本还含选中标记；随后按控件标签定位并完成流程。没有因此重跑已完成的 GPU 操作。

`01-prompts.png` 至 `08-history.png` 保留关键页面；`preview-isolation-check.json`、`bundle-verification.json`、`final-dom-check.json` 保留文件和 DOM 检查。媒体、截图、下载包和浏览器 profile 不提交 Git。测试服务和测试浏览器在完成后关闭。

```powershell
# 准备输入（目录需先创建；不要覆盖已有证据）
wsl -d Ubuntu-24.04 --exec ffmpeg -hide_banner -loglevel error -framerate 10 -i data/processed/traffic-004-cyclists/%05d.jpg -c:v libx264 -pix_fmt yuv420p outputs/tasks/dev32-browser-e2e-001/traffic-004.mp4
# config.json 复制默认配置，只将 task.tasks_root 改为 outputs/tasks/dev32-browser-e2e-001/tasks
wsl -d Ubuntu-24.04 --exec env CLICKVOS_PORT=7866 CLICKVOS_CONFIG=outputs/tasks/dev32-browser-e2e-001/config.json CLICKVOS_CHECKPOINT=/home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt /home/clickvos/.venvs/clickvos/bin/python -m clickvos.web_app
# 按上表在浏览器完成操作后，使用实际任务 ID/下载文件运行：
wsl -d Ubuntu-24.04 --exec /home/clickvos/.venvs/clickvos/bin/python scripts/verify_downloaded_bundle.py --task outputs/tasks/dev32-browser-e2e-001/tasks/bf3e81f09121 --downloaded outputs/tasks/dev32-browser-e2e-001/downloads/clickvos-bf3e81f09121.zip --output outputs/tasks/dev32-browser-e2e-001/bundle-verification.json
wsl -d Ubuntu-24.04 --exec /home/clickvos/.venvs/clickvos/bin/python -m pytest -q
```

上传 MP4 SHA-256：`57916fe7b6968ac71e1da7cc5bb24b6409975b942b638d41b14edcc35d6be5b6`，1,002,543 字节。最后回归为 `122 passed in 5.49s`。

## 边界与下一步

本轮通过的是桌面浏览器核心标注流程，不代表十人试用、手机完整流程、多用户隔离/压力测试或云端部署。真实连续空掩码后重现的候选仍缺失，相关确认/撤销不能据本轮宣称实景覆盖。无新增 GT 指标。下一步可以准备十人试用任务与记录表，并制作 Codex Sites 作品介绍，在线 GPU 服务仍另行验证。
