# 任务清单: sandbox-line-refinement

```yaml
@feature: sandbox-line-refinement
@created: 2026-03-17
@status: pending
@mode: R2
```

<!-- LIVE_STATUS_BEGIN -->
状态: in_progress | 进度: 0/4 (0%) | 更新: 2026-03-17 18:00:00
当前: 正在实现 Slice A 的路径融合与几何重构沙盒实验
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 0 | 0 | 0 | 4 |

---

## 任务列表

### 1. 方案准备
- [ ] 1.1 读取 `slice_A_v2.svg` 结构并确定端点吸附、共线合并与中心修正策略 | depends_on: []

### 2. 实现
- [ ] 2.1 创建 `sandbox_line_refinement.py`，实现路径读取、吸附合并、几何中心估计与 SVG 导出 | depends_on: [1.1]
- [ ] 2.2 创建 `test_sandbox_line_refinement.py`，覆盖脚本执行和关键合并逻辑 | depends_on: [2.1]

### 3. 验证
- [ ] 3.1 运行脚本和测试，确认生成 `debug_04_refined_structure.png` 与 `slice_A_v3.svg`，并检查路径数阈值 | depends_on: [2.2]
