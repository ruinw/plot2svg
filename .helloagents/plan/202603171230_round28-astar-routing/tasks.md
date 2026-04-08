# 任务清单: round28-astar-routing

```yaml
@feature: round28-astar-routing
@created: 2026-03-17
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 6/6 (100%) | 更新: 2026-03-17 13:08:00
当前: Round 28 已完成 A* 路由实现、回归测试与样例导出
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 6 | 0 | 0 | 6 |

---

## 任务列表

### 1. 测试与约束

- [√] 1.1 在 `tests/test_graph_builder.py` 中补充 text/template 避障与 panel 非障碍测试 | depends_on: []
- [√] 1.2 在 `tests/test_graph_builder.py` 中补充路由平滑与寻路失败直连降级测试 | depends_on: []

### 2. 路由器实现

- [√] 2.1 新建 `src/plot2svg/router.py`，实现网格化、障碍物映射与带转角惩罚的 A* 搜索 | depends_on: [1.1, 1.2]
- [√] 2.2 在 `src/plot2svg/router.py` 中实现路径平滑、共线点剔除与像素坐标回写 | depends_on: [2.1]

### 3. 拓扑接线

- [√] 3.1 修改 `src/plot2svg/graph_builder.py`，在 source/target 已锚定时接入 `FlowchartRouter` 并保留降级链路 | depends_on: [2.1, 2.2]

### 4. 验证与产物

- [√] 4.1 运行定向测试并重跑样例，输出 `outputs/end_to_end_flowchart_round28/final.svg` | depends_on: [3.1]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-17 12:30:00 | 方案包创建 | completed | 已建立 Round 28 A* 路由方案包 |
| 2026-03-17 12:43:00 | 测试先行 | completed | 新增 3 个路由行为测试并先看失败 |
| 2026-03-17 12:56:00 | 路由器实现 | completed | 已新增 `router.py` 并接入 `graph_builder.py` |
| 2026-03-17 13:08:00 | 验证与样例导出 | completed | 定向回归通过，已生成 `outputs/end_to_end_flowchart_round28/final.svg` |

---

## 执行备注

- 本轮固定采用方案 A：专用 `router.py` 模块 + `graph_builder.py` 接入。
- `panel-region` 永远不是障碍物；`text` 与 `svg-template` 是主要障碍物来源。
- 在 A* 代价中额外加入了轻量边缘惩罚，避免路径再次沿画布底边贴边走线。
- 寻路失败会保底降级为两点直连，避免 connector relation 丢失。
