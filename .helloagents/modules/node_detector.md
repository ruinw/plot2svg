# node_detector

职责:

- 将几何 region 提升为显式 `NodeObject`
- 为 graph/object 层补充节点形状元数据

当前事实:

- 第八轮仅识别 circle-like region；第九轮起新增 polygon node detection
- 当前识别顺序为：
  - `shape_hint == 'circle'` 或无 hint 时优先尝试 Hough circle
  - contour threshold + polygon approximation
  - circle circularity fallback
- 当前显式支持的节点形状包括：
  - `circle`
  - `triangle`
  - `pentagon`
- `NodeObject.metadata` 现在会输出：
  - `shape_type`
  - `vertex_count`
  - `size`
  - `shape_hint`
- 该模块现在不仅负责把圆节点显式化，也负责防止多边形节点继续停留在普通 region 兼容层里
