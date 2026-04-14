# 方案包: phase4-stroke-refine-1

```yaml
@feature: phase4-stroke-refine-1
@created: 2026-04-14
@type: implementation
@mode: R3
@selected_option: 2
```

## 1. 需求

### 背景
`Phase 4` 的 `stroke_detector` 还存在两类明显问题：一类是箭头方向误判，另一类是更弱对比度的单条长线会被误拆成 dense-lines 多段结果。

### 目标
- 阻止反向三角形被误识别成箭头
- 让弱对比度单条长线优先保持为单条折线，而不是被误拆成 dense-lines

### 约束条件
- 本轮只处理箭头方向验证与 dense-lines 误拆分
- 不扩展到交叉点局部 Hough 重构
- 先补测试，再写实现，严格按 TDD 推进

### 验收标准
- 反向三角形不再被吸收为箭头
- 弱对比度单条长线只输出单个 primitive
- 现有 dense fan 重建测试仍通过

## 2. 方案

### 技术方案
采用“两点修补”的最小方案：

1. 在端点三角形吸收逻辑中补充“候选 tip 必须贴近折线端点”的方向约束
2. 在 dense reconstruction 入口前增加“长而单一 spine”场景的跳过逻辑
3. 保持现有 fan dense-lines 重建逻辑不变

### 影响范围
- 修改: `src/plot2svg/stroke_detector.py`
- 修改: `tests/test_stroke_detector.py`

### 风险评估
- 风险 1: 箭头 tip 贴近约束过严会漏掉真实箭头
- 风险 2: dense-lines 跳过条件过宽会误伤真正的扇形密集连线

### 关键决策
- 决策 ID: phase4-stroke-refine-1#D001
- 决策: 本轮优先修正“误判”和“误拆”，不扩大到交叉点路径重构。
- 原因: 这两项最容易形成稳定测试闭环，也最符合当前阶段目标。
