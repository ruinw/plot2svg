# 方案包: phase1-semantic-labeling

```yaml
@feature: phase1-semantic-labeling
@created: 2026-04-09
@type: implementation
@mode: R2
@selected_option: 2
```

## 1. 需求

### 背景
在完成 `inpaint.py`、`color_utils.py`、`bbox_utils.py` 和 `panel_detection.py` 后，`pipeline.py` 里仍保留一整组语义识别逻辑，包括模板提升、raster 判断、icon 提取和语义恢复。这一段已经形成相对独立的子系统，适合继续抽离。

### 目标
- 新建 `src/plot2svg/semantic_labeling.py`
- 将 `pipeline.py` 中以下语义识别主函数迁入新模块：
  - `_filter_node_objects`
  - `_should_route_template_candidate_to_icon_object`
  - `_promote_svg_template_nodes`
  - `_extract_icon_objects`
  - `_detect_raster_objects`
  - `_resolve_semantic_raster_objects`
  - `_filter_region_objects`
  - `_looks_like_data_chart`
  - `_is_lightweight_text_container`
- 同时迁移只服务于这组语义识别逻辑的 helper 和常量
- 保持主管线行为不变

### 约束条件
- 本轮只处理语义识别闭环，不扩展到无关模块
- 先补测试，再写实现，严格按 TDD 推进
- 继续沿用“隔离 worktree → 定向验证 → 合回 main → 全量测试”的流程

### 验收标准
- `src/plot2svg/semantic_labeling.py` 存在并被 `pipeline.py` 复用
- 新增语义识别测试通过
- 相关 `pipeline` 回归测试通过

## 2. 方案

### 技术方案
采用“主函数 + 专属 helper 一起迁移”的最小闭环方案：

1. 新增 `tests/test_semantic_labeling.py`，先对 `plot2svg.semantic_labeling` 的导入和关键行为写出失败测试。
2. 新建 `src/plot2svg/semantic_labeling.py`，迁移语义识别主函数与以下 helper / 常量：
   - `_append_component_role_tag`
   - `_is_template_candidate_bbox`
   - `_texts_within_bbox`
   - `_text_context_near_bbox`
   - `_translate_compound_path`
   - `_looks_like_large_black_artifact`
   - `_CHART_TEXT_KEYWORDS`
3. `pipeline.py` 改为从 `semantic_labeling.py` 导入这些函数。
4. 保持其它非语义识别逻辑原位不动。

### 影响范围
- 新增: `src/plot2svg/semantic_labeling.py`
- 修改: `src/plot2svg/pipeline.py`
- 新增: `tests/test_semantic_labeling.py`

### 风险评估
- 风险 1: 这组逻辑同时依赖 `bbox_utils`、`color_utils`、`IconProcessor`、`vectorize_clean_image` 和模板推断，迁移时容易漏导入。
- 风险 2: `_looks_like_large_black_artifact` 还被 `pipeline.py` 里别的逻辑引用，迁移后需要同步回接，避免断链。
- 风险 3: icon/raster/template 的语义边界一旦漂移，会影响后续导出层级和对象类型。

### 关键决策
- 决策 ID: phase1-semantic-labeling#D001
- 决策: 本轮将语义识别主函数和其专属 helper 一起迁移，连带把 `_looks_like_large_black_artifact` 也纳入同一模块。
- 原因: 这样能形成真正完整的语义识别子模块，避免 `pipeline.py` 里留下只给语义逻辑服务的残余函数。
