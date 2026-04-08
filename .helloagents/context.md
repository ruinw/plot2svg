# 项目上下文

## 目标

`plot2svg` 将 PNG/JPG 等栅格图转换为可编辑 SVG，当前优先级是：

- 先保证视觉还原接近原图
- 再尽量保留可编辑结构

处理链为：

`analyze -> enhance -> segment -> scene_graph -> ocr -> object primitives / graph build -> export_svg`

## 当前技术事实

- 入口是 [pipeline.py](H:\project\plot2svg\src\plot2svg\pipeline.py)
- 路由与小图/宽图判断在 [analyze.py](H:\project\plot2svg\src\plot2svg\analyze.py)
- 组件提议由 [segment.py](H:\project\plot2svg\src\plot2svg\segment.py) 负责
- 场景节点构建与区域样式抽样在 [scene_graph.py](H:\project\plot2svg\src\plot2svg\scene_graph.py)
- 文本识别由 [ocr.py](H:\project\plot2svg\src\plot2svg\ocr.py) 负责
- 区域/笔画 legacy 适配分别在 [vectorize_region.py](H:\project\plot2svg\src\plot2svg\vectorize_region.py) 与 [vectorize_stroke.py](H:\project\plot2svg\src\plot2svg\vectorize_stroke.py)
- 第八轮新增对象驱动主链模块：
  - [stroke_detector.py](H:\project\plot2svg\src\plot2svg\stroke_detector.py)
  - [node_detector.py](H:\project\plot2svg\src\plot2svg\node_detector.py)
  - [region_vectorizer.py](H:\project\plot2svg\src\plot2svg\region_vectorizer.py)
  - [graph_builder.py](H:\project\plot2svg\src\plot2svg\graph_builder.py)
  - [object_svg_exporter.py](H:\project\plot2svg\src\plot2svg\object_svg_exporter.py)
- SVG 原语分类与透明填充输出由 [detect_shapes.py](H:\project\plot2svg\src\plot2svg\detect_shapes.py) 负责

## 当前关键结论

- 项目不是“训练失败”，而是基于 classical CV + scene graph 的工程式重建管线
- 真正的质量瓶颈通常出在：
  - proposal 是否把实例切对
  - node / region / stroke 是否分层成功
  - 主链是否把正确图层喂给正确模块
- 第九轮 P0 收口证明：
  - 单测通过不等于实图有效
  - `graphic_layer` 适合 node/stroke，但不适合依赖真实填充色的 region 拟合

## 当前修复状态

- 已修复小图超分后的坐标映射错误
- 已修复 `signature_lineart` 误路由
- 已压低 `F2.png` 中的误注入 circle hint
- 已为 region 节点增加原图样式抽样，恢复非白色填充和 `fill-opacity`
- 已让 region vectorize 优先按填充区域轮廓重建，而不是一律依赖边缘稿
- 已让 SVG primitive 输出支持 `fill-opacity`
- 已引入对象驱动主链：`detect_nodes -> vectorize_region_objects -> detect_strokes -> build_graph -> export`
- 已完成第九轮 P0 收口：
  - 大型椭圆容器重新输出为 `<ellipse>`
  - 低对比细线重新通过 `contrast+otsu / adaptive` 双策略进入 `stroke_primitives`

## 当前已验证样本

- `picture/a22efeb2-370f-4745-b79c-474a00f105f4.png`
- `picture/F2.png`
- `picture/Gemini_Generated_Image_sw0xj6sw0xj6sw0x.png`
- `picture/orr_signature.png`

## 第九轮补充结果（2026-03-12）

- `region_vectorizer.py`：
  - 椭圆拟合改为基于填实后的最大外轮廓
  - 内部 `irregular` 文本孔洞不再阻断椭圆
  - 少量简单几何孔洞仍保留 path + holes
- `pipeline.py`：
  - `vectorize_region_objects(...)` 重新读取原图 `cfg.input_path`
  - 固定 `coordinate_scale=1.0`
  - `detect_nodes(...)` / `detect_strokes(...)` 继续读取去字后的 `graphic_layer`
- `object_svg_exporter.py`：
  - `RegionObject.metadata.shape_type == 'ellipse'` 时直接输出 `<ellipse>`
- `vectorize_region.py`：
  - legacy adapter 已兼容新的椭圆/孔洞分流，不再把有孔复杂区域退化为矩形 fallback

## 最新人工回归摘要

- 主样本 `a22...png`：
  - scene graph 当前包含 2 个 `ellipse` region objects
  - 最终 SVG 当前包含 2 个 `<ellipse>` 大容器
  - `stroke_primitives` 当前为 16 条
- `F2.png`：
  - `stroke_primitives` 当前为 186 条
  - 同时存在 `contrast+otsu` 与 `contrast+otsu+adaptive` 两类检测路径
  - 已观察到端点箭头吸附元数据 `arrow_absorbed=true`

## 运行建议

- 修改和人工测试期间建议关闭 `plot2svg-app`，避免前端缓存旧 SVG 或占用输出文件
- 当前仓库存在用户侧未收敛改动与 `README.md` 合并标记，后续整理时要单独处理，避免与图像重建主线混改

## 最新验证结果

- 全量测试最近一次结果为 `130 passed, 1 warning`

## 第十一轮补充结果（2026-03-12）

- `region_vectorizer.py`：
  - 新增 `entity_valid / reject_reason` 元数据门禁
  - 通过区域均值、环带对比、接近白底程度、透明度/置信度联合判定，拦截低对比背景残渣
  - 无效 `RegionObject` 保留在 scene graph 中，但供导出层跳过渲染并抑制 legacy fallback
- `stroke_detector.py`：
  - 检测主路径改为 `adaptive + contrast + blackhat`
  - `otsu` 仅在前述路径像素过少时补入
  - 新增连通域噪声过滤，避免自适应阈值把小斑点放大成伪线段
- `text_layers.py`：
  - 文本遮罩由整块 bounding box 改为轮廓级填充
  - 不再用大矩形直接切割 label box 背景
- `segment.py`：
  - `_ensure_mixed_component_types(...)` 收紧为仅在 proposal 完全为空时才注入全屏兜底 region/stroke
- `object_svg_exporter.py`：
  - `metadata.entity_valid == false` 的 region object 不再渲染

## 第十一轮真实样本回归（2026-03-12）

- `outputs/round11_a22_balanced/scene_graph.json`
  - `region_objects=16`
  - `invalid_regions=1`
  - `stroke_primitives=16`
  - `graph_edges=16`
  - 最终 SVG `class='region'` 为 15，说明 1 个无效 region 已被导出层拦截
- `outputs/round11_f2_balanced/scene_graph.json`
  - `region_objects=35`
  - `invalid_regions=0`
  - `stroke_primitives=186`
  - `graph_edges=186`
- 与已有 `round9_*_balanced` 对比：
  - `a22` 的 edge/stroke 计数保持住，同时减少 1 个幽灵 region 输出
  - `F2` 的 edge/stroke 计数保持住，未因 adaptive 主路径回退

## 最新验证结果

- 全量测试最近一次结果为 `134 passed, 1 warning`

## ?????????2026-03-13?

- `segment.py`?
  - proposal ???????? `graphic_layer + text_layer`
  - `text_only` ????????????? `text_like` ??????? `F2.png` ??? `propose_components(...)` ????? 400+ proposal
  - ?? `debug_region_segmentation.png`??????? proposal ??? region
  - ???? proposal ????????? region/stroke
- `text_layers.py`?
  - ?? `blackhat` ???????????????????
  - ??????? `graphic_layer` ??????????? overlay/???????? label box ????? OCR ?????
- `region_vectorizer.py`?
  - `empty-crop / empty-mask / invalid entity` ????? path????? bbox fallback ???
- `stroke_detector.py`?
  - ?? `debug_lines_mask.png` ??
  - ???/????????????????????????
- `pipeline.py`?
  - proposal ???? `proposal_layers.graphic_layer` ? `proposal_layers.text_layer`
  - `detect_strokes(...)` ?? debug mask ??
  - `region_vectorizer` ???????????????/????????? region object

## ???????????2026-03-13?

- `outputs/round12_a22_balanced/`
  - ??? `final.svg`?`debug_lines_mask.png`?`debug_region_segmentation.png`
  - `region_objects` ? 16 ?? 42
  - `ellipse region objects` ? 2 ?? 3
  - `huge arrows(>500 area)` ? 5 ?? 3
  - `rect-like region objects` ? 1 ?? 0
- `outputs/round12_f2_balanced/`
  - ??? `final.svg`?`debug_lines_mask.png`?`debug_region_segmentation.png`
  - `graph_edges` ? 186 ?? 72?`huge arrows(>500 area)` ? 35 ?? 18
  - `region_objects` ? 19????????????????????
  - ? `rect-like region objects` ??????17?????? `F2` ???????????????????

## ??????

- ??????????? `139 passed, 1 warning`

## 2026-03-15 实样本补充：end_to_end_flowchart

- 真实样本 `picture/end_to_end_flowchart.png` 在 `balanced + auto` 下曾卡死于 `detect_strokes(...)`。
- 根因不是前置 OCR / 分割，而是 `stage2` 仅有 1 个几乎覆盖全图的 `stroke` 节点，导致 dense reconstruction 误触发。
- 该节点的 oversized mask 进入 `dense_line_reconstructor` 后，`_detect_lines(...)` 产生 1660 条 raw lines、1169 条 merged lines，随后 hub 估计退化为高耗时路径。
- 当前修复策略是在 `stroke_detector._should_reconstruct_dense_lines(...)` 中为超大 mask 增加保护，避免把整图级 stroke supernode 当作局部 dense fan 处理。
- 修复后基线可在约 24 秒内完成并生成：
  - `outputs/end_to_end_flowchart/scene_graph.json`
  - `outputs/end_to_end_flowchart/final.svg`
- 当前质量结论：结果已可导出，但结构编辑性一般；本样本仍有 `raster_objects = 21`、`stroke_primitives = 1`、`graph_edges = 1`，说明大量内容仍依赖 raster fallback。
