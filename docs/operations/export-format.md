# 标注导出格式

Web 的“生成标注下载包”与以下命令产生相同 ZIP：

```bash
python -m clickvos.export bundle outputs/tasks/<task-id>
```

## 压缩包结构

```text
project.json
annotations/coco_rle.json
preview.mp4
masks/object_001/00000.png
masks/object_002/00000.png
...
```

- `project.json`：ClickVOS 项目格式，包含视频尺寸、FPS、对象 ID、类别、颜色、初始点、逐帧前景像素、异常、保护帧和修正记录。
- `annotations/coco_rle.json`：COCO 结构，`segmentation` 使用 JSON 可读的 uncompressed RLE。
- `preview.mp4`：所有对象的彩色合成预览。
- `masks/object_NNN/`：各对象逐帧 8 位二值 PNG，前景为 255，背景为 0。

COCO `images` 会记录原任务帧名、宽度和高度，但 ZIP 默认不重复打包抽帧图片。无前景的对象帧不创建 `annotation`；`images` 记录仍保留。每条 annotation 额外保留 `object_id`，用于区分同类别的不同实例。

## COCO RLE 约定

- `size` 顺序为 `[height, width]`。
- `counts` 为从背景开始、按列优先（Fortran order）扫描的游程长度数组。
- `area` 为非零掩码像素数。
- `bbox` 为 `[x, y, width, height]`，包含边界像素。
- `iscrowd` 固定为 0。

类别 ID 固定为：车辆 1、行人 2、非机动车 3。

## 隐私与可移植性

标注包不会包含原始上传视频、`frames/` 抽帧目录、任务源文件、日志或本机绝对路径。预览视频和掩码属于用户主动生成的任务结果，下载和对外使用前仍应确认原素材许可证允许相应用途。
