# 方案包: phase4-ocr-layout-1

```yaml
@feature: phase4-ocr-layout-1
@created: 2026-04-14
@type: implementation
@mode: R3
@selected_option: 2
```

## 1. 需求

### 背景
`Phase 4` 最后一条线是 OCR 文本定位。当前问题主要有两类：一是 overlay bbox 偏大，二是多行文字被压成一行导出。

### 目标
- 收紧 OCR overlay bbox
- 保留多行文本的换行结构
- 导出时使用 `<tspan>` 按行输出

### 约束条件
- 本轮只处理 bbox 收紧和多行文本导出
- 不扩展到更大范围的 OCR 模型或布局重构
- 先补测试，再写实现，严格按 TDD 推进

### 验收标准
- OCR overlay bbox 会根据实际前景收紧
- `_read_text_from_bbox()` 在多行情形下可返回带换行的文本
- `_render_text_node()` 对多行文本输出 `<tspan>`

## 2. 方案

### 技术方案
采用“双点修补”的最小方案：

1. 在 OCR overlay 生成后，依据图像中的实际墨迹区域对 bbox 做收紧
2. 多行 OCR 读取保留换行，而不是直接用空格拼接
3. 文本导出层识别换行并输出 `<tspan>`，基于 bbox 高度估算行距

### 影响范围
- 修改: `src/plot2svg/ocr.py`
- 修改: `src/plot2svg/object_svg_exporter.py`
- 修改: `tests/test_ocr.py`
- 修改: `tests/test_export_svg.py`

### 风险评估
- 风险 1: bbox 收紧过头会裁掉字符边缘
- 风险 2: 多行导出若行距估算不稳，可能造成行间重叠

### 关键决策
- 决策 ID: phase4-ocr-layout-1#D001
- 决策: 本轮只做 bbox 收紧和多行 `<tspan>` 导出，不做 OCR 引擎层面的替换。
- 原因: 这样能用最小改动把 `Phase 4` 的 OCR 目标补齐。
