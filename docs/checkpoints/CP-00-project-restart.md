# CP-00：项目重建起点

- 日期：2026-09-09
- 状态：已建立本地目录骨架，并初始化 Git 仓库的 `main` 分支；尚未创建首次提交和远程仓库。
- 已知情况：旧原型代码未保留；申报材料称旧版已具备 Gradio、SAM2 视频传播、ffmpeg 抽帧与 OpenCV 合成能力。
- 本 checkpoint 的目标：不声称旧功能仍可运行；从环境验证开始重新建立可复现证据。

## 下一步

1. 重启 Windows，使 WSL 与虚拟机平台组件生效。
2. 初始化 Ubuntu 24.04 用户，并运行 `scripts/bootstrap_wsl.sh`。
3. 配置 Git 提交邮箱并验证 GitHub 凭据，然后提交、推送本 checkpoint。
