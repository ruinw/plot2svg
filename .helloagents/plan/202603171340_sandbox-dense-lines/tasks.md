# 任务清单: sandbox-dense-lines

```yaml
@feature: sandbox-dense-lines
@created: 2026-03-17
@status: completed
@mode: R2
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 4/4 (100%) | 更新: 2026-03-17 13:45:00
当前: A.png 的高密度连线沙盒实验已完成并生成调试图与 SVG
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 4 | 0 | 0 | 4 |

---

## 任务列表

### 1. 测试
- [√] 1.1 创建最小回归测试，约束脚本生成 skeleton、extracted_lines 和 slice_A.svg | depends_on: []

### 2. 实现
- [√] 2.1 实现 `sandbox_dense_lines.py` 的骨架化与 HoughLinesP 提取 | depends_on: [1.1]
- [√] 2.2 实现线段合并与 `<line>` SVG 导出 | depends_on: [2.1]

### 3. 验证
- [√] 3.1 运行脚本并确认产物存在、SVG 含 `<line>` 标签 | depends_on: [2.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-17 13:40:00 | 方案包创建 | completed | 已建立 A.png 高密度线条沙盒方案包 |
| 2026-03-17 13:42:00 | 测试先行 | completed | 先创建回归测试并验证失败点为脚本缺失 |
| 2026-03-17 13:44:00 | 脚本实现 | completed | 已完成骨架化、HoughLinesP、端点合并与 `<line>` SVG 导出 |
| 2026-03-17 13:45:00 | 验证完成 | completed | `pytest` 与脚本直跑均成功，`debug_02` 已可视化核查 |

---

## 执行备注

- 本轮只修改了 `sandbox/` 目录和当前方案包目录。
- 主线核心代码未做任何改动。
- 当前输出共 33 条 `<line>`，右侧扇出主结构已成形，左下角仍有少量短噪声段可在后续沙盒轮次继续压缩。
