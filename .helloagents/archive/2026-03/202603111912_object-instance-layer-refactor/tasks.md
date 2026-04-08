# 任务清单: object-instance-layer-refactor

> **@status:** completed | 2026-03-11 19:26

```yaml
@feature: object-instance-layer-refactor
@created: 2026-03-11
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 5/5 (100%) | 更新: 2026-03-11 20:05:00
当前: 第七轮对象实例优先改造、测试验证与知识库同步已完成，准备归档方案包
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 5 | 0 | 0 | 5 |

---

## 任务列表

### 7. Object Instance First 主体实例层改造

- [√] 7.1 在 `.helloagents/plan/202603111912_object-instance-layer-refactor/` 中固化第七轮方案，明确对象层边界 | depends_on: []
- [√] 7.2 在 `tests/test_scene_graph.py`、`tests/test_detect_structure.py`、`tests/test_pipeline.py` 中补对象层失败测试 | depends_on: [7.1]
- [√] 7.3 在 `src/plot2svg/scene_graph.py` 中新增最小对象层数据模型与对象构建逻辑，并阻止顶部标题误吸附到大容器 | depends_on: [7.2]
- [√] 7.4 在 `src/plot2svg/detect_structure.py`、`src/plot2svg/export_svg.py`、`src/plot2svg/pipeline.py` 中接入对象层元数据，避免大型网络容器继续误标为普通 box | depends_on: [7.3]
- [√] 7.5 执行定向测试与 `pytest -q`，同步 `.helloagents` 文档与进度记录 | depends_on: [7.4]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-11 19:14:00 | 7.1 | completed | 已创建 `.helloagents/plan/202603111912_object-instance-layer-refactor/` 并固化对象实例优先方案 |
| 2026-03-11 19:32:00 | 7.2 | completed | 已补 `SceneObject`、对象层 box 规避、SVG 对象元数据与 pipeline 对象输出的回归测试 |
| 2026-03-11 19:48:00 | 7.3 | completed | 已在 `scene_graph.py` 中新增 `SceneObject` / `SceneGraph.objects` / `build_object_instances(...)`，并阻断顶部标题误吸附 |
| 2026-03-11 19:56:00 | 7.4 | completed | 已在 `pipeline.py`、`detect_structure.py`、`export_svg.py` 接入对象层元数据，避免大型网络容器继续误标为普通 box |
| 2026-03-11 20:05:00 | 7.5 | completed | 已完成定向测试与全量 `pytest -q`，结果为 `112 passed, 1 warning`，并同步 `.helloagents` 文档 |

---

## 执行备注

> 本轮不再继续阈值微调；优先目标是让主样本从“node/group/relation 补丁链”升级到“最小对象层约束链”。
