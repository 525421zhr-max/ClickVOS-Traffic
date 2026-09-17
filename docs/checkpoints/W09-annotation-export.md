# 周进度记录：W09 多目标标注下载与 COCO RLE 导出

- 实施日期：2026-09-17
- 对应检查点：CP-04 下载闭环、CP-05 标准标注导出
- 状态：工程实现、格式测试和 W08 真实任务导出完成

## 实际完成

- Web 增加“生成标注下载包”按钮和 ZIP 文件下载组件。
- 支持对已有任务执行 `python -m clickvos.export bundle <task>`。
- 导出逐对象 PNG 掩码、合成预览视频、项目 JSON 和 COCO uncompressed RLE JSON。
- COCO 包含 images、annotations、categories、area、bbox、iscrowd 和扩展 object_id。
- 空掩码帧保留 image 记录但不生成 annotation。
- 导出器兼容 W08 等缺少 `color_rgb`、`mask_directory` 新字段的旧任务记录。
- 新运行的 `result.json` 增加模型名称、配置、权重 SHA-256、offload 设置和峰值 CUDA 显存字段。
- ZIP 明确排除原始视频、抽帧图片、日志和本机绝对路径。

## 可复现命令

```bash
/home/clickvos/.venvs/clickvos/bin/python -m pytest -q

/home/clickvos/.venvs/clickvos/bin/python -m clickvos.export bundle \
  outputs/tasks/9e54b382ef55
```

## 真实导出结果

输入为 W08 已验证的 `traffic-001` 双车辆任务，不重新运行模型。

| 检查项 | 实际值 |
| --- | ---: |
| ZIP 文件 | `clickvos-9e54b382ef55.zip` |
| ZIP 大小 | 505,211 字节 |
| ZIP 条目数 | 103 |
| 对象 1 PNG 掩码 | 50 |
| 对象 2 PNG 掩码 | 50 |
| COCO image 记录 | 50 |
| COCO 非空 annotation | 23 |
| 项目 JSON | 1 |
| COCO RLE JSON | 1 |
| 预览视频 | 1 |
| 自动化测试 | 31 passed in 3.20s |

反向检查确认：ZIP 不含 `frames/`、`source/`，项目 JSON 不含 `/mnt/` 或 `C:\Users` 绝对路径。

## 接受结论与限制

CP-05 工程门通过：多目标任务可以导出为可重读的项目格式和一种标准标注格式，并从网页下载。

本轮验证格式完整性和可重读性，不代表掩码质量达到某个精度。COCO 文件引用原任务帧名，但为控制体积和避免无意传播素材，ZIP 默认不包含抽帧图片；使用者应从有权使用的原视频自行保留对应帧。

## 遇到的问题

首次对 W08 旧任务导出时，`result.json` 尚无 `color_rgb` 和 `mask_directory`，导出器触发 `KeyError`，且没有产生错误 ZIP。随后增加基于对象 ID 的安全默认值，测试与真实导出均通过。

## 本地产物

- `outputs/tasks/9e54b382ef55/exports/clickvos-9e54b382ef55.zip`
- `outputs/tasks/9e54b382ef55/exports/project.json`
- `outputs/tasks/9e54b382ef55/exports/coco_rle.json`

以上运行产物被 Git 忽略。

## 下一步

- 在网页中显示导出包内容摘要和文件大小。
- 增加异常帧定位、确认和逐对象重叠提示。
- 使用带真值的公开小样本验证 COCO 导出后的下游读取流程。
