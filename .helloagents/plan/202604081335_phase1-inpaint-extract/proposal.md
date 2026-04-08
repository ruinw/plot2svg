# 方案包: phase1-inpaint-extract

```yaml
@feature: phase1-inpaint-extract
@created: 2026-04-08
@type: implementation
@mode: R3
@selected_option: 1
```

## 1. 需求

### 背景
`pipeline.py` 当前仍为 2109 行，已经明显超出可维护范围。按照 `PLAN.md` 的第一优先级，本轮只推进 Phase 1 的第一批最小可交付改进：先把 inpaint 相关逻辑从 `pipeline.py` 中抽离出来，同时尽量不改变现有行为。

### 目标
- 新建 `src/plot2svg/inpaint.py`，承接 `pipeline.py` 中的 inpaint 相关逻辑。
- 保持主管线现有行为不变，`run_pipeline()` 的输出和现有测试语义不被破坏。
- 让 `pipeline.py` 的职责更偏向编排，减少一段高度耦合的图像擦除实现。

### 约束条件
- 本轮不联动推进 `color_utils.py` 和 `bbox_utils.py` 的全面拆分。
- 为了控制风险，可以在 `inpaint.py` 内临时保留少量重复 helper，后续再统一收口。
- 现有 `tests/test_pipeline.py` 中直接引用这些内部函数，因此兼容层不能断。

### 验收标准
- `src/plot2svg/inpaint.py` 存在，并承接 inpaint 主逻辑。
- 相关单元测试通过，至少覆盖：
  - 新模块可导入。
  - `heal_masked_stage_image` 的关键行为不变。
- 真实图片完整跑通一次，能够正常生成产物。

## 2. 方案

### 技术方案
采用“自包含拆分”的最小交付路径：

1. 在 `tests/` 中先补一个针对 `plot2svg.inpaint` 的失败测试，证明新模块当前尚不存在。
2. 新建 `src/plot2svg/inpaint.py`，迁移以下主函数：
   - `_mask_ignored_regions`
   - `_heal_masked_stage_image`
   - `_mask_for_nodes`
   - `_inpaint_node_and_icon_regions`
   - `_inpaint_stroke_regions`
   - `_erase_region_nodes`
   - `_build_inpaint_mask`
   - `_rasterize_node_mask`
   - `_bbox_mask`
3. 把与这些主函数强耦合的少量辅助逻辑一并迁移到新模块，避免第一批就牵扯过宽：
   - `_panel_background_mask`
   - `_is_exportable_stroke_node`
   - `_should_inpaint_stroke_node`
   - `_merge_masks`
   - `_hex_to_bgr`
   - `_clamp_bbox`
4. `pipeline.py` 改为从 `inpaint.py` 导入这些函数，保留原测试可访问路径。

### 影响范围
- 新增: `src/plot2svg/inpaint.py`
- 修改: `src/plot2svg/pipeline.py`
- 新增: `tests/test_inpaint.py`

### 风险评估
- 风险 1: 辅助函数搬得不全，导致新模块和主管线之间出现遗漏依赖。
- 风险 2: 现有 `tests/test_pipeline.py` 直接引用的内部函数名失效。
- 风险 3: 路径和 mask 逻辑一旦偏移，会导致真实图片输出发生行为漂移。

### 关键决策
- 决策 ID: phase1-inpaint-extract#D001
- 决策: 第一批优先做“自包含的 inpaint 模块拆分”，不在同一轮同时推进颜色和 bbox 通用模块化。
- 原因: 这样既能实质性缩短 `pipeline.py`，又能把本轮行为风险控制在可验证范围内。
