# scene_graph

职责:

- 根据 proposal 生成中间场景节点
- 构建对象层、分组层和对象驱动原语容器
- 为下游 graph/exporter 保留足够的语义边界

当前事实:

- `SceneGraph` 当前同时承载：
  - `nodes / groups / relations` 兼容层
  - `objects` 最小对象层
  - `stroke_primitives / node_objects / region_objects / graph_edges` 对象驱动主链
- 第九轮起，`build_object_instances(...)` 会把 `triangle / pentagon / circle` 统一视为 node-like shape，而不再只统计圆形
- `label_box` 判定已改为参考 node-like shape 数量，避免多边形节点把普通标签框误抬成复杂对象
- `network_container` 判定已对“面积略小但节点密度高”的区域放宽，避免真实网络容器在实例拆分后退化成若干 `cluster_region`
- 当前最小对象类型仍包括：
  - `title`
  - `label_box`
  - `network_container`
  - `cluster_region`
- `promote_component_groups(...)`、`enrich_region_styles(...)` 与 `detect_structures(...)` 继续透传第八轮原语字段，避免对象驱动主链中途丢失
