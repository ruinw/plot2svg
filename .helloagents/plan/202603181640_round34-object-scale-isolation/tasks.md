# 任务清单: round34-object-scale-isolation

```yaml
@feature: round34-object-scale-isolation
@created: 2026-03-18
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: in_progress | 进度: 0/4 (0%) | 更新: 2026-03-18 17:00:00
当前: 创建方案包并准备 Round 34 的失败测试
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 4 | 0 | 0 | 4 |

---

## 任务列表

### 1. 测试约束

- [?] 1.1 在 `tests/test_pipeline.py` 中补充 cleanup id 收集测试，确保 `svg_template` 节点在全局 stroke 提取前会被纳入 icon 清理范围 | depends_on: []
- [?] 1.2 在 `tests/test_pipeline.py` 中补充 stage1 `svg_template` 节点保留测试，确保 `_assemble_scene_graph()` 不会丢失模板 icon | depends_on: []

### 2. 主管线实现

- [?] 2.1 修改 `src/plot2svg/pipeline.py`，增加局部 icon cleanup id 收集逻辑，并接入 `_inpaint_node_and_icon_regions()` | depends_on: [1.1]
- [?] 2.2 修改 `src/plot2svg/pipeline.py`，在 `_assemble_scene_graph()` 中强制保留 stage1 的 `svg_template` 节点 | depends_on: [1.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-18 17:00:00 | 方案包创建 | completed | 已建立 Round 34 对象尺度隔离方案包 |

---

## 执行备注

- 沙盒 `sandbox_text_inpainting.py` 在本轮只作为约束基线，不再引入任何 line/hough 提取逻辑。
- 主管线重点修复“局部图标先清除、后保留导出”的闭环，不额外扩散到未证明有问题的模块。
