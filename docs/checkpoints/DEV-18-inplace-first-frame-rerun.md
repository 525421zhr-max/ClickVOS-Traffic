# DEV-18：结果区首帧补点与同任务重新传播

- 日期：2026-09-22
- 状态：界面、状态安全、真实 GPU 闭环完成

## 完成内容

- 在传播结果区增加“首帧补点目标”和“首帧补点类型”。
- 用户可直接点击首帧叠加结果，向选定对象追加正点或负点。
- 新增“撤销最后一个补点”；撤销前核对对象 ID、坐标、类型和对象提示点末项，状态不一致时拒绝不安全修改。
- 新增“用补点重新传播”；复用当前任务目录、视频帧、传播设置和更新后的对象提示，不要求返回页面上方。
- 每次传播完成后清空本轮“可撤销补点”记录，防止跨运行误撤销已经生效的提示。
- 增加真实 GPU 验证脚本 `scripts/verify_first_frame_review_rerun.py`。

## 可复现命令

```bash
python scripts/verify_first_frame_review_rerun.py \
  --frames-dir data/raw/davis2017/trainval-road-cars/DAVIS/JPEGImages/480p/car-roundabout \
  --checkpoint /home/clickvos/sam2.1-hiera-tiny-modelscope-20260914/sam2.1_hiera_tiny.pt \
  --output outputs/tasks/web-first-frame-rerun-002
```

脚本把前 10 帧复制到任务隔离目录，先运行 1 正点加 1 负点，再通过结果区回调追加 3 个正点，并在同一任务目录重新运行。默认关闭 ClickVOS 最大连通区域与重新激活保护，避免把后处理混入此工程验证。

## 实际结果

| 项目 | 首次传播 | 结果区补点后重新传播 |
| --- | ---: | ---: |
| 帧数 | 10 | 10 |
| 正点 | 1 | 4 |
| 负点 | 1 | 1 |
| 首帧前景像素 | 8,804 | 56,794 |
| 推理时间 | 1.1450 s | 2.0048 s |

人工查看第 0 帧和第 9 帧：首次传播的已知输入为车门局部；重新传播结果覆盖同一辆灰色汽车的完整车体。对重新传播的中间 8 帧使用官方 DAVIS 实现，实测 J=0.9781、F=0.9611、J&F=0.9696。该 8 帧结果只验证新交互没有破坏 DEV-16 的整车提示效果，不作为独立数据集结论。

本地证据：

- `outputs/tasks/web-first-frame-rerun-002/review-rerun-result.json`
- `outputs/tasks/web-first-frame-rerun-002/davis-metrics.json`
- `outputs/tasks/web-first-frame-rerun-002/exports/preview.mp4`

## 遇到的问题

第一次验证把 DAVIS 原目录的前 10 个路径传给 SAM2，但官方预测器按路径所在目录枚举全部 75 帧；ClickVOS 任务状态只有 10 个条目，因此第 11 帧触发 `IndexError`。这次失败保存在本地 `web-first-frame-rerun-001`，没有计入通过结果。

生产 Web 每次抽帧本来就在独立任务目录中，因此该问题不影响正常上传流程。验证脚本已改为先把选定帧复制到隔离目录，第二次运行严格加载 10 帧并通过。这个现象也说明所有基于 SAM2 目录接口的子集实验都必须隔离帧目录，不能只切片路径列表。

当前仍会出现缺少可选 `sam2._C` 的警告，与 DEV-17 诊断一致；两次传播处于相同环境。

## 验证

- `python -m pytest -q`：`47 passed`
- 源码与脚本编译检查：通过
- 仓库完整性检查：通过
- Impeccable 界面机械检查：无发现项
- 临时 Gradio 服务：HTTP 200，配置中包含“首帧补点目标”“首帧补点类型”“用补点重新传播”；验证后已关闭
