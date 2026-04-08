# 任务清单: relation_layer_refactor

> **@status:** completed | 2026-03-11 13:18

```yaml
@feature: relation_layer_refactor
@created: 2026-03-11
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 5/5 (100%) | 更新: 2026-03-11 13:20:00
当前: 已完成第四轮关系层改造、全量测试与知识库同步
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 5 | 0 | 0 | 5 |

---

## 任务列表

### 4. 关系层改造

- [√] 4.1 创建第四轮方案包，明确“最小关系层 + 关系优先导出”的改造边界 | depends_on: []
- [√] 4.2 在 `tests/test_scene_graph.py`、`tests/test_detect_structure.py`、`tests/test_pipeline.py` 中补关系层失败测试 | depends_on: [4.1]
- [√] 4.3 在 `src/plot2svg/scene_graph.py` 中新增 `SceneRelation` 与 `SceneGraph.relations` 序列化 | depends_on: [4.2]
- [√] 4.4 在 `src/plot2svg/detect_structure.py`、`src/plot2svg/export_svg.py` 中实现 fan relation 检测与 relation-first 导出 | depends_on: [4.3]
- [√] 4.5 执行定向测试与 `pytest -q`，并同步 `.helloagents` 文档与进度记录 | depends_on: [4.4]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-11 13:08:00 | 4.1 | completed | 已创建 `.helloagents/plan/202603111305_relation-layer-refactor/` 并填充 proposal/tasks |
| 2026-03-11 13:10:00 | 4.2 | completed | 已补关系层失败测试，确认 `SceneRelation` 缺失导致红灯 |
| 2026-03-11 13:14:00 | 4.3 | completed | 已为 `SceneGraph` 接入 `relations` 并保持多阶段透传 |
| 2026-03-11 13:15:00 | 4.4 | completed | 已为 `fan` 产出 relation，并让 `export_svg` relation-first 导出 |
| 2026-03-11 13:20:00 | 4.5 | completed | `pytest -q` 通过，知识库已同步到第四轮结果 |

---

## 执行备注

> 本轮只解决“连接关系表达缺失”这一核心瓶颈，不把范围扩散到整套图元实例化系统重写。
