# 方案包: phase1-color-utils

```yaml
@feature: phase1-color-utils
@created: 2026-04-08
@type: implementation
@mode: R2
@selected_option: 1
```

## 1. 需求

### 背景
在完成 `inpaint.py` 拆分后，`pipeline.py` 和 `object_svg_exporter.py` 里仍有一批明显重复或相近的颜色工具逻辑。按照 `PLAN.md` 的 Phase 1.2，本轮需要把这些颜色工具统一出来，继续降低主管线文件的杂糅程度。

### 目标
- 新建 `src/plot2svg/color_utils.py`
- 统一以下颜色工具：
  - `_bgr_to_hex` / `_hex_to_bgr`
  - `_is_near_white` / `_is_near_black`
  - `_is_light_hex` / `_is_light_container_color`
  - `_is_dark_color` / `_is_pure_black_region_fill`
  - `_sample_panel_fill` / `_sample_panel_border_color` / `_sample_arrow_fill_color`
- 保持 `pipeline.py` 与 `object_svg_exporter.py` 的现有行为不变

### 约束条件
- 本轮只做颜色工具统一，不扩散到 bbox 或更广的通用工具拆分
- 为了控制风险，允许 `color_utils.py` 内临时保留少量与 bbox 相关的本地辅助函数
- 先补测试，再写实现，严格按 TDD 推进

### 验收标准
- `src/plot2svg/color_utils.py` 存在并被两处模块复用
- 新增颜色工具测试通过
- 相关 pipeline / export_svg 测试通过

## 2. 方案

### 技术方案
采用“通用颜色工具先统一，场景调用点原地回接”的最小改动方案：

1. 新增 `tests/test_color_utils.py`，先对新模块导入和关键颜色判断行为写出失败测试。
2. 新建 `src/plot2svg/color_utils.py`，承接颜色转换、明暗判断和面板采样函数。
3. `pipeline.py` 和 `object_svg_exporter.py` 改为从 `color_utils.py` 导入相关函数。
4. 保持其余场景逻辑和调用顺序不变，只减少重复实现。

### 影响范围
- 新增: `src/plot2svg/color_utils.py`
- 修改: `src/plot2svg/pipeline.py`
- 修改: `src/plot2svg/object_svg_exporter.py`
- 新增: `tests/test_color_utils.py`

### 风险评估
- 风险 1: `pipeline.py` 中的 panel 采样函数和 bbox 裁剪逻辑存在轻耦合，迁移时容易漏掉边界行为。
- 风险 2: `object_svg_exporter.py` 与 `pipeline.py` 对“深色/浅色”的判定阈值不完全一致，统一时如果选错实现，可能引起微妙行为变化。
- 风险 3: 现有测试没有直接覆盖这些工具，必须补独立测试才能保证这次拆分可控。

### 关键决策
- 决策 ID: phase1-color-utils#D001
- 决策: 优先统一真正通用的颜色工具，同时把 panel/arrow 取色函数也一起纳入 `color_utils.py`，但不在本轮扩展到 bbox 工具模块化。
- 原因: 这样能在一轮内显著减少两处颜色重复逻辑，同时把风险控制在“颜色工具统一”这个单一主题内。
