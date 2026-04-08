# 方案包: round28-astar-routing

```yaml
@feature: round28-astar-routing
@created: 2026-03-17
@type: implementation
@mode: R3
@selected_option: A
```

## 1. 需求

### 背景
当前 `graph_builder.py` 生成的 `graph_edges` 仍依赖原始 stroke polyline 与失败后的边界直连降级，导致连线存在贴边走、沿底边绕行和转角生硬的问题。Round 28 需要将连线路由从“被动修补”升级为“主动规划”。

### 目标
- 引入轻量级网格化 A* 路由器，替换当前依赖 primitive path 的死板路径。
- 将 `text` 与 `svg-template` 视为主要障碍物，并加入 10-15 像素 padding。
- 明确四大 `panel-region` 不是障碍物，连线可以在背景面板内部穿行。
- 在代价函数中引入转角惩罚，输出更接近人工绘制的正交连线。
- 在导出前保持路径为简化后的关键拐点 polyline，并保留找不到路时的直连降级。

### 约束条件
- 停止通过阈值微调修补连线问题，必须以规则化/语义化路由实现。
- 不破坏现有锚点吸附、monster stroke 熔断与 panel arrow 逻辑。
- 不将 `panel-region-*` 当作障碍物。
- 路由失败时必须保底，避免 `connector` relation 丢失。

### 验收标准
- `tests/test_graph_builder.py` 新增或更新的 A* 路由测试通过。
- 贴边失败路径不再沿画布底边绕行，输出为横平竖直的关键拐点路径。
- 文本框与 `svg-template` 周边出现明显避障效果。
- 重跑样例后，`final.svg` 中的 connector 路由明显优于当前版本，且仍可正确挂载 source/target。

## 2. 方案

### 技术方案
采用“专用路由模块 + 拓扑构建接线”的方案：

1. 在 `src/plot2svg/router.py` 中新增 `FlowchartRouter`。
   - 负责画布网格化。
   - 负责障碍物写入与 panel 豁免。
   - 负责 A* 搜索、转角惩罚、寻路失败降级与共线点剔除。
2. 在 `src/plot2svg/graph_builder.py` 中保留现有锚点吸附与 endpoint snap。
   - 当 source/target 都存在时，改为请求 `FlowchartRouter` 计算正交路径。
   - 继续保留 `_degrade_failed_route()` 作为兜底，但优先使用 A* 结果。
3. 在 `tests/test_graph_builder.py` 中补充以下验证：
   - panel 不作为障碍物。
   - text/template 形成障碍并迫使路径绕行。
   - 路径共线简化后仅保留关键拐点。
   - 路由失败时降级为两点直连。

### 影响范围
- 新增: `src/plot2svg/router.py`
- 修改: `src/plot2svg/graph_builder.py`
- 修改: `tests/test_graph_builder.py`
- 可能重跑样例输出: `outputs/end_to_end_flowchart_round28/`

### 风险评估
- 网格过粗会导致终点贴附偏差；通过 endpoint snap 后再路由、并在结果两端保持锚点边界坐标缓解。
- 障碍 padding 过大可能导致无路可走；通过有限 padding 和直连降级避免阻断。
- A* 状态空间增大可能拖慢测试；通过 10-15 px 网格和四方向搜索控制复杂度。

### 关键决策
- 决策 ID: round28-astar-routing#D001
- 决策: 路由逻辑拆到独立 `router.py`，不继续膨胀 `graph_builder.py`。
- 原因: 便于后续扩展障碍规则、缓存策略和多种 routing profile。
