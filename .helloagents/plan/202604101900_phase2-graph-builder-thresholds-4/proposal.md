# 方案包: phase2-graph-builder-thresholds-4

```yaml
@feature: phase2-graph-builder-thresholds-4
@created: 2026-04-10
@type: implementation
@mode: R2
@selected_option: 2
```

## 1. 需求

### 背景
前两批 `Phase 2` 已经让 `ThresholdConfig` 落地，并把 `graph_builder.py` 的 monster stroke、端点吸附、partial edge / text cluster 过滤接入了配置层。下一批继续处理 `graph_builder.py` 里剩余高价值的 routing / obstacle 阈值。

### 目标
- 扩展 `ThresholdConfig`
- 将 `graph_builder.py` 中以下阈值接入配置层：
  - route grid size 相关阈值
  - obstacle padding 相关阈值
  - border-hugging 路径降级判定阈值
- 保持默认行为不变

### 约束条件
- 本轮只处理 routing / obstacle 这一组阈值，不继续扩散到其它模块
- 先补测试，再写实现，严格按 TDD 推进
- 继续沿用“隔离 worktree → 定向验证 → 合回 main → 全量测试”的节奏

### 验收标准
- `ThresholdConfig` 新增这组字段
- `graph_builder.py` 默认行为不变
- 可以通过自定义阈值改变：
  - route grid size 的选择
  - obstacle padding 的覆盖范围
- 相关测试通过，合回 `main` 后全量测试通过

## 2. 方案

### 技术方案
采用“配置骨架继续扩展 + helper 显式传阈值”的最小改动方案：

1. 在 `ThresholdConfig` 中新增：
   - grid size 阈值
   - obstacle padding 阈值
   - border route 判定阈值
2. 修改 `graph_builder.py`
   - `_route_grid_size()` 读取阈值
   - `_attempt_orthogonal_route()` 把阈值传给 `_route_grid_size()` 与 `_populate_router_obstacles()`
   - `_populate_router_obstacles()` 读取 text/shape padding 阈值
   - `_looks_like_failed_border_route()` 读取 border route 判定阈值
3. 用最小测试验证：
   - grid size 可通过阈值改变
   - padding 可通过阈值改变

### 影响范围
- 修改: `src/plot2svg/config.py`
- 修改: `src/plot2svg/graph_builder.py`
- 修改: `tests/test_config.py`
- 修改: `tests/test_graph_builder.py`

### 风险评估
- 风险 1: routing 这段 helper 链比较深，漏传 `thresholds` 很容易让新字段挂空
- 风险 2: border route 阈值如果默认值改偏，会影响已存在的绕路回归
- 风险 3: obstacle padding 直接影响路由结果，测试一定要选“可观察但不脆弱”的断言

### 关键决策
- 决策 ID: phase2-graph-builder-thresholds-4#D001
- 决策: 本轮只接 route grid size / obstacle padding / border route 判定这三组阈值。
- 原因: 这三组最适合继续沿着 `graph_builder` 的小批次治理推进，而且测试边界清晰。
