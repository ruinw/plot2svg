# 方案包: phase3-e2e-regression

```yaml
@feature: phase3-e2e-regression
@created: 2026-04-14
@type: implementation
@mode: R3
@selected_option: 1
```

## 1. 需求

### 背景
`Phase 1` 与 `Phase 2` 已经完成主要代码拆分和阈值治理，但当前测试仍然主要集中在模块级和少量重型 pipeline 用例，缺少一套可复用、可长期维护的 E2E 回归基线。

### 目标
- 新增多图片 E2E 回归测试
- 增补边界输入测试（空白图、超大图、纯文字、错误格式）
- 建立性能预算测试，防止后续回退

### 约束条件
- 继续沿用隔离执行，避免重型 pipeline 测试污染当前 pytest 进程
- 由于 `picture/` 样本目录不在 worktree 内，本轮需要先解决“工作树代码 + 主仓库样本目录”的测试路径问题
- 需要保证新增测试可持续运行，避免直接把超重样本全部塞进常规回归

### 验收标准
- 新增 `tests/test_e2e_regression.py`
- 新增 `tests/test_performance.py`
- 建立 golden snapshot 基线并能做回归比较
- 覆盖空白图、超大图、纯文字、错误格式等边界输入
- 新增测试通过，合回 `main` 后回归验证通过

## 2. 方案

### 技术方案
采用“三层结构”的 Phase 3 方案：

1. 新增测试辅助层，统一解决：
   - worktree 代码导入
   - 主仓库 `picture/` 样本定位
   - subprocess 隔离执行 pipeline
   - 输出摘要与阶段耗时提取
2. 在其上建立 E2E 回归测试：
   - 选取代表性回归样本集（小图、网络图、流程图 / 论文图）
   - 对 scene_graph 指标与 SVG 基本结构做 golden snapshot 比对
3. 补充边界与性能测试：
   - 空白图、纯文字、错误格式、超大图 tiling gate
   - 对代表性样本设置总耗时 / 关键阶段预算

### 回归样本策略
考虑当前 `picture/` 中部分样本过重，本轮回归基线使用“代表性样本集”而不是盲目把全部图片塞进常规套件：

- `orr_signature.png`：小图 / 签名线稿
- `a22efeb2-370f-4745-b79c-474a00f105f4.png`：复杂网络图
- `13046_2025_3555_Fig1_HTML.jpg`：普通论文图或网页图
- 如运行成本允许，再纳入 `end_to_end_flowchart.png`

超重样本 `F2.png` 保留在现有重型 pipeline 用例和单独性能 gate 中，不额外复制到常规 E2E 快照循环。

### 影响范围
- 新建: `tests/e2e_utils.py`
- 新建: `tests/fixtures/e2e_regression_snapshot.json`
- 新建: `tests/test_e2e_regression.py`
- 新建: `tests/test_performance.py`
- 可能修改: `src/plot2svg/benchmark.py`（仅在复用时需要）

### 风险评估
- 风险 1: 若直接对所有 `picture/` 样本做常规回归，测试总时长会失控
- 风险 2: 若继续在 pytest 主进程里跑重型 pipeline，用例稳定性会下降
- 风险 3: golden snapshot 若做得过于脆弱，会导致后续合理改进也频繁误报

### 关键决策
- 决策 ID: phase3-e2e-regression#D001
- 决策: 常规 E2E 回归采用“代表性样本集 + golden snapshot”，而不是对所有图片无差别全量运行。
- 原因: 这样既能建立真实基线，也能保持测试套件长期可运行。
