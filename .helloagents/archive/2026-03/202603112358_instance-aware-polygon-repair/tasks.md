# 任务清单: instance-aware-polygon-repair

> **@status:** completed | 2026-03-12 00:50

```yaml
@feature: instance-aware-polygon-repair
@created: 2026-03-11
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 6/6 (100%) | 更新: 2026-03-12 00:45:00
当前: 第九轮实例拆分、polygon 节点升级、样本验证与知识库同步已完成，准备归档方案包
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 6 | 0 | 0 | 6 |

---

## 任务列表

### 9. Round 9 Instance-Aware Polygon Repair

- [√] 9.1 在 `tests/test_segment.py`、`tests/test_pipeline.py` 中补失败测试，覆盖粘连对象拆分、误合并保护与主样本结构回归 | depends_on: []
- [√] 9.2 在 `tests/test_scene_graph.py` 与 `tests/test_node_detector.py` 中补失败测试，覆盖 triangle / pentagon 节点对象识别与 metadata 输出 | depends_on: []
- [√] 9.3 在 `src/plot2svg/segment.py` 中实现基于距离变换和 watershed 的实例级拆分，并收紧 `_find_merge_target` / `_find_record_merge_target` 的几何对象合并门控 | depends_on: [9.1]
- [√] 9.4 在 `src/plot2svg/node_detector.py` 中实现多边形节点识别，输出 `shape_type`、`vertex_count`、`size` 等 metadata，并保持 circle 兼容 | depends_on: [9.2]
- [√] 9.5 在 `src/plot2svg/scene_graph.py`、`src/plot2svg/pipeline.py` 中接入多边形节点语义，确保对象层和网络容器启发式可利用新 shape 信息 | depends_on: [9.3, 9.4]
- [√] 9.6 使用 `./picture` 样本执行回归验证、运行 `pytest`，修复回归后同步 `.helloagents` 文档和归档方案包 | depends_on: [9.5]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-11 23:59:00 | design | completed | 已确认采用“实例拆分优先 + 多边形节点升级 + 合并门控收紧”方案，并生成第九轮 implementation 方案包 |
| 2026-03-12 00:05:00 | 9.1 | completed | 已补 segment / pipeline 红测，锁定粘连拆分和误合并回归 |
| 2026-03-12 00:10:00 | 9.2 | completed | 已新增 polygon node / scene graph 红测，锁定 triangle / pentagon 节点识别需求 |
| 2026-03-12 00:20:00 | 9.3 | completed | 已在 `segment.py` 接入保守的 distance transform + watershed 拆分与几何对象合并保护 |
| 2026-03-12 00:28:00 | 9.4 | completed | 已在 `node_detector.py` 增加 triangle / pentagon 检测，并输出形状元数据 |
| 2026-03-12 00:35:00 | 9.5 | completed | 已让 `scene_graph.py` 把 polygon node 视为 node-like shape，恢复主样本 `network_container` |
| 2026-03-12 00:45:00 | 9.6 | completed | 已完成 `./picture` 样本人工回归与全量 `pytest -q`，结果为 `121 passed, 1 warning` |

---

## 执行备注

> 本轮没有引入外部训练模型，仍保持 OpenCV/NumPy 技术栈。
>
> 手工样本回归显示：`a22...png` 当前已同时输出 `network_container / cluster_region / label_box / title`；`F2.png` 仍保持 `title`、`graph_edges` 和 `region_objects` 正常导出。

