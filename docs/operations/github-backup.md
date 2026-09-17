# GitHub 备份与上传规则

远程仓库：`https://github.com/525421zhr-max/ClickVOS-Traffic`（当前保持私有）。

## 上传内容

- `src/`、`scripts/`、`tests/` 中的源码和自动化测试。
- `configs/` 中不含密钥的配置。
- `docs/` 中的检查点、复现命令、数据来源登记和研究记录。
- `docs/research/results/` 中从已接受检查点整理出的机器可读结果摘要。
- 依赖声明、GitHub Actions 工作流和空目录占位文件。

## 永不上传

- SAM2 权重及其他 `*.pt`、`*.pth`、`*.ckpt` 文件。
- 原始或处理后视频，包括 `*.mp4`、`*.mov`、`*.avi`、`*.webm`、`*.mkv`。
- 逐帧图像、掩码、叠加视频、任务目录和日志。
- `.env`、令牌、账号凭据或本机专用配置。
- 私人照片、人像、来源或授权不清晰的素材及其衍生产物。

上述内容主要由 `.gitignore` 防护；`scripts/check_repository.py` 还会检查已经进入 Git 索引的危险文件，避免仅依赖忽略规则。

## 日常备份命令

```powershell
git status --short
wsl -d Ubuntu-24.04 -- bash -lc "cd '/mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS' && /home/clickvos/.venvs/clickvos/bin/python scripts/check_repository.py"
wsl -d Ubuntu-24.04 -- bash -lc "cd '/mnt/c/Users/ASUS/Desktop/科研项目/大创/ClickVOS' && /home/clickvos/.venvs/clickvos/bin/python -m pytest -q"
git add <明确需要提交的文件>
git diff --cached --check
git diff --cached
git commit -m "<本轮变更说明>"
git push origin main
git status --short
```

不要使用 `git add .` 跳过人工检查。实验数字只有在本地原始结果和 checkpoint 已核对后，才能进入 `docs/research/results/`。没有真值的实验明确记录 `ground_truth_available: false`，不得填写 IoU、J 或 F。

## 恢复方式

新环境先克隆仓库，再按 `docs/operations/environment-inventory.md` 和各 checkpoint 的命令准备 WSL、SAM2 与权重。权重和实验媒体不从 GitHub 恢复，必须从其官方或已登记来源重新获取并校验哈希。

GitHub Actions 只做无需 GPU 的仓库完整性与 Python 语法检查，不能替代 WSL GPU 回归。
