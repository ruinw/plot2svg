# detect_shapes

职责:

- 分类 contour 形状
- 生成 circle / ellipse / rect / polygon / path 等 SVG 原语

当前事实:

- 支持 `circle / ellipse / rectangle / triangle / polygon / irregular` 分类
- `svg_circle`、`svg_ellipse`、`svg_rect`、`svg_polygon` 和 path fallback 都支持 `fill-opacity`
- region vectorize 会通过本模块把填充轮廓尽量转成更稳定的 SVG 原语
