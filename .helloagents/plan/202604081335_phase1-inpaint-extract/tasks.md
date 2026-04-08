# 任务清单: phase1-inpaint-extract

```yaml
@feature: phase1-inpaint-extract
@created: 2026-04-08
@status: in_progress
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 4/4 (100%) | 更新: 2026-04-08 14:05:00
当前: 第一批 inpaint 模块拆分已完成并通过针对性验证
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 4 | 0 | 0 | 4 |

---

## 任务列表

### 1. 失败测试

- [√] 1.1 新增 `tests/test_inpaint.py`，先对 `plot2svg.inpaint` 的导入和关键行为写出失败测试 | depends_on: []

### 2. 模块提取

- [√] 2.1 新建 `src/plot2svg/inpaint.py`，迁移 inpaint 主逻辑和最小必要辅助函数 | depends_on: [1.1]
- [√] 2.2 修改 `src/plot2svg/pipeline.py`，改为从 `inpaint.py` 导入相关函数并保持现有调用路径 | depends_on: [2.1]

### 3. 验证

- [√] 3.1 运行相关测试，并用真实图片跑通一次完整流程验证产物生成 | depends_on: [2.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-04-08 13:35:00 | 方案包创建 | completed | 已建立 Phase 1 第一批 inpaint 拆分方案包 |
| 2026-04-08 13:40:00 | 1.1 | completed | 新增 `tests/test_inpaint.py`，先验证模块不存在时确实失败 |
| 2026-04-08 13:55:00 | 2.1 / 2.2 | completed | 新建 `src/plot2svg/inpaint.py` 并将 `pipeline.py` 改为导入调用 |
| 2026-04-08 14:05:00 | 3.1 | completed | 新模块测试、相关 pipeline 回归和真实样本主管线验证均通过 |

---

## 执行备注

- 本轮只推进 `PLAN.md` 中 Phase 1 的第一批最小交付，不扩散到 `color_utils.py` 和 `bbox_utils.py`。
- 现有大量 `pipeline` 内部测试需要兼容，因此本轮会保留函数名与可访问路径的连续性。
- worktree 中不包含被忽略的 `picture/` 数据集，因此较大的图片烟测改用仓库内可用的真实样本路径执行。
