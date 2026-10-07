# DEV-35：设计技能安装与作品页精修

- 日期：2026-10-07
- 应用基线：DEV-34 `9f978018b3f6cdb77b0d0f95074dcdc58e082329`
- 状态：安装、页面精修、浏览器检查及 Sites 第 2 版发布完成。
- 地址：https://clickvos-traffic-portfolio.elven-trail-5448.chatgpt.site

## 安装与使用

本机原有 `taste-skill`（name 为 design-taste-frontend）和 Impeccable。本轮使用内置 skill-installer，成功新增 `C:/Users/ASUS/.codex/skills/redesign-existing-projects/` 与 `frontend-design/`，没有重复覆盖原有技能。新技能可在下一轮自动识别，本轮已读取其 SKILL.md 并实际应用。

```powershell
python C:/Users/ASUS/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo Leonxlnx/taste-skill --path skills/redesign-skill --name redesign-existing-projects --dest C:/Users/ASUS/.codex/skills
python C:/Users/ASUS/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo anthropics/skills --path skills/frontend-design --dest C:/Users/ASUS/.codex/skills
```

GitHub 页面本轮显示 Taste 仓库约 93.1k stars、Impeccable 77.7k、Anthropic skills 179.9k；这是各仓库热度，不能理解为某个单独技能的分数。GitHub API 匿名额度耗尽，使用仓库页面核对，没有更改账号或绕过限制。来源：[Taste](https://github.com/Leonxlnx/taste-skill)、[Impeccable](https://github.com/pbakaus/impeccable)、[Anthropic](https://github.com/anthropics/skills)。

按 Taste 的保留式改版协议先审查当前页面，以 Impeccable polish 和 Anthropic frontend-design 辅助精修。保留技术作品集方向、品牌、导航、事实内容、交通 SVG 示意和五步流程。项目 `DESIGN.md` 记录设计约定；`AGENTS.md` 记录用户的界面质量偏好，便于后续按任务选择技能。

## 实际修改

- 自托管 Noto Sans SC 可变字体页面字符子集，109784 字节，附 SIL OFL 许可，避免依赖访客访问外部字体服务。
- 删除重复章节编号及装饰小标题，调整标题字距、字重和正文行距，桌面导航从 100px 收至 76px。
- 三列功能说明改为按用途排列的横向条目，手机顺序堆叠；首屏交通示意继续承担视觉识别。
- 硬偏移投影改为克制的柔和投影，流程说明改用同一主题内的浅表面，增加系统深色模式语义变量。
- 流程与箭头使用自托管 Tabler outline SVG，附 MIT 许可，保留提示点与掩码的语义颜色。
- 保留五步切换、下一步循环、上下/Home/End 导航；触摸目标、键盘焦点与按压反馈统一，减少动态效果时关闭平滑滚动和过渡。

没有改变主标注应用、模型行为、实验结果或十人试用协议。没有新增推理或质量指标。

## 验证与限制

- `node --check dist/app.js`、Git diff 空白检查通过。
- 隔离 Edge 浏览器检查 1440/1024/390/320px 浅色，以及 1440/390px 深色，共六种组合；字体加载、减少动态效果、无横向溢出均通过。
- 所有组合中的五个流程面板、End 键及下一步循环均通过。桌面/手机/深色/流程截图已本地复核，未放入部署包。
- Impeccable 检测器运行一次；其投影与边框叠加建议已处理。品牌字标的 Arial 和局部框选角标保留；检测器把嵌套容器的留白、深浅变量及字标误判为页面问题，按实际截图和样式核对，不宣称零警告。
- Lighthouse 13.5.0 对本地 `http://127.0.0.1:7870/` 默认移动端模拟审查：performance/accessibility/best-practices/SEO 均为 100，LCP=1737.0013ms，CLS=0。报告在独立项目本地 `qa/lighthouse.json`。这不是生产站点现场指标或用户体验试验，未测量真实 INP。
- 首次 Lighthouse 动态调试端口启动失败；改用隔离浏览器固定调试端口后成功。仅关闭本轮创建的浏览器和作品页本地预览，未停止本地标注应用。

## 发布

- Sites 源码提交：`f9bf2db25d9ab6878ee6fe8b53569316a46449ed`，官方工作流已推送并核对。
- 站点：`appgprj_6ac5b868145081918414e8b6050ba3d1`，沿用已有站点。
- 版本 2：`appgprj_6ac5b868145081918414e8b6050ba3d1~appgver_32b631421000819198ad4ff0ea771fb0`。
- 部署：`appgdep_6ac5bd014da08191b4edf67a47faa3d3`，succeeded，`2026-10-07T03:31:19.946869+00:00`。
- 本轮读取到站点当前 access_mode=public，因此沿用当前受众使用常规发布；未调用访问权限修改操作。DEV-34 创建时的私有状态保留为历史记录，不作为当前状态。
- 部署包 15 个文件，仅静态页面、字体/图标、许可和 hosting 配置；原始视频、模型、GT、掩码及真人反馈均未加入。

十人试用继续等用户提供真实记录。后续应用界面修改应采用适合操作工具的设计方法，并记录版本变化对试用的影响。
