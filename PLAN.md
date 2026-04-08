# Plot2SVG 改进计划

## Context

Plot2SVG 目前处于积极开发调试阶段，核心 pipeline 已经可以运行，但存在以下主要问题：
1. **代码可维护性差** — `pipeline.py` 膨胀至 2109 行（含 60+ 辅助函数），违反单一职责
2. **测试覆盖不均** — 307 个测试中仅 2-3 个真正 E2E，缺乏多样化真实图片验证
3. **大量硬编码阈值** — 分散在各模块中，调参困难，无法按场景微调
4. **重复代码** — 颜色工具函数在 `pipeline.py` 和 `object_svg_exporter.py` 各有一套
5. **输出质量不稳定** — 复杂图表（多层嵌套、密集网络图）的 SVG 输出存在误检/漏检

本计划按 **优先级从高到低** 排列，每个阶段独立可交付。

---

## Phase 1: 核心拆分 — 解构 pipeline.py（可维护性）

**目标**：将 `pipeline.py`（2109 行）拆分为 ≤500 行/文件的模块，不改变任何行为。

### 1.1 提取 `inpaint.py`（~700 行）

从 `pipeline.py` 抽出所有 inpainting 相关函数：

| 函数 | 行号 | 说明 |
|------|------|------|
| `_heal_masked_stage_image` | 1662 | 核心 inpaint 引擎（环采样+中值填充） |
| `_inpaint_node_and_icon_regions` | 1733 | 节点/图标区域擦除 |
| `_inpaint_stroke_regions` | 1794 | 笔画区域擦除 |
| `_build_inpaint_mask` | 1847 | 构建 inpaint 掩码 |
| `_rasterize_node_mask` | 1859 | 从磁盘加载掩码 |
| `_bbox_mask` | 1883 | 创建 bbox 掩码 |
| `_mask_for_nodes` | 1704 | 从节点创建掩码 |
| `_mask_ignored_regions` | 1654 | 应用忽略掩码 |
| `_erase_region_nodes` | 1813 | 按掩码擦除区域 |

**关键文件**：`src/plot2svg/pipeline.py` → 新建 `src/plot2svg/inpaint.py`

### 1.2 提取 `color_utils.py`（~150 行）

合并 `pipeline.py` 和 `object_svg_exporter.py` 中的重复颜色函数：

- `_bgr_to_hex` / `_hex_to_bgr` / `_is_near_white` / `_is_near_black`
- `_is_light_hex` / `_is_light_container_color`
- `_sample_panel_fill` / `_sample_panel_border_color` / `_sample_arrow_fill_color`
- `object_svg_exporter.py` 中的 `_is_dark_color` / `_is_pure_black_region_fill`

**关键文件**：`pipeline.py` + `object_svg_exporter.py` → 新建 `src/plot2svg/color_utils.py`

### 1.3 提取 `bbox_utils.py`（~120 行）

- `_bbox_overlap` / `_bbox_iou` / `_bbox_gap`
- `_contains_bbox` / `_expand_bbox` / `_clamp_bbox`
- `_overlaps_existing_region` / `_matches_text_bbox`

**关键文件**：`pipeline.py` → 新建 `src/plot2svg/bbox_utils.py`

### 1.4 提取 `panel_detection.py`（~400 行）

panel 背景检测 + 面板箭头检测是独立子系统：

- `_detect_panel_background_nodes` / `_attach_panel_background_regions`
- `_detect_panel_arrow_regions` / `_estimate_visible_panel_bbox`
- `_collect_boundary_arrow_boxes` / `_merge_nearby_bboxes` / `_select_boundary_arrow_boxes`
- `_synthesize_right_arrow_path` / `_panel_background_mask`

**关键文件**：`pipeline.py` → 新建 `src/plot2svg/panel_detection.py`

### 1.5 提取 `semantic_labeling.py`（~400 行）

语义识别逻辑独立：

- `_promote_svg_template_nodes` / `_should_route_template_candidate_to_icon_object`
- `_extract_icon_objects` / `_detect_raster_objects` / `_resolve_semantic_raster_objects`
- `_filter_node_objects` / `_filter_region_objects`
- `_looks_like_data_chart` / `_is_lightweight_text_container`

**关键文件**：`pipeline.py` → 新建 `src/plot2svg/semantic_labeling.py`

### 1.6 重构后 `pipeline.py` 结构

拆分后 `pipeline.py` 应仅保留 ~300 行的 **编排逻辑**：

```python
def run_pipeline(cfg: PipelineConfig) -> PipelineArtifacts:
    # Phase 1: Analysis & Enhancement
    # Phase 2: Text Extraction (OCR + inpaint)
    # Phase 3: Panel Detection
    # Phase 4-6: 3-Stage Processing
    # Phase 7: Scene Graph Assembly
    # Phase 8: Post-Processing (structure, layout, routing)
    # Phase 9: SVG Export
```

加上 `_assemble_scene_graph`、`_choose_processing_sources` 等紧密耦合的编排函数。

### 验证

```bash
# 拆分后每一步都要通过全部测试
pytest tests/ -v
# 确认无行为变更
plot2svg --input picture/F2.png --output output/refactor_test/
# diff 拆分前后的 scene_graph.json 和 final.svg 确保一致
```

---

## Phase 2: 阈值治理 — 消灭硬编码魔法数字

**目标**：将分散在各模块中的 ~100 个硬编码阈值收归 `config.py`，支持按 profile 微调。

### 2.1 扩展 `PipelineConfig`

在 `config.py` 中新增阈值组：

```python
@dataclass
class ThresholdConfig:
    """所有可调阈值的集中管理"""
    # Stroke detection
    stroke_min_length: float = 18.0
    stroke_clahe_clip: float = 2.0
    # Node detection
    node_circularity: float = 0.82
    # OCR
    ocr_early_exit_confidence: float = 0.85
    ocr_min_pixel_std: float = 10.0
    # Region filtering
    region_min_area_ratio: float = 0.001
    # ... 更多
```

### 2.2 按 profile 提供预设

```python
_PROFILE_OVERRIDES = {
    "speed": ThresholdConfig(
        ocr_early_exit_confidence=0.75,
        stroke_min_length=24.0,
    ),
    "quality": ThresholdConfig(
        ocr_early_exit_confidence=0.92,
        stroke_min_length=12.0,
    ),
}
```

### 2.3 逐模块替换

优先处理影响最大的模块（按硬编码数量排序）：

1. `graph_builder.py` — ~15 个阈值
2. `detect_structure.py` — ~10 个阈值
3. `stroke_detector.py` — ~10 个阈值
4. `ocr.py` — ~8 个阈值
5. `detect_shapes.py` — ~8 个阈值
6. `segment.py` — ~8 个阈值
7. `analyze.py` — ~5 个阈值

**关键文件**：`src/plot2svg/config.py` + 上述 7 个模块

### 验证

```bash
# 默认 profile 行为不变
pytest tests/ -v
# 对比 3 个 profile 的输出差异
plot2svg --input picture/F2.png --output output/speed/ --profile speed
plot2svg --input picture/F2.png --output output/quality/ --profile quality
```

---

## Phase 3: 测试加固 — E2E 覆盖与回归基线

**目标**：建立多图片 E2E 回归基线，确保后续改动不破坏输出。

### 3.1 构建 E2E 回归测试

新增 `tests/test_e2e_regression.py`：

- 对 `picture/` 下每张测试图片运行完整 pipeline
- 记录 `scene_graph.json` 的关键指标（节点数、边数、对象数、文本数）
- 验证 SVG 产出的基本结构（有 `<g>` 元素、有 `data-shape-type` 属性）
- 基于 golden snapshot 做回归对比

### 3.2 补充边界测试

| 场景 | 当前状态 | 需要补充 |
|------|----------|----------|
| 纯白图片 | 部分覆盖 | 全 pipeline 空输入 |
| 超大图片 (>4096px) | 未覆盖 | 验证 tiling 路径 |
| 密集网络图 | 未覆盖 | 多节点+多连线 |
| 纯文字无图形 | 未覆盖 | 仅 OCR 路径 |
| 错误格式输入 | 未覆盖 | 损坏图片、非图片文件 |

### 3.3 性能基准

新增 `tests/test_performance.py`：

- 记录各阶段耗时（analyze → enhance → OCR → stage1/2/3 → export）
- 设置合理上界阈值防止性能回退

**关键文件**：`tests/test_e2e_regression.py`（新建）、`tests/test_performance.py`（新建）

### 验证

```bash
pytest tests/test_e2e_regression.py -v
pytest tests/test_performance.py -v --tb=short
```

---

## Phase 4: 输出质量提升 — 矢量化精度

**目标**：提升 SVG 输出的视觉保真度。

### 4.1 region_vectorizer 改进

当前 `region_vectorizer.py` 使用 `cv2.approxPolyDP` 做轮廓简化，对曲线区域（圆角矩形、不规则形状）拟合不佳。

改进方向：
- 引入 **自适应 epsilon**：根据轮廓周长动态调整 `approxPolyDP` 精度
- 对检测为椭圆/圆的区域，直接输出 `<ellipse>` / `<circle>` 而非多边形路径
- 对检测为矩形的区域，输出 `<rect>` 并支持 `rx/ry` 圆角

### 4.2 stroke_detector 改进

当前骨架追踪在交叉点处容易断裂或误连。

改进方向：
- 在交叉点处使用 **局部 Hough** 投票确定走向
- 对 arrowhead 检测增加基于角度的验证（当前仅用面积比）
- 改进低对比度线条检测（当前 CLAHE 参数固定）

### 4.3 text 定位精度

当前 OCR bbox 有时偏大或偏小，导致文字在 SVG 中错位。

改进方向：
- 对 OCR 返回的 bbox 做 **收缩校正**（去掉空白填充）
- 对多行文本块做 **行间距估算**，改进 `<tspan>` 定位

**关键文件**：`src/plot2svg/region_vectorizer.py`、`src/plot2svg/stroke_detector.py`、`src/plot2svg/ocr.py`

### 验证

```bash
pytest tests/ -v
# 用 3+ 张不同类型图片目视对比改进前后 SVG
plot2svg --input picture/F2.png --output output/quality_test/ --profile quality
```

---

## Phase 5: object_svg_exporter 清理（1032 行）

**目标**：拆分并简化 SVG 导出模块。

### 5.1 提取渲染函数

将各类型的渲染逻辑拆分：

- `_render_region_object` + `_render_detail_group_template_override` → `renderers/region_renderer.py`
- `_render_icon_object` + `_render_raster_object` + `_render_raster_template_override` → `renderers/object_renderer.py`
- `_render_graph_edge` + marker 相关 → `renderers/edge_renderer.py`
- `_render_text_node` → `renderers/text_renderer.py`

### 5.2 消除与 pipeline.py 的重复

统一使用 Phase 1 提取的 `color_utils.py`，删除 `object_svg_exporter.py` 中重复的：
- `_is_dark_color` / `_is_pure_black_region_fill` / `_is_light_hex`

**关键文件**：`src/plot2svg/object_svg_exporter.py` → 新建 `src/plot2svg/renderers/` 目录

---

## Phase 6: 可观测性 — 日志与调试

**目标**：用 `logging` 替代 `print()`，增强调试能力。

### 6.1 统一日志

- 替换 `cli.py` 中 3 处 `print()` 为 `logging.info()`
- 在 pipeline 各阶段入口添加 `logger.info("Stage N: ...")` + 耗时记录
- 在 `ocr.py` 的 `except Exception` 处添加 `logger.warning()`

### 6.2 调试输出增强

- 在 `scene_graph.json` 中增加各阶段统计摘要（节点数、文本数、边数等）
- 增加 `--verbose` CLI 参数控制 debug 图片输出

**关键文件**：`src/plot2svg/cli.py`、`src/plot2svg/pipeline.py`、`src/plot2svg/ocr.py`

---

## 执行顺序与依赖

```
Phase 1 (拆分 pipeline.py)  ← 最高优先级，解锁后续所有改进
    │
    ├── Phase 2 (阈值治理)  ← 依赖 Phase 1 的 config 扩展
    │
    ├── Phase 3 (测试加固)  ← 可与 Phase 2 并行
    │
    └── Phase 5 (exporter 清理) ← 复用 Phase 1 的 color_utils
         │
         Phase 4 (质量提升) ← 依赖 Phase 3 的回归基线
         │
         Phase 6 (可观测性) ← 任何时候可做
```

## 风险与注意事项

1. **Phase 1 是纯重构**，必须严格保证行为不变 — 每提取一个模块就跑全量测试
2. **Phase 2 修改签名**，所有调用方都需要适配 — 建议先保留默认值兼容
3. **Phase 4 可能改变输出** — 必须先有 Phase 3 的回归基线才能安全进行
4. `onnxruntime` 和 `onnxruntime-gpu` 冲突问题需在 CI 中分别测试
