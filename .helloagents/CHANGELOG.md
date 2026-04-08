## [0.2.11] - 2026-03-17

### ??
- **[object_svg_exporter]**: ???????? bbox?????????????????? 10px ??? OCR ??????????????????
- **[graph_builder]**: ?????? connector polyline ??????????????????????????????
- **[pipeline]**: `region object` ?????????? `container_shape` ????????????????????
- **[tests]**: ????????????????????????????

### ??
- `python -X utf8 -m py_compile src/plot2svg/object_svg_exporter.py src/plot2svg/graph_builder.py src/plot2svg/pipeline.py`
- `python -X utf8 -m pytest tests/test_export_svg.py -k "prunes_text_overlapping_emitted_template_bbox or keeps_lightweight_container_overlapping_text or overlapping_text_box or replaces_panel_arrow_polygon or force_snaps_edge_endpoint" -q` -> 5 passed
- `python -X utf8 -m pytest tests/test_graph_builder.py -k "border_hugging_route or ray_extension_snaps_to_text_node or directionally_snaps_line_that_stops_short_of_nodes" -q` -> 3 passed
- `python -X utf8 -m pytest tests/test_pipeline.py -k "lightweight_container_overlapping_text_bbox or filter_region_objects_drops_region_overlapping_text_bbox" -q` -> 2 passed
- `picture/end_to_end_flowchart.png` -> `outputs/end_to_end_flowchart_round26/`???? `final.svg`?`scene_graph.json`?`preview.png`

## [0.2.10] - 2026-03-17

### ??
- **[object_svg_exporter]**: Round 25 ???????????????? `text` bbox ???? `region/stroke` ??? SVG ??????????????????
- **[object_svg_exporter]**: `panel_arrow` ?????? `<line>` + `marker-end='url(#standard-arrow)'`???????????????
- **[object_svg_exporter]**: ??? connector ?? 40px ???????????????????????? `data-target-id`????????
- **[tests]**: ????????panel_arrow ? polygon?connector ????????????????

### ??
- `python -X utf8 -m py_compile src/plot2svg/object_svg_exporter.py tests/test_export_svg.py`
- `python -X utf8 -m pytest tests/test_export_svg.py -k "overlapping_text_box or replaces_panel_arrow_polygon or force_snaps_edge_endpoint" -q` -> 3 passed
- `picture/end_to_end_flowchart.png` -> `outputs/end_to_end_flowchart_round25/`???? `final.svg`?`scene_graph.json`?`preview.png`

﻿## [0.2.9] - 2026-03-15

### 修复
- **[stroke_detector]**: 为 `dense reconstruction` 增加超大 mask 保护，避免真实样本 `end_to_end_flowchart.png` 中的全图级 stroke supernode 触发高耗时 hub 估计，导致 `detect_strokes(...)` 长时间卡住 — by ruinw
  - 方案: [202603150305_run-end-to-end-flowchart](plan/202603150305_run-end-to-end-flowchart/)

### 验证
- `pytest -q tests/test_stroke_detector.py` -> 10 passed
- `pytest -q tests/test_pipeline.py tests/test_stroke_detector.py` -> 23 passed
- `python -X utf8 -m plot2svg.cli --input picture/end_to_end_flowchart.png --output outputs/end_to_end_flowchart --profile balanced --enhancement-mode auto` -> 成功生成 `final.svg`

## [0.2.8] - 2026-03-13

### ??
- **[stroke_detector]**: ?????????? CLAHE ????????????? contrast/blackhat/adaptive ????????????????????????? Round 18 ? dense-line ?????? ? by Codex

### ??
- `pytest -q tests/test_stroke_detector.py` -> 9 passed
- `python -X utf8 -m plot2svg.cli --input 'picture/a22efeb2-370f-4745-b79c-474a00f105f4.png' --output 'outputs/round19-a22-clahe'`
  - `stroke_primitives`: 51?Round 18: 48?
  - `graph_edges`: 51
  - `raster_objects`: 8


## [0.2.7] - 2026-03-13

### ??
- **[ocr]**: ??????????? mask + `cv2.inpaint(...)`????? OCR ?????????? ? by Codex
- **[segment]**: ???????????? + ???? + ??????????????????????? raster candidate ? by Codex
- **[pipeline]**: ???????? `RasterObject` ??????????? Base64 `<image>` ???? ? by Codex
- **[region_vectorizer]**: ?? pastel ??????????????????????????????????? ? by Codex
- **[object_svg_exporter]**: ?? oversized dark region ????????????/????????? ? by Codex
- **[tests]**: ?? Round 17 ??????? text inpaint?raster fallback?large dark region suppression ? pastel container ?? ? by Codex

### ??
- `pytest -q tests/test_pipeline.py tests/test_export_svg.py tests/test_segment.py tests/test_ocr.py tests/test_region_vectorizer.py` -> 61 passed
- `pytest -q` -> 153 passed
- `picture/F2.png` -> `outputs/F2-round17/` (`raster_objects = 10`, `<image> = 10`)
- `picture/a22efeb2-370f-4745-b79c-474a00f105f4.png` -> `outputs/a22-round17/` (`raster_objects = 8`, `<image> = 8`, `<ellipse> = 2`)



## [0.2.6] - 2026-03-13

### ??
- **[pipeline]**: Round 16 ????????? proposal mask ???????node/stroke ?????????? + `cv2.inpaint(...)`???? stage1 ? stroke ????? `SceneGraph`? by Codex
- **[segment]**: ?? `raster_candidate` ??????????????????????????? by Codex
- **[object_svg_exporter]**: ? `GraphEdge.arrow_head` ??????????????????????????????? by Codex
- **[tests]**: ????????????? inpaint???????????? by Codex

### ??
- `pytest -q tests/test_pipeline.py tests/test_export_svg.py tests/test_segment.py` -> 36 passed
- `pytest -q` -> 150 passed
# CHANGELOG

## [0.2.5] - 2026-03-13

### ??
- **[pipeline]**: ??????? inpaint ????????? `text -> node/icon -> stroke -> region` ????????????? `SceneGraph`??????????????? ? by Codex

### ??
- **[ocr]**: ?? `extract_text_overlays(...)` ? `inpaint_text_nodes(...)`?????????????????? ? by Codex
- **[scene_graph]**: ?? `RasterObject`?????????? raster fallback ???????? `scene_graph.json` ? by Codex

### ??
- **[object_svg_exporter/export_svg]**: ?? raster object ????? `region -> node/raster -> edge -> text` ??????????????????? path ? by Codex
- **[pipeline]**: ?? `debug_text_inpaint.png`?`debug_nodes_inpaint.png`?`debug_strokes_inpaint.png`??? fan/network container ????????????????????? ? by Codex
- **[tests]**: ?? Round 15 ??????? raster object ???/???OCR overlay/inpaint ????????????? ? by Codex

### ??
- `pytest -q tests/test_scene_graph.py tests/test_export_svg.py tests/test_ocr.py tests/test_pipeline.py` -> 52 passed
- `pytest -q` -> 147 passed

## [0.2.4] - 2026-03-13

### ??
- **[stroke_detector]**: ????????????????????????????????????????????? `absorbed_region_ids` ??????????????????? by Codex
  - ??: [202603130011_defensive-debug-topology-repair](plan/202603130011_defensive-debug-topology-repair/)

- **[graph_builder]**: ??????????????????? `stroke_detector` ??????????? `GraphEdge`??????????????????? by Codex
  - ??: [202603130011_defensive-debug-topology-repair](plan/202603130011_defensive-debug-topology-repair/)

- **[object_svg_exporter]**: ?????????/?? -> ?? -> ?? -> fallback -> ??????????????????????????????/??????? by Codex
  - ??: [202603130011_defensive-debug-topology-repair](plan/202603130011_defensive-debug-topology-repair/)

- **[tests]**: ?? Round 13 ?????????????????????????????? fallback/??????? by Codex
  - ??: [202603130011_defensive-debug-topology-repair](plan/202603130011_defensive-debug-topology-repair/)

### ??
- `pytest -q` -> 143 passed
- ????: `outputs/round13_a22_balanced/` ? `outputs/round13_f2_balanced/`

## [0.2.3] - 2026-03-12

### 修复
- **[region_vectorizer]**: 为 `RegionObject` 增加 `entity_valid / reject_reason` 门禁，拦截低对比、近白底、低透明度的背景残渣，停止把幽灵色块继续导出为 region — by ruinw
  - 方案: [202603121840_entity-validity-and-topology-repair](plan/202603121840_entity-validity-and-topology-repair/)

- **[stroke_detector]**: 检测主路径切换为 `adaptive + contrast + blackhat`，并增加连通域噪声过滤，修复淡色背景内低对比线段被全局阈值抹掉的问题 — by ruinw
  - 方案: [202603121840_entity-validity-and-topology-repair](plan/202603121840_entity-validity-and-topology-repair/)

- **[object_svg_exporter]**: 导出层开始跳过 `metadata.entity_valid == false` 的 `RegionObject`，同时保持 legacy fallback 被覆盖抑制 — by ruinw
  - 方案: [202603121840_entity-validity-and-topology-repair](plan/202603121840_entity-validity-and-topology-repair/)

- **[text_layers]**: 文本遮罩从整块矩形切割改为轮廓级填充，降低 label box 背景被 OCR 负掩膜咬坏的风险 — by ruinw
  - 方案: [202603121840_entity-validity-and-topology-repair](plan/202603121840_entity-validity-and-topology-repair/)

- **[segment]**: `_ensure_mixed_component_types(...)` 改为仅在完全无 proposal 时才注入全屏兜底 region/stroke，避免真实样本继续制造背景实体 — by ruinw
  - 方案: [202603121840_entity-validity-and-topology-repair](plan/202603121840_entity-validity-and-topology-repair/)
## [0.2.2] - 2026-03-12

### 修复
- **[region_vectorizer]**: 椭圆拟合改为基于填实后的最大外轮廓，并区分“文本/连线孔洞”与“少量几何孔洞”，修复大型半透明容器在实图中持续退化为 path 碎片的问题 — by ruinw
  - 方案: [202603121407_ellipse-and-low-contrast-stroke-repair](plan/202603121407_ellipse-and-low-contrast-stroke-repair/)

- **[pipeline]**: `vectorize_region_objects(...)` 改为读取原图 `cfg.input_path` 且固定使用原图坐标 `coordinate_scale=1.0`，避免 `graphic_layer` inpaint 破坏填充色后导致椭圆实图识别失效 — by ruinw
  - 方案: [202603121407_ellipse-and-low-contrast-stroke-repair](plan/202603121407_ellipse-and-low-contrast-stroke-repair/)

- **[stroke_detector]**: 新增局部对比度增强、双策略阈值和端点三角形吸附，恢复低对比细线与部分箭头头部 — by ruinw
  - 方案: [202603121407_ellipse-and-low-contrast-stroke-repair](plan/202603121407_ellipse-and-low-contrast-stroke-repair/)

- **[object_svg_exporter]**: `RegionObject.metadata.shape_type == 'ellipse'` 时直接导出 `<ellipse>`，不再强制退回 `<path>` — by ruinw
  - 方案: [202603121407_ellipse-and-low-contrast-stroke-repair](plan/202603121407_ellipse-and-low-contrast-stroke-repair/)

- **[vectorize_region]**: legacy adapter 兼容新的椭圆/孔洞输出，避免复杂有孔区域退化为矩形 fallback — by ruinw
  - 方案: [202603121407_ellipse-and-low-contrast-stroke-repair](plan/202603121407_ellipse-and-low-contrast-stroke-repair/)

## [0.2.1] - 2026-03-11

### 修复
- **[segment]**: 新增基于距离变换和 watershed 的保守实例拆分，并为显式几何对象增加 proposal 合并保护，避免粘连节点和相邻 polygon 过早被吞并 — by ruinw
  - 方案: [202603112358_instance-aware-polygon-repair](archive/2026-03/202603112358_instance-aware-polygon-repair/)
  - 决策: instance-aware-polygon-repair#D001(采用实例级拆分修复粘连对象)

- **[node_detector]**: 从仅识别 circle-like region 升级为同时识别 `circle / triangle / pentagon`，并输出 `shape_type / vertex_count / size` 元数据 — by ruinw
  - 方案: [202603112358_instance-aware-polygon-repair](archive/2026-03/202603112358_instance-aware-polygon-repair/)
  - 决策: instance-aware-polygon-repair#D002(在 metadata 中扩展多边形节点语义)

- **[scene_graph]**: 对象层开始把 `triangle / pentagon` 视为 node-like shape，并放宽高节点密度区域的 `network_container` 判定，修复主样本回归中的容器退化问题 — by ruinw
  - 方案: [202603112358_instance-aware-polygon-repair](archive/2026-03/202603112358_instance-aware-polygon-repair/)

- **[pipeline]**: 保持第八轮对象驱动主链不变，但接收更细粒度 proposal 和 polygon node object，恢复 `a22...png` 的 `network_container` 对象层结果 — by ruinw
  - 方案: [202603112358_instance-aware-polygon-repair](archive/2026-03/202603112358_instance-aware-polygon-repair/)
## [0.2.0] - 2026-03-11

### 新增
- **[stroke_detector]**: 新增对象驱动 stroke 检测与 polyline 追踪，将 connector / edge 从 contour 填充碎片提升为显式 `StrokePrimitive` — by ruinw
  - 方案: [202603111949_object-driven-vector-reconstruction](archive/2026-03/202603111949_object-driven-vector-reconstruction/)

- **[node_detector]**: 新增 node primitive 检测，基于圆检测与圆度过滤生成显式 `NodeObject` — by ruinw
  - 方案: [202603111949_object-driven-vector-reconstruction](archive/2026-03/202603111949_object-driven-vector-reconstruction/)

- **[region_vectorizer]**: 新增 mask-based、hole-aware 的区域对象重建，输出 `RegionObject` 供对象驱动导出使用 — by ruinw
  - 方案: [202603111949_object-driven-vector-reconstruction](archive/2026-03/202603111949_object-driven-vector-reconstruction/)

- **[graph_builder]**: 新增 graph 拓扑重建，把 stroke primitive 端点锚定到 node / label anchor，生成显式 `GraphEdge` — by ruinw
  - 方案: [202603111949_object-driven-vector-reconstruction](archive/2026-03/202603111949_object-driven-vector-reconstruction/)

- **[object_svg_exporter]**: 新增对象驱动 SVG 导出器，按 `regions -> edges -> nodes -> text` 顺序输出最终 SVG — by ruinw
  - 方案: [202603111949_object-driven-vector-reconstruction](archive/2026-03/202603111949_object-driven-vector-reconstruction/)

### 重构
- **[scene_graph]**: 新增 `StrokePrimitive`、`NodeObject`、`RegionObject`、`GraphEdge` 与对应 `SceneGraph` 字段，把 scene graph 从最小对象层升级为最小对象驱动场景层 — by ruinw
  - 方案: [202603111949_object-driven-vector-reconstruction](archive/2026-03/202603111949_object-driven-vector-reconstruction/)
  - 决策: object-driven-vector-reconstruction#D001(采用对象驱动主链重建而非继续修补 contour 导出)

### 修复
- **[pipeline]**: 接入 `detect_nodes -> vectorize_region_objects -> detect_strokes -> build_graph` 主链，正式从 contour-driven pipeline 切向 object-driven pipeline — by ruinw
  - 方案: [202603111949_object-driven-vector-reconstruction](archive/2026-03/202603111949_object-driven-vector-reconstruction/)

- **[export_svg]**: exporter 改为优先消费对象驱动 primitives，同时保留 `fan` 与 `connector` 兼容元数据，避免历史能力回退 — by ruinw
  - 方案: [202603111949_object-driven-vector-reconstruction](archive/2026-03/202603111949_object-driven-vector-reconstruction/)

- **[vectorize_region]**: 降级为 `RegionObject -> RegionVectorResult` 兼容适配层，不再承担主区域重建职责 — by ruinw
  - 方案: [202603111949_object-driven-vector-reconstruction](archive/2026-03/202603111949_object-driven-vector-reconstruction/)

- **[vectorize_stroke]**: 降级为 `StrokePrimitive -> StrokeVectorResult` 兼容适配层，不再承担主 stroke 重建职责 — by ruinw
  - 方案: [202603111949_object-driven-vector-reconstruction](archive/2026-03/202603111949_object-driven-vector-reconstruction/)

## [0.1.6] - 2026-03-11

### 重构
- **[scene_graph]**: 新增 `SceneObject`、`SceneGraph.objects` 与 `build_object_instances(...)`，在 OCR 后先构建最小对象实例层，再交给 group/relation 兼容链消费，阻断标题误吸附与大容器误识别的根因链路 — by ruinw
  - 方案: [202603111912_object-instance-layer-refactor](archive/2026-03/202603111912_object-instance-layer-refactor/)

### 修复
- **[pipeline]**: 在主干流程中接入 `build_object_instances(...)`，把对象层插入到 `populate_text_nodes(...)` 与 `promote_component_groups(...)` 之间，停止继续依赖纯 node/group 补丁链 — by ruinw
  - 方案: [202603111912_object-instance-layer-refactor](archive/2026-03/202603111912_object-instance-layer-refactor/)

- **[detect_structure]**: `box` 分类开始读取对象层元数据，跳过 `network_container / cluster_region`，避免大型网络容器继续误标为普通 box — by ruinw
  - 方案: [202603111912_object-instance-layer-refactor](archive/2026-03/202603111912_object-instance-layer-refactor/)

- **[export_svg]**: 导出层补充 `data-object-id` / `data-object-type`，使对象层识别结果可在最终 SVG 中直接核对 — by ruinw
  - 方案: [202603111912_object-instance-layer-refactor](archive/2026-03/202603111912_object-instance-layer-refactor/)

## [0.1.5] - 2026-03-11

### 新增
- **[text_layers]**: 新增文字/图形分层预处理，输出 `text_mask / text_layer / graphic_layer` 调试产物，为后续图形矢量化提供去字后的图层 — by ruinw

### 修复
- **[pipeline]**: 接入 graphic-only 矢量化链路，但保留 proposal 走原图，避免在吸收外部参考工具时回退已有 connector / fan 关系检测 — by ruinw

- **[segment]**: `propose_components(...)` 支持单独 `text_image_input`，保证文本候选仍能从原图补提，不因去字预处理而丢失 — by ruinw

## [0.1.4] - 2026-03-11

### 重构
- **[scene_graph]**: 放宽 connector 候选提升规则，开始覆盖对角线、短箭头和部分折线 stroke，为普通连接关系进入 relation 层提供入口 — by ruinw
  - 方案: [202603111646_connector-relation-refactor](archive/2026-03/202603111646_connector-relation-refactor/)

### 修复
- **[detect_structure]**: 为普通 connector 生成 `SceneRelation(relation_type='connector')`，不再只有 `fan` 进入关系层 — by ruinw
  - 方案: [202603111646_connector-relation-refactor](archive/2026-03/202603111646_connector-relation-refactor/)

- **[export_svg]**: connector group 改为优先按 relation 重建干净连接线/箭头，并补充 `data-relation-type='connector'` 元数据 — by ruinw
  - 方案: [202603111646_connector-relation-refactor](archive/2026-03/202603111646_connector-relation-refactor/)

## [0.1.3] - 2026-03-11

### 重构
- **[scene_graph]**: 新增 `SceneRelation` 与 `SceneGraph.relations`，把连接关系从 group 兼容层中拆出来，为关系优先导出提供数据入口 — by ruinw
  - 方案: [202603111305_relation-layer-refactor](archive/2026-03/202603111305_relation-layer-refactor/)

### 修复
- **[detect_structure]**: `fan` 检测现在会同步产出 `fan relation`，不再只停留在 group 级启发式结果 — by ruinw
  - 方案: [202603111305_relation-layer-refactor](archive/2026-03/202603111305_relation-layer-refactor/)

- **[export_svg]**: `fan` 导出切换为 relation-first，并补充 `data-relation-id` / `data-relation-type` 元数据，便于主样本回归检查连接结构 — by ruinw
  - 方案: [202603111305_relation-layer-refactor](archive/2026-03/202603111305_relation-layer-refactor/)

## [0.1.2] - 2026-03-11

### 修复
- **[vectorize_region]**: 为复杂填充区域增加孔洞检测，并改用 `fill-rule='evenodd'` 路径输出，防止主样本大轮廓和团块被错误简化为单个圆/椭圆 — by ruinw
  - 方案: [202603111200_vector_structure_repair](archive/2026-03/202603111200_vector_structure_repair/)

- **[detect_structure]**: 新增 `fan` 结构检测，识别“左侧多圆点源节点 + 中央汇聚线束 + 右侧目标框”的扇形关系 — by ruinw
  - 方案: [202603111200_vector_structure_repair](archive/2026-03/202603111200_vector_structure_repair/)

- **[export_svg]**: 为 `fan` 结构新增专用导出重建，避免继续直接输出单个超长原始 `stroke` — by ruinw
  - 方案: [202603111200_vector_structure_repair](archive/2026-03/202603111200_vector_structure_repair/)

## [0.1.1] - 2026-03-11

### 修复
- **[pipeline]**: 修复小图超分后的 proposal / OCR / vectorize 坐标系不一致问题，避免节点越界和错误裁切 — by ruinw
  - 方案: [202603110214_vector_quality_repair](archive/2026-03/202603110214_vector_quality_repair/)

- **[analyze]**: 将 `signature_lineart` 路由从文件名强匹配改为文件名提示 + 图像内容校验，避免 `orr_signature.png` 这类非签名图误判 — by ruinw
  - 方案: [202603110214_vector_quality_repair](archive/2026-03/202603110214_vector_quality_repair/)

- **[segment]**: 为 Hough 圆形注入增加局部轮廓验证，显著降低 `F2.png` 中的误注入圆形节点 — by ruinw
  - 方案: [202603110214_vector_quality_repair](archive/2026-03/202603110214_vector_quality_repair/)

- **[scene_graph]**: 为 region 节点从原图抽样 `fill / stroke / fill_opacity`，修复导出结果长期退化为白底黑线的问题 — by ruinw
  - 方案: [202603110214_vector_quality_repair](archive/2026-03/202603110214_vector_quality_repair/)

- **[vectorize_region]**: 优先按填充区域掩膜提取轮廓，并保留透明填充输出，提升彩色与半透明区域的视觉还原 — by ruinw
  - 方案: [202603110214_vector_quality_repair](archive/2026-03/202603110214_vector_quality_repair/)

- **[detect_shapes]**: 新增 SVG primitive 透明填充支持，保证 `circle / ellipse / rect / polygon / path` 输出 `fill-opacity` — by ruinw
  - 方案: [202603110214_vector_quality_repair](archive/2026-03/202603110214_vector_quality_repair/)

- **[export_svg/object_svg_exporter]**: 连线导出改为标准 line/polyline + SVG marker 箭头，移除手工 edge-arrow 多边形；根 SVG 注入 standard-arrow defs；模板上下文替换逻辑继续保留。 [type: refactor] [files: src/plot2svg/export_svg.py, src/plot2svg/object_svg_exporter.py, tests/test_export_svg.py]

