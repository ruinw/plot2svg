# 方案包: phase2-ocr-thresholds-1

```yaml
@feature: phase2-ocr-thresholds-1
@created: 2026-04-12
@type: implementation
@mode: R2
@selected_option: 2
```

## 1. 需求

### 背景
`Phase 2` 已经在 `graph_builder.py`、`detect_structure.py` 和 `stroke_detector.py` 落下了多批阈值治理。下一步切到 `ocr.py`，先从两类最核心、最容易验证的阈值开始：早停置信度和像素方差过滤。

### 目标
- 扩展 `ThresholdConfig`
- 将 `ocr.py` 中以下阈值接入配置层：
  - `_EARLY_EXIT_CONFIDENCE`
  - `_MIN_PIXEL_STD`
- 保持默认行为不变

### 约束条件
- 本轮只处理这两类 OCR 阈值，不扩展到 overlay bbox 或文本框合并阈值
- 先补测试，再写实现，严格按 TDD 推进
- 继续沿用“隔离 worktree → 定向验证 → 合回 main → 全量测试”的节奏

### 验收标准
- `ThresholdConfig` 新增 OCR 阈值字段
- 默认测试行为不变
- 可以通过自定义阈值改变：
  - OCR 是否在第一轮高置信候选时提前退出
  - 低方差图块是否继续进入 OCR
- 相关测试通过，合回 `main` 后全量测试通过

## 2. 方案

### 技术方案
采用“先接最核心两类阈值”的最小闭环方案：

1. 在 `ThresholdConfig` 中新增：
   - `ocr_early_exit_confidence`
   - `ocr_min_pixel_std`
2. 在 `ocr.py` 中新增一个很轻的阈值读取入口，让 `_read_text_from_bbox()` 使用 `cfg.thresholds`
3. 保持默认值与当前实现一致，确保默认行为不变
4. 用最小测试验证：
   - 自定义较低 early-exit 阈值会减少 OCR engine 调用次数
   - 自定义较低 pixel-std 阈值会放宽低方差图块过滤

### 影响范围
- 修改: `src/plot2svg/config.py`
- 修改: `src/plot2svg/ocr.py`
- 修改: `tests/test_config.py`
- 修改: `tests/test_ocr.py`

### 风险评估
- 风险 1: OCR 这一层直接碰 engine 调用，测试如果写得不稳，很容易变脆
- 风险 2: 如果默认阈值漂移，会影响大量 OCR 相关回归
- 风险 3: 一次接太多 OCR 阈值，会让范围迅速失控

### 关键决策
- 决策 ID: phase2-ocr-thresholds-1#D001
- 决策: 第一批只接 early-exit 和 pixel-std 两个阈值。
- 原因: 这两类阈值最核心，也最容易用稳定测试验证。
