# 任务清单: defensive-debug-topology-repair

`yaml
@feature: defensive-debug-topology-repair
@created: 2026-03-13
@status: completed
@mode: R3
`

<!-- LIVE_STATUS_BEGIN -->
状态: in_progress | 进度: 0/7 (0%) | 更新: 2026-03-13 00:00:00
当前: 复现 Round 12 的 bbox 实体化、放射线坍塌和低对比拓扑丢失
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 7 | 0 | 0 | 7 |

---

## 任务列表

### 1. 失败复现与测试约束
- [ ] 1.1 为 bbox 禁止实体化补失败测试，覆盖 region fallback 与文本框遮挡回归 | depends_on: []
- [ ] 1.2 为放射线簇分流补失败测试，覆盖 Polygenic 巨三角回归 | depends_on: []
- [ ] 1.3 为低对比线条与箭头尺寸补失败测试，覆盖 debug mask 和箭头面积约束 | depends_on: []

### 2. 实现修复
- [ ] 2.1 重构 segment.py：细线簇分流、文本/矩形框防御过滤、区域分割 debug 输出 | depends_on: [1.1, 1.2]
- [ ] 2.2 重构 
egion_vectorizer.py：禁用 bbox/path fallback 实体化，仅允许真实轮廓进入 RegionObject | depends_on: [1.1]
- [ ] 2.3 重构 stroke_detector.py：低对比增强、轻量细化、箭头尺寸约束、线条 debug 输出 | depends_on: [1.3]
- [ ] 2.4 调整 pipeline.py 与必要导出链路，确保 debug 产物落盘且 proposal 不再回流原始文本框 | depends_on: [2.1, 2.2, 2.3]

### 3. 回归验证
- [ ] 3.1 运行 picture/a22efeb2-370f-4745-b79c-474a00f105f4.png 与 picture/F2.png，输出最新 SVG 和两张 debug 图 | depends_on: [2.4]
- [ ] 3.2 运行 pytest -q 全量回归，并同步知识库与任务状态 | depends_on: [3.1]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-13 00:00:00 | 方案包创建 | completed | 已按方案A建立 Round 12 方案包 |

## 执行备注
- 本轮不再接受“看起来像 region 就先导出再过滤”的策略，防御性分流优先。
- debug 图片是阻断性交付物，不生成则视为本轮未完成。
| 2026-03-13 00:25:00 | Round 12 ???? | completed | ??? bbox fallback?????????????? debug ???? |
| 2026-03-13 00:50:00 | ?????? | completed | ??? segment / text_layers / region_vectorizer / stroke_detector / pipeline ?????? |
| 2026-03-13 01:05:00 | ???? | completed | ??? round12_a22_balanced ? round12_f2_balanced ? final.svg ??? debug ? |
| 2026-03-13 01:15:00 | ?????????? | completed | 139 passed, 1 warning???? debug ????? |
