# graph_builder

职责:

- 根据 `StrokePrimitive` 与 `NodeObject` 重建显式图拓扑

当前事实:

- 当前会为 `node_objects` 建立主 anchor
- 也会为 `label_box` / `title` 等对象建立辅助 anchor
- 对每条 stroke primitive 取两端点做最近邻锚定，输出 `GraphEdge`
- `GraphEdge` 当前包含：
  - `source_id`
  - `target_id`
  - `path`
  - `backbone_id`
  - `arrow_head`
- 该模块是第八轮 object-driven graph reconstruction 的拓扑主入口
