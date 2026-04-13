# 方案包: phase4-region-ellipses-1

```yaml
@feature: phase4-region-ellipses-1
@created: 2026-04-14
@type: implementation
@mode: R3
@selected_option: 2
```

## 1. 需求

### 背景
`Phase 4` 目标是提升 SVG 输出的几何保真度。本轮范围锁定在 `region_vectorizer`，优先让简单圆/椭圆区域尽量直接输出为真实几何元素，而不是退回为通用路径。

### 目标
- 优先提升圆/椭圆区域的几何直出
- 保持复杂带孔区域继续走路径
- 通过新增测试锁定行为

### 约束条件
- 本轮不扩展到矩形 / 圆角矩形
- 本轮不做更大范围的自适应 epsilon 重构
- 先补测试，再写实现，严格按 TDD 推进

### 验收标准
- 简单圆形区域可输出 `<circle>`
- 简单椭圆区域可输出 `<ellipse>`
- 带孔的复杂圆/椭圆区域仍保留路径
- 新增测试通过

## 2. 方案

### 技术方案
采用“保留现有拟合逻辑、补足几何直出链路”的最小方案：

1. 让 `region_vectorizer` 的椭圆拟合结果同时区分 `circle` 和 `ellipse`
2. 在 `vectorize_region.py` 中优先读取 `RegionObject.metadata.shape_type`
3. 在对象导出层中补上 `shape_type == 'circle'` 的直出
4. 不改复杂带孔区域的回退逻辑，避免误判

### 影响范围
- 修改: `src/plot2svg/region_vectorizer.py`
- 修改: `src/plot2svg/vectorize_region.py`
- 修改: `src/plot2svg/object_svg_exporter.py`
- 修改: `tests/test_vectorize_region.py`
- 修改: `tests/test_export_svg.py`

### 风险评估
- 风险 1: 圆/椭圆阈值过松会把带孔或不规则区域误提成几何元素
- 风险 2: 导出层与测试层如果几何分支不一致，会出现一个地方画圆、另一个地方仍走路径

### 关键决策
- 决策 ID: phase4-region-ellipses-1#D001
- 决策: 本轮只补“圆/椭圆几何直出链路”，不重构其它几何类型。
- 原因: 这样最容易验证，也最符合当前用户确认范围。
