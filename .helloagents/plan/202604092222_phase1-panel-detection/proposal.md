# 方案包: phase1-panel-detection

```yaml
@feature: phase1-panel-detection
@created: 2026-04-09
@type: implementation
@mode: R2
@selected_option: 1
```

## 1. 需求

### 背景
在完成 `inpaint.py`、`color_utils.py` 和 `bbox_utils.py` 后，`pipeline.py` 里仍然保留一段相对独立的 panel 检测逻辑。按照 `PLAN.md` 的 Phase 1.4，本轮继续把这部分从主管线中抽离出来。

### 目标
- 新建 `src/plot2svg/panel_detection.py`
- 将 `pipeline.py` 中 panel 检测相关主函数迁入新模块：
  - `_inject_panel_background_regions`
  - `_detect_panel_background_nodes`
  - `_attach_panel_background_regions`
  - `_detect_panel_arrow_regions`
  - `_estimate_visible_panel_bbox`
  - `_collect_boundary_arrow_boxes`
  - `_merge_nearby_bboxes`
  - `_select_boundary_arrow_boxes`
  - `_synthesize_right_arrow_path`
- 同时迁移只服务于 panel 检测的辅助函数 `_cluster_text_columns`
- 保持主管线行为不变

### 约束条件
- 本轮只处理 panel 检测相关逻辑，不扩展到 `_attach_synthetic_region_nodes` 或其它非 panel 专属逻辑
- 先补测试，再写实现，严格按 TDD 推进
- 继续沿用“隔离 worktree → 定向验证 → 合回 main → 全量测试”的流程

### 验收标准
- `src/plot2svg/panel_detection.py` 存在并被 `pipeline.py` 复用
- 新增 panel_detection 测试通过
- 相关 `pipeline` / `export_svg` 回归测试通过

## 2. 方案

### 技术方案
采用“主函数 + 专属 helper 一起迁移”的最小闭环方案：

1. 新增 `tests/test_panel_detection.py`，先对 `plot2svg.panel_detection` 的导入和关键行为写出失败测试。
2. 新建 `src/plot2svg/panel_detection.py`，迁移 panel 检测主函数与 `_cluster_text_columns`。
3. `pipeline.py` 改为从 `panel_detection.py` 导入这些函数。
4. 保持其它非 panel 专属逻辑原位不动，避免本轮范围扩散。

### 影响范围
- 新增: `src/plot2svg/panel_detection.py`
- 修改: `src/plot2svg/pipeline.py`
- 新增: `tests/test_panel_detection.py`

### 风险评估
- 风险 1: panel 检测依赖 `SceneGraph`、`SceneNode`、`RegionObject` 以及 color/bbox 工具，迁移时容易漏导入。
- 风险 2: `_inject_panel_background_regions` 既是测试入口，也是上游包装函数，若迁移边界不当容易留下半截逻辑在 `pipeline.py`。
- 风险 3: panel arrow 的路径生成和取色逻辑一旦漂移，会影响最终导出结构。

### 关键决策
- 决策 ID: phase1-panel-detection#D001
- 决策: 本轮只提取 panel 检测的闭环逻辑和其专属 helper，不把非 panel 专属的节点附着逻辑一起带走。
- 原因: 这样能最大化减少 `pipeline.py` 体积，同时把行为风险限制在 panel 子系统内部。
