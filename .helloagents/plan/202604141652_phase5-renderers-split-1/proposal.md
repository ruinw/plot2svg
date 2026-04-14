# 方案包: phase5-renderers-split-1

```yaml
@feature: phase5-renderers-split-1
@created: 2026-04-14
@type: implementation
@mode: R3
@selected_option: 1
```

## 1. 需求

### 背景
`Phase 5` 的目标是把 `object_svg_exporter.py` 继续拆分，让不同类型的 SVG 渲染逻辑进入独立模块，同时保持现有导出行为不变。

### 目标
- 新建 `renderers/` 目录
- 拆分 region / object / edge / text 渲染逻辑
- 保持 `export_object_scene_graph()` 对外行为不变

### 约束条件
- 本轮优先完成渲染逻辑拆分，不改变现有 SVG 语义
- 先补测试，再写实现，严格按 TDD 推进
- 现有 `tests/test_export_svg.py` 必须继续通过

### 验收标准
- `object_svg_exporter.py` 明显瘦身
- 新增 renderer 模块可直接导入并产出与现有一致的 SVG 片段
- 相关测试通过

## 2. 方案

### 技术方案
采用“保留 orchestration、拆出 renderers”的最小重构方案：

1. 新建 `src/plot2svg/renderers/`
2. 将 region 渲染逻辑拆到 `region_renderer.py`
3. 将 icon / raster / node 渲染逻辑拆到 `object_renderer.py`
4. 将 edge 渲染逻辑拆到 `edge_renderer.py`
5. 将 text 渲染逻辑拆到 `text_renderer.py`
6. `object_svg_exporter.py` 保留 orchestration 和模板分组相关逻辑，直接调用新 renderer

### 影响范围
- 新建: `src/plot2svg/renderers/__init__.py`
- 新建: `src/plot2svg/renderers/common.py`
- 新建: `src/plot2svg/renderers/region_renderer.py`
- 新建: `src/plot2svg/renderers/object_renderer.py`
- 新建: `src/plot2svg/renderers/edge_renderer.py`
- 新建: `src/plot2svg/renderers/text_renderer.py`
- 修改: `src/plot2svg/object_svg_exporter.py`
- 新建: `tests/test_renderers.py`

### 风险评估
- 风险 1: 拆分时 helper 依赖容易断裂
- 风险 2: 私有函数迁移后，现有测试可能仍依赖旧模块内的名字

### 关键决策
- 决策 ID: phase5-renderers-split-1#D001
- 决策: 先拆 renderers，保留 `object_svg_exporter.py` 作为 orchestration 壳。
- 原因: 这样能最大程度保证行为不变，同时让文件体量快速下降。
