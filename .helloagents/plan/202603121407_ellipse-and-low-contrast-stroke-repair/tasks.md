# 任务清单: ellipse-and-low-contrast-stroke-repair

```yaml
@feature: ellipse-and-low-contrast-stroke-repair
@created: 2026-03-12
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 5/5 (100%) | 更新: 2026-03-12 16:05:00
当前: 已完成主样本/回归验证与知识库同步
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 5 | 0 | 0 | 5 |

---

## 任务列表

### 1. 测试约束

- [x] 1.1 在 `tests/test_region_vectorizer.py` 中新增椭圆区域拟合失败测试 | depends_on: []
- [x] 1.2 在 `tests/test_stroke_detector.py` 中新增低对比细线与箭头吸附失败测试 | depends_on: []

### 2. 实现修复

- [x] 2.1 在 `src/plot2svg/region_vectorizer.py` 中实现椭圆优先拟合与 path 退化逻辑 | depends_on: [1.1]
- [x] 2.2 在 `src/plot2svg/stroke_detector.py` 中实现背景减除、多策略检测和端点箭头吸附 | depends_on: [1.2]

### 3. 回归验证

- [x] 3.1 运行 `picture/a22...png`、`picture/F2.png` 与全量 pytest 回归，并更新知识库文档 | depends_on: [2.1, 2.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-12 14:07:00 | 方案包创建 | completed | 已生成 proposal/tasks 模板 |
| 2026-03-12 14:45:00 | 椭圆/箭头定向测试 | completed | `tests/test_region_vectorizer.py tests/test_stroke_detector.py tests/test_export_svg.py` 通过 |
| 2026-03-12 15:10:00 | 主样本集成排查 | completed | 定位到 `graphic_layer` 破坏区域填充色，导致实图椭圆始终失效 |
| 2026-03-12 15:35:00 | 主链修复 | completed | `pipeline.py` 改为让 `vectorize_region_objects(...)` 读取原图并固定原图坐标 |
| 2026-03-12 16:05:00 | 全量回归与文档同步 | completed | `130 passed, 1 warning`，知识库已更新 |

---

## 执行备注

> 记录执行过程中的重要说明、决策变更、风险提示等

- 当前优先解决椭圆容器崩塌和低对比线条丢失，不在本轮主攻 star 识别。
- 修改和人工测试期间建议关闭 `plot2svg-app`，避免旧 SVG 缓存影响判断。
- 本轮关键根因不是单个阈值，而是区域模块错误读取了去字后的 `graphic_layer`。
- `README.md` 仍存在合并标记，属于独立清理事项，未纳入本轮修复。
