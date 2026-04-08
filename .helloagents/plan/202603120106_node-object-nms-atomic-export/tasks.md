# 任务清单: node-object-nms-atomic-export

```yaml
@feature: node-object-nms-atomic-export
@created: 2026-03-12
@status: pending
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: in_progress | 进度: 0/4 (0%) | 更新: 2026-03-12 01:06:00
当前: 编写失败测试并准备对象层修复
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 0 | 0 | 0 | 4 |

---

## 任务列表

### 1. 测试约束

- [ ] 1.1 在 `tests/test_node_detector.py` 中新增对象级 NMS 与三角形朝向失败测试 | depends_on: []
- [ ] 1.2 在 `tests/test_export_svg.py` 中新增多边形节点原子导出失败测试 | depends_on: []

### 2. 实现修复

- [ ] 2.1 在 `src/plot2svg/node_detector.py` 中实现对象级 NMS、三角形朝向 metadata 与相关辅助函数 | depends_on: [1.1]
- [ ] 2.2 在 `src/plot2svg/object_svg_exporter.py` 中实现多边形节点原子导出 | depends_on: [1.2, 2.1]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-12 01:06:00 | 方案包创建 | completed | 已生成 proposal/tasks 模板 |

---

## 执行备注

> 记录执行过程中的重要说明、决策变更、风险提示等

- 主样例诊断显示 `region-hough-*` 圆节点为当前重复节点的主要来源。
- 本轮先修节点对象链路，不扩大到整条线段检测重构。
