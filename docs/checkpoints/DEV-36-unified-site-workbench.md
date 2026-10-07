# DEV-36：作品页与真实标注工作台整合

日期：2026-10-07。真实浏览器核心流程和导出核验通过；137 项自动化测试通过。Sites 第 3 版发布成功。

用户选择先使用本机 GPU。保留现有作品页品牌与原生 HTML/CSS/JS，增加实际上传、正负点、多目标、首帧预览/撤销、中间帧修正、下载工作台；复用现有 SAM2 和导出逻辑。原有 Gradio 服务及固定十人试用协议不覆盖。通过有访问码的独立网关和临时 HTTPS 连接接入 Sites；不是云 GPU 部署或多用户服务。

## 事先固定的工程回归

- 输入：已授权 traffic-004 12–15 秒片段 `outputs/tasks/user-trial-v1/T3-riders.mp4`，30 帧、960×540、10 FPS。
- SHA-256：`57916fe7b6968ac71e1da7cc5bb24b6409975b942b638d41b14edcc35d6be5b6`。
- 新独立目录：`outputs/tasks/unified-site-v1/`，不覆盖 DEV-28/29/32。
- 对象 1 非机动车，正点 (393,147)、(379,197)，负点 (348,145)、(433,215)。对象 2 非机动车，正点 (350,142)、(341,176)，负点 (393,147)、(318,210)。这些点选择骑行者人体，不声称轮圈或整车质量。
- 首帧对象 1 背景负点 (449,249)，单帧预览一次，核对正式输出哈希未变化；验证未传播补点时导出禁用/拒绝，撤销后继续。
- 中间帧 15 对象 1 背景负点 (480,399)，应用一次并传播到末尾。
- GPU 预算：一次完整初始传播、一次单帧预览、一次中间帧修正。仅发生工程故障时允许一次修复后确认，不继续调质量。
- 每个 GPU 操作观察上限 120 秒；超时停止追加运行，检查日志。验收：真实浏览器上传和画布点击、上述操作完成，实际下载 ZIP 与服务器文件一致，60 张 PNG 与独立解码的 COCO RLE 一致。
- 验证权限、跨域、上传限制、提示范围、状态保护；桌面和手机布局、深色模式以及原作品页导航。
- 无 GT、不新增 J/F，不计为真人试用、云部署或完整数据集评估。

## 实际实现与验证

新增有访问码的 FastAPI 网关（单进程，单操作锁），复用 `web_app.py` 现有回调；原生前端提供真实上传与画布点选。支持 20 个目标、128 个提示点、50 MiB/300 帧上限。首帧补点未应用时服务端拒绝导出，中间帧未应用提示阻止切换；访问码失效或连接失败后显示重连入口。本地连接页只监听 loopback，动态提供带权限的入口；网站移除地址片段中的访问码，只保留本次浏览器会话。

依赖实际版本：Python 3.12、PyTorch `2.11.0+cu128`、Gradio `6.27.0`、FastAPI `0.141.1`、Uvicorn `0.53.0`、Pydantic `2.13.5`；SAM2 源码提交和 Tiny 权重沿用 DEV-28，权重 SHA-256 `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`。可选 `_C` 扩展仍未启用。Node `v24.19.0` 用于 Edge CDP。

使用 Edge headless、独立 profile、1440×1100 视口，在本地前端 `http://127.0.0.1:7870/#workbench` 中连接真实临时 HTTPS 服务，逐个触发上传、目标按钮和画布坐标点击，不使用直接 Python 回调代替。真实浏览器前端与公开 Sites 的来源不同；额外核对正式 Sites 来源的 HTTPS 预检和鉴权响应。Sites 发布是否完成以原生部署结果为准。

实际任务 `5077678111f8`，输入哈希与冻结协议一致。两对象初始点及补点、修正点与冻结坐标一致。本轮执行一次 30 帧初始传播、一次单帧预览、一次第 15 帧到结尾修正，没有 GPU 追加或质量调参。

| 项目 | 核验结果 |
| --- | --- |
| 上传、两对象正负点、传播 | 完成，各对象保存 30 张掩码 |
| 首帧补点后的导出保护 | UI 禁用，服务端 POST 返回 409 |
| 单帧预览 | 正式 masks/overlays 共 120 个 PNG/JPG 哈希保持一致；本次未对报告/MP4 另做前后哈希，不扩大隔离结论 |
| 撤销首帧补点 | 恢复原提示、允许导出 |
| 对象 1 第 15 帧负点修正 | 记录 (480,399)，向后传播 15 帧 |
| 实际浏览器下载 ZIP | 1,147,065 字节，64 项，与服务端生成包一致 |
| 独立 PNG/RLE 校验 | 60 张掩码及全部 60 条 RLE 逐像素、area/bbox 一致 |
| 换视频 | 画布、目标、修正和下载状态清空；不追加 GPU |
| 工作台 5 种视口/主题 | 桌面、390px 手机、320px 窄屏、桌面/手机深色；无横向溢出，字体加载，无未捕获 JS 异常；已查看实际截图 |
| 原作品页 6 种视口/主题 | 五步按钮、键盘 End、下一步循环及减少动态效果保留 |

下载 SHA-256：`66181b5438d9b6591f5bd6889667a0c3bd83d5099a5eeb01e68aa8edab34a5c8`。日志事件 `propagate/add/preview/undo`；项目包含一次中间帧修正。原媒体与临时预览不进入 ZIP。初次报告 22 个异常，修正后 23 个；这些数量不是错误率。

最后的界面状态检查另外使用已保存的真实任务摘要模拟上传交接，不操作后端或 GPU：验证坐标输入、待应用中间帧点的帧/导出保护、切换目标不丢点、撤销恢复和 401 重连。通过本机连接页进入真实本机工作台并连接 GPU，验证权限片段从地址栏移除。它是状态检查，不冒充再次完整推理。

15 项新增 API 测试覆盖鉴权、静态目录隔离、跨域、空/超限/分块上传、无效大小、坐标、重复目标和提前导出。完整回归 `137 passed in 5.28s`，有 FastAPI/Starlette TestClient 上游弃用提示；不为此升级现有已验证环境。

## 复现与本地证据

启动：`./scripts/start_unified_site.ps1`；连接页 `http://127.0.0.1:7882/`，本机工作台端口 7880。官方 Cloudflare Windows 2026.10.0 程序哈希见运行说明；实际临时连接以 HTTP/2 接通，未修改代理、账号或网络配置。

```powershell
wsl -d Ubuntu-24.04 -- /home/clickvos/.venvs/clickvos/bin/python -m pytest -q
wsl -d Ubuntu-24.04 -- /home/clickvos/.venvs/clickvos/bin/python scripts/check_repository.py
wsl -d Ubuntu-24.04 -- /home/clickvos/.venvs/clickvos/bin/python scripts/verify_downloaded_bundle.py --task outputs/tasks/unified-site-v1/tasks/5077678111f8 --downloaded outputs/tasks/unified-site-v1/downloads/ClickVOS-5077678111f8.zip --output outputs/tasks/unified-site-v1/bundle-verification.json
```

本地 `outputs/tasks/unified-site-v1/driver.cjs`、`actions.jsonl`、`browser-checks.json`、`preview-isolation-check.json`、`bundle-verification.json`、`check-guards.cjs`、`ui-guards.json` 和截图保留工程证据，不发布。运行设置、访问码和日志不入 Git。公开备份含可恢复的 `web/site/` UI 代码和清楚许可的字体/图标；Sites 静态目录不包含推理素材。

## 边界

Sites 沿用现有公开访问范围和原地址，没有发布访问码或素材。源码提交 `a958dc513a533d8bde545973cb3dd1c28fa51fa4`；版本 `appgprj_6ac5b868145081918414e8b6050ba3d1~appgver_af07b7b4bf6c8191a7981fecd733ada5`；部署 `appgdep_6ac5c355f0a48191929266659e52bd87`，原生结果 `succeeded`。URL：<https://clickvos-traffic-portfolio.elven-trail-5448.chatgpt.site>。静态发布包 18 文件，不包含本地 runtime 或 task。

发布后从本机连接页点击在线入口，在实际 Sites 页面验证访问片段移除、自动连接真实 HTTPS 网关、GPU 就绪及上传控件启用；没有追加推理。`published-connection.json` 保留此功能核验，`https-site-origin.json` 记录正式来源预检 200、带访问码读取 200、无访问码读取 401。

临时网络连接和电脑必须持续运行；不是稳定云服务。网关仅单人操作，不支持多人并发隔离；服务重启后需重新上传，没有历史恢复 UI。原 Gradio 高级历史/回收区、重新激活候选确认和撤销仍由原应用提供。本轮没有真人试用、手机完整任务、多用户压力测试、新质量评价、容器实机或云 GPU 运行。真实交通 GT 与重新出现事件素材缺口保持原状。
