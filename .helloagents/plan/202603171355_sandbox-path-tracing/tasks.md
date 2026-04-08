# 任务清单: sandbox-path-tracing

```yaml
@feature: sandbox-path-tracing
@created: 2026-03-17
@status: pending
@mode: R2
```

<!-- LIVE_STATUS_BEGIN -->
状态: in_progress | 进度: 0/4 (0%) | 更新: 2026-03-17 13:55:00
当前: A.png 路径追踪沙盒实验已开始
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 0 | 0 | 0 | 4 |

---

## 任务列表

### 1. 测试
- [ ] 1.1 创建最小回归测试，约束脚本生成 `debug_03_paths.png` 与 `slice_A_v2.svg` | depends_on: []

### 2. 实现
- [ ] 2.1 实现 `sandbox_path_tracing.py` 的骨架化与像素邻域图构建 | depends_on: [1.1]
- [ ] 2.2 实现端点路径追踪与 polyline SVG 导出 | depends_on: [2.1]

### 3. 验证
- [ ] 3.1 运行脚本并确认产物存在、SVG 含 polyline/path 标签 | depends_on: [2.2]
