# vectorize_stroke

职责:

- 将笔画节点转成折线路径

当前事实:

- 支持 `coordinate_scale`
- 第八轮起 `vectorize_strokes(...)` 已从主实现降级为 legacy adapter
- 当前主流程会优先调用 `stroke_detector.py` 生成 `StrokePrimitive`
- `vectorize_strokes(...)` 负责把 `StrokePrimitive.points` 包装回旧的 `StrokeVectorResult`
- stroke 输出已从 contour 路径转向 polyline path，而不是填充碎片
- 使用增强图时不会再直接拿原图 bbox 去错位裁切
