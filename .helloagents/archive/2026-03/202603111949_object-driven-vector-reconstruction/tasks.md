# 任务清单: object-driven-vector-reconstruction

> **@status:** completed | 2026-03-11 20:16

```yaml
@feature: object-driven-vector-reconstruction
@created: 2026-03-11
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 8/8 (100%) | 更新: 2026-03-11 20:52:00
当前: 第八轮对象驱动主链改造、全量测试与知识库同步已完成，准备归档方案包
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 8 | 0 | 0 | 8 |

---

## 任务列表

### 8. Round 8 Object-Driven Vector Reconstruction

- [√] 8.1 在 `tests/` 中补第八轮失败测试，覆盖 stroke vectorization、graph reconstruction、arrow detection 与对象驱动导出顺序 | depends_on: []
- [√] 8.2 新增 `src/plot2svg/stroke_detector.py`，实现 stroke primitive 检测、polyline 追踪与最小箭头头部识别 | depends_on: [8.1]
- [√] 8.3 新增 `src/plot2svg/node_detector.py`，实现 node primitive 检测与颜色/半径抽样 | depends_on: [8.1]
- [√] 8.4 新增 `src/plot2svg/region_vectorizer.py`，实现 mask-based、hole-aware 的 region object 输出 | depends_on: [8.1]
- [√] 8.5 新增 `src/plot2svg/graph_builder.py`，实现 edge 端点锚定和 `Node ↔ Edge ↔ Node` 重建 | depends_on: [8.2, 8.3]
- [√] 8.6 在 `src/plot2svg/scene_graph.py`、`src/plot2svg/pipeline.py` 中接入 primitive/object/graph 数据主链，保留第七轮 SceneObject 兼容层 | depends_on: [8.2, 8.3, 8.4, 8.5]
- [√] 8.7 在 `src/plot2svg/export_svg.py`、`src/plot2svg/vectorize_region.py`、`src/plot2svg/vectorize_stroke.py`、`src/plot2svg/detect_structure.py` 中切换到对象驱动导出与兼容适配 | depends_on: [8.6]
- [√] 8.8 执行主样本回归、`pytest -q`、知识库同步与方案包归档 | depends_on: [8.7]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-11 20:18:00 | design | completed | 已确认采用“对象驱动主链重建”方案，并生成第八轮 implementation 方案包 |
| 2026-03-11 20:24:00 | 8.1 | completed | 已补 `test_stroke_detector.py`、`test_graph_builder.py` 及对象驱动 exporter / pipeline 回归测试 |
| 2026-03-11 20:31:00 | 8.2 | completed | 已新增 `stroke_detector.py`，生成 `StrokePrimitive(points, width, arrow_head)` |
| 2026-03-11 20:34:00 | 8.3 | completed | 已新增 `node_detector.py`，把 circle-like region 提升为 `NodeObject` |
| 2026-03-11 20:37:00 | 8.4 | completed | 已新增 `region_vectorizer.py`，输出 mask-based、hole-aware 的 `RegionObject` |
| 2026-03-11 20:40:00 | 8.5 | completed | 已新增 `graph_builder.py`，完成 stroke 端点到 node / label anchor 的最小锚定 |
| 2026-03-11 20:44:00 | 8.6 | completed | 已在 `scene_graph.py`、`pipeline.py` 接入第八轮 primitives/object/graph 主链 |
| 2026-03-11 20:48:00 | 8.7 | completed | 已切换 `export_svg.py` 到对象驱动导出，并保留 `fan` 与 legacy adapter 兼容层 |
| 2026-03-11 20:52:00 | 8.8 | completed | 已完成 `pytest -q`，结果为 `117 passed, 1 warning`，并同步 `.helloagents` 文档 |

---

## 执行备注

> 本轮不再继续 contour 导出补丁；核心目标是让 SVG exporter 的输入从 contour 结果切换为 object/graph 结果。
