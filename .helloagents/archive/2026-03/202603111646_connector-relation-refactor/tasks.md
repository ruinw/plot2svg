# 任务清单: connector_relation_refactor

> **@status:** completed | 2026-03-11 17:01

```yaml
@feature: connector_relation_refactor
@created: 2026-03-11
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 5/5 (100%) | 更新: 2026-03-11 17:28:00
当前: 已完成第五轮 connector relation 扩展、全量测试与知识库同步
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 5 | 0 | 0 | 5 |

---

## 任务列表

### 5. Connector First 关系层扩展

- [√] 5.1 创建第五轮方案包，明确 connector-first 改造边界 | depends_on: []
- [√] 5.2 在 `tests/test_scene_graph.py`、`tests/test_detect_structure.py`、`tests/test_pipeline.py` 中补 connector relation 失败测试 | depends_on: [5.1]
- [√] 5.3 在 `src/plot2svg/scene_graph.py` 中扩展 connector 候选提升逻辑，覆盖对角/折线 connector | depends_on: [5.2]
- [√] 5.4 在 `src/plot2svg/detect_structure.py`、`src/plot2svg/export_svg.py` 中实现 connector relation 检测与 relation 元数据导出 | depends_on: [5.3]
- [√] 5.5 执行定向测试与 `pytest -q`，同步 `.helloagents` 文档与方案包归档 | depends_on: [5.4]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-11 16:49:00 | 5.1 | completed | 已创建 `.helloagents/plan/202603111646_connector-relation-refactor/` 并填充 proposal/tasks |
| 2026-03-11 16:58:00 | 5.2 | completed | 已补 connector relation 回归测试，锁定普通 connector 未入 relation 层的失败场景 |
| 2026-03-11 17:08:00 | 5.3 | completed | 已放宽 connector 候选提升规则，覆盖更多对角线、短箭头和折线 stroke |
| 2026-03-11 17:16:00 | 5.4 | completed | 已为普通 connector 生成 relation，并在导出层按 relation 重建干净连线与箭头 |
| 2026-03-11 17:28:00 | 5.5 | completed | 定向测试与 `pytest -q` 通过，知识库已同步到第五轮结果 |

---

## 执行备注

> 本轮优先把普通 connector 从“裸 stroke 导出”升级到“显式 relation 导出”，主样本已从 fan-only 升级为 connector + fan relation 共存，但主体实例层仍是下一轮单独问题。
