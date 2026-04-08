# 方案包: phase1-bbox-utils

```yaml
@feature: phase1-bbox-utils
@created: 2026-04-08
@type: implementation
@mode: R2
@selected_option: 2
```

## 1. 需求

### 背景
在完成 `inpaint.py` 和 `color_utils.py` 的拆分后，`pipeline.py` 里仍保留一组密集的 bbox 判断工具。这些函数既是后续重构的基础，也让主管线继续承担了过多细节工具逻辑。

### 目标
- 新建 `src/plot2svg/bbox_utils.py`
- 将 `pipeline.py` 里的以下 bbox 工具迁入新模块：
  - `_bbox_overlap`
  - `_bbox_iou`
  - `_bbox_gap`
  - `_contains_bbox`
  - `_expand_bbox`
  - `_clamp_bbox`
  - `_overlaps_existing_region`
  - `_matches_text_bbox`
- 保持 `pipeline.py` 行为不变，并继续让现有测试可用

### 约束条件
- 本轮只处理 `pipeline.py` 中计划内的 bbox 工具，不扩展到其它模块的 bbox 重复收口
- 先补测试，再写实现，严格按 TDD 推进
- 允许 `bbox_utils.py` 直接依赖 `SceneNode` 等当前已有类型，不强行追求“完全通用”

### 验收标准
- `src/plot2svg/bbox_utils.py` 存在并被 `pipeline.py` 复用
- 新增 bbox 工具测试通过
- 相关 `pipeline` 回归测试通过

## 2. 方案

### 技术方案
采用“先抽工具，再回接主管线”的最小改动路径：

1. 新增 `tests/test_bbox_utils.py`，先对 `plot2svg.bbox_utils` 的导入和关键 bbox 判断行为写出失败测试。
2. 新建 `src/plot2svg/bbox_utils.py`，承接上面列出的 bbox 工具函数。
3. `pipeline.py` 改为从 `bbox_utils.py` 导入这些函数，并删除本地重复实现。
4. 保持调用语义与返回值不变，不改业务逻辑。

### 影响范围
- 新增: `src/plot2svg/bbox_utils.py`
- 修改: `src/plot2svg/pipeline.py`
- 新增: `tests/test_bbox_utils.py`

### 风险评估
- 风险 1: `_matches_text_bbox` 和 `_overlaps_existing_region` 这类工具依赖 `SceneNode`，迁移时容易漏类型导入。
- 风险 2: `_clamp_bbox` / `_expand_bbox` 是多处逻辑的底层依赖，一旦边界条件变动会带来连锁影响。
- 风险 3: 现有测试对这些工具没有独立覆盖，必须补测试后再迁移。

### 关键决策
- 决策 ID: phase1-bbox-utils#D001
- 决策: 本轮只提取 `PLAN.md` 明确列出的 `pipeline.py` bbox 工具，不顺手改造其他模块。
- 原因: 这样最符合当前“下一小批”的目标，也能把行为风险控制在可验证范围内。
