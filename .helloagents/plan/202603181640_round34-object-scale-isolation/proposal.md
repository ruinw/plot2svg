# 方案包: round34-object-scale-isolation

```yaml
@feature: round34-object-scale-isolation
@created: 2026-03-18
@type: implementation
@mode: R3
@selected_option: 2
```

## 1. 需求

### 背景
上一轮把“全局连线降维为 `<line>/<polyline>`”的方向做对了，但把这种宏观策略直接套到几十像素的局部 icon 上，会把文档/数据库等复杂图标抹成糊块。Round 34 需要明确“按对象尺度隔离”的渲染架构，避免再用一套微观/宏观通吃的处理逻辑。

### 目标
- 保持 `sandbox_text_inpainting.py` 的 Fill-only 局部图标渲染，不引入 `HoughLinesP` 或 `<line>` 逻辑。
- 在主管线中将“局部 icon / 模板节点”和“全局长连线”彻底拆分：
  - 局部 icon 在全局连线提取前先被掩膜移除，避免污染 `stroke_detector`。
  - 全局连线提取后，再执行 remove-strokes 清理，交给 region 通道提取大面状容器。
- 在最终 SVG 中强制保持底到顶的顺序：
  1. RegionPaths
  2. IconObjects
  3. StrokePaths
  4. TextNodes

### 约束条件
- 不破坏 Round 33 沙盒中的图标细节保真策略。
- 不把局部 icon 内部细线错误地交给全局 stroke 通道。
- 尽量复用现有 `stroke_detector.py` 的 `blackhat + skeleton` 能力，不重写整条主管线。

### 验收标准
- `sandbox/sandbox_text_inpainting.py` 保持 Fill-only 方案，不引入 `HoughLinesP`。
- 主管线在连线提取前会清除 `svg_template` 类 icon 区域。
- `svg_template` 节点在合图阶段仍被保留，最终能正常导出模板/图标。
- 回归测试能覆盖：
  - icon cleanup id 收集包含 `svg_template`
  - `assemble_scene_graph` 保留 stage1 的 `svg_template` 节点
  - 导出顺序仍保持 region/icon 在 edge 之前，text 在最顶层

## 2. 方案

### 技术方案
采用“最小侵入修复”的两点改造：

1. 在 `pipeline.py` 增加统一的 icon cleanup id 收集函数。
   - 将 `node_objects`、`raster_objects`、`svg_template` 节点统一视为“局部对象层”。
   - 在 `detect_strokes()` 之前通过 `_inpaint_node_and_icon_regions()` 一并白化。

2. 修正 `pipeline.py::_assemble_scene_graph()` 的保留逻辑。
   - 现状只保留 `node_objects` 和 `raster_objects` 对应的 stage1 节点。
   - Round 34 需要额外强制保留 `svg_template` 节点，否则它们虽然被提前白化，但会在后续合图时消失，无法导出成独立 icon layer。

### 影响范围
- 修改: `src/plot2svg/pipeline.py`
- 修改: `tests/test_pipeline.py`
- 验证: `tests/test_export_svg.py` 定位已有渲染顺序保障
- 沙盒保持: `sandbox/sandbox_text_inpainting.py` 不新增 line/hough 逻辑

### 风险评估
- 若 cleanup id 收集过宽，可能误杀应保留为 region 的结构节点。
- 若合图保留范围过宽，可能带回之前被故意删掉的杂点区域。
- 因此本轮只对白名单 `shape_hint == 'svg_template'` 开放，避免泛化过头。

### 关键决策
- 决策 ID: round34-object-scale-isolation#D001
- 决策: 不改沙盒 icon 路线；只在主管线里补“局部 icon 先清除、后保留导出”的闭环。
- 原因: 用户已经明确指出局部 icon 的 Fill 渲染是正确路线，问题在于主管线尺度混淆，而不是图标渲染策略本身。
