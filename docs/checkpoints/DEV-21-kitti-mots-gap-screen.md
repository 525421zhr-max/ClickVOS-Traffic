# DEV-21：道路目标标注缺席候选筛选

- 日期：2026-09-23
- 状态：官方标注筛选完成；真实遮挡重现和保护规则误拦截仍未验证

## 目的和边界

DEV-20 的 DAVIS `crossing` 试验没有出现模型连续空掩码后的重现，因此无法判断重新激活保护是否误拦正确目标。本轮按 `docs/research/quality-pilot.md` 的筛选合同，只找具备同一实例 ID 内部缺席区间的道路目标候选。没有下载 RGB、运行 SAM2 或计算 IoU。筛选不会改变 DEV-20 的信息不足结论。

## 输入与可复现命令

- 数据：KITTI MOTS 官方 TXT 标注包，来源及许可见 `docs/research/data-sources.md`；本地 ZIP 不提交 Git。
- 环境：WSL Ubuntu 24.04、Python 3.12.3、PyTorch 2.11.0+cu128；扫描脚本只用 Python 标准库，无 GPU 需求。
- ZIP：4,080,394 字节，SHA-256 `d11c35401be1885d79111f363f861339c733355a776fcd2d9fd095274212049c`。

```bash
mkdir -p data/raw/kitti-mots
curl -L --retry 3 -o data/raw/kitti-mots/instances_txt.zip \
  https://www.vision.rwth-aachen.de/media/resource_files/instances_txt.zip
sha256sum data/raw/kitti-mots/instances_txt.zip
python scripts/scan_mots_gaps.py \
  --archive data/raw/kitti-mots/instances_txt.zip \
  --minimum-gap 3 \
  --output docs/research/screens/dev21-kitti-mots-gap-screen.json
python -m pytest -q
```

## 实际结果

| 项目 | 实际值 |
| --- | ---: |
| 序列 | 21 |
| 出现标注的帧（各序列之和） | 7,927 |
| 出现标注的对象轨迹 | 749 |
| 同 ID 内部连续缺席至少 3 帧的区间 | 59 |
| 其中车辆 / 行人 | 46 / 13 |
| 涉及的不同对象轨迹 | 48 |
| 全项目测试 | 55 通过 |

完整候选清单保存在 `docs/research/screens/dev21-kitti-mots-gap-screen.json`。示例：序列 `0002` 的车辆 ID `1016` 在第 168 帧有标注、第 169–190 帧无标注、第 191 帧再次有标注。此现象**仅说明官方 TXT 里的标注缺席**；也可能与遮挡、截断或标注策略有关，不能直接解释为同一车在画面中真实消失再出现，更不能宣称 SAM2 会触发保护规则。

## 遇到的问题和下一步

- Windows 系统 Python 未安装 pytest；改用现有 WSL 虚拟环境运行，55 项测试通过，无需增加项目依赖。
- WSL 启动时打印 localhost 代理提示；Python 扫描与测试均正常完成。
- 图像尚未取得且许可尚未核对，因此候选没有经过画面检查。下一步先核对 KITTI 原始图像许可、抽取少量候选相邻帧做人工复核；只有确认真实可用场景，才另行冻结小规模 SAM2 运行的提示、预算和判定规则。
