# pipeline

职责:

- 串联分析、增强、分割、OCR、对象层构建、图结构重建和 SVG 导出

当前事实:

- 当前主干顺序为：
  - `build_scene_graph`
  - `enrich_region_styles`
  - `populate_text_nodes`
  - `build_object_instances`
  - `promote_component_groups`
  - `detect_structures`
  - `detect_nodes`
  - `vectorize_region_objects`
  - `detect_strokes`
  - `build_graph`
  - `export_svg`
- 第九轮没有改动主链顺序，而是提升了主链输入质量：
  - `segment.py` 现在会先做实例拆分和更保守的 proposal 合并
  - `node_detector.py` 现在会把 triangle / pentagon 也提升为 `NodeObject`
  - `scene_graph.py` 现在会把 polygon node 作为网络对象判定信号
- 2026-03-12 的 P0 收口新增了一个重要约束：
  - `vectorize_region_objects(...)` 必须读取原图 `cfg.input_path`，并固定使用原图坐标 `coordinate_scale=1.0`
  - `detect_nodes(...)` 与 `detect_strokes(...)` 仍继续读取去字后的 `graphic_layer`
  - 原因是区域拟合依赖真实填充色，而 `graphic_layer` 的 inpaint 会破坏半透明容器颜色
- `a22...png` 的最新人工回归结果中：
  - scene graph 包含 2 个 `ellipse` region objects
  - 最终 SVG 已输出 2 个 `<ellipse>` 大容器
- `F2.png` 的最新人工回归结果中，仍保持 `region_objects`、`stroke_primitives` 和 `graph_edges` 正常输出
- 最新全量验证结果已更新为 `130 passed, 1 warning`
