# Sprint 执行指南（Stage 2.5 → Stage 3）

*最后更新：2026-05-14*

> 本文档是开发者的短期执行手册，不是战略愿景。目标能力 → 对应文件 → 成功判定命令，逐一对应。

---

## Stage 2.5 前置验证（2026-05-13 ✅）

> Day 1 执行记录，逐一打勾：

- [x] **文档一致性检查**：`Registry 中 4 工具 = 文档 4 工具，零漂移**
  ```bash
  uv run python3 scripts/check_doc_consistency.py
  # ✅ 一致性检查通过
  ```
- [x] **全量测试 18/18**：
  ```bash
  uv run pytest tests/ -v
  # 18 passed in 0.19s ✅
  ```
- [x] **真实任务 × 2 全部 success**：
  ```bash
  # 任务1: calculator.py（stdin 计算器）
  # 会话 2026-05-14-003 ✅ success
  # 关键链路: list_files → 写文件 → QA fail → retry → QA pass → Git 快照

  # 任务2: reverse.py（字符串倒序）
  # 会话 2026-05-14-004 ✅ success
  # 关键链路: read_file 工具生效 → parse_error 修复 → QA pass
  ```
- [x] **Stage 3 探针实验**：DeepSeek V4 Flash 精准修复端口 8888→8889 ✅
  ```bash
  # 手动破坏 server_probe.py PORT=8889 → 触发 retry
  # Engineer read_file 定位 → 修复 → QA 通过
  ```

---

## Stage 2.5 当前状态

**已落地** ✅（Day 1 验证完毕）

- [x] Tool/ToolRegistry 抽象
- [x] `read_file` 工具
- [x] `edit_file` 工具
- [x] `search_code` 工具
- [x] `list_files` 工具
- [x] `tool_call` 消息循环
- [x] QA 读源码辅助
- [x] `human_gate` 关卡
- [x] 原子 `status.json` 写入
- [x] 启动孤儿进程清理
- [x] `STRICT_QUEUE_MODE` 开关

**未落地** ⏳

- [ ] **Stage 3: Manager 大循环** ✅ 已实现（2026-05-14）
- [ ] **Stage 3: 主观/客观需求自动分流** ❌

| 能力 | 核心文件 | 成功判定 |
|------|---------|---------|
| Tool/ToolRegistry 抽象 | `opc/tools/__init__.py` | `uv run python3 -c "from opc.tools import get_registry; print(get_registry().list_tools().keys())"` |
| `read_file` 工具 | `opc/tools/file_tools.py` | `uv run python3 -c "from opc.tools import get_registry; print(get_registry().execute('read_file', {'path':'README.md'})[:50])"` |
| `edit_file` 工具 | `opc/tools/file_tools.py` | `uv run python3 -c "from opc.tools import get_registry; print('edit_file' in get_registry().list_tools())"` |
| `search_code` 工具 | `opc/tools/search_tools.py` | `uv run python3 -c "from opc.tools import get_registry; r=get_registry().execute('search_code',{'pattern':'def run_engineer'}); print('scanned' in r)"` |
| `list_files` 工具 | `opc/tools/search_tools.py` | 同上，确认 registry 中存在 |
| `tool_call` 消息循环 | `opc/main.py:run_engineer()` | `uv run pytest tests/ -q` 全绿 |
| QA 读源码辅助 | `opc/main.py:run_qa()` | 无测试，但代码已接入 |
| `human_gate` 关卡 | `opc/main.py` 状态机 | `uv run python3 -c "from opc.config import VALID_STAGES; print('human_review' in VALID_STAGES)"` |
| 原子 `status.json` 写入 | `opc/state.py:save_status()` | `uv run pytest tests/test_queue_stage2.py -q` |
| 启动孤儿进程清理 | `opc/executor.py:cleanup_all_orphans()` | `uv run python3 -c "from opc.executor import cleanup_all_orphans; print(cleanup_all_orphans())"` |
| `STRICT_QUEUE_MODE` | `opc/config.py` | `uv run python3 -c "from opc.config import STRICT_QUEUE_MODE; print(STRICT_QUEUE_MODE)"` |

**未落地** ⏳

| 能力 | 状态 | 备注 |
|------|------|------|
| **Engineer 小循环** | ✅ 已实现（2026-05-14）| `REPAIR_PROMPT_TEMPLATES` 7 类型专门策略 |
| **Manager 大循环** | ✅ 已实现（2026-05-14）| `MAX_MANAGER_REPLANS=2`，去重检测 |
| **主观/客观需求自动分流** | ❌ 未实现 | Manager 无法自动标记，human_gate 手动触发 |
| `patch/diff` 智能化写入 | ❌ Stage 2 规划后置 | — |
| 模型降级/升级策略 | ❌ Stage 2 P2 | — |

---

## 快速命令参考

```bash
# 开发
uv sync                    # 安装依赖
uv run python -m opc.main  # 运行 OPC

# 测试
uv run pytest tests/ -v                    # 全量测试
uv run pytest tests/test_queue_stage2.py   # 队列测试
uv run pytest tests/test_sandbox.py        # 沙箱测试

# 工具验证
uv run python3 scripts/check_doc_consistency.py  # 文档一致性
uv run python3 -c "from opc.tools import get_registry; print(list(get_registry().list_tools().keys()))"

# 清理
uv run pytest tests/ --cache-clear  # 清除缓存重新跑
```

---

## Stage 3 Day 3 验证记录（2026-05-14 ✅）

**Engineer 小循环** ✅ 已实现：
- [x] `REPAIR_PROMPT_TEMPLATES` 7 个 failure_type（test_failure, compile_error, timeout, runtime_error, qa_parse_error, qa_validation_error, unknown）
- [x] `test_failure` 引导 read_file + edit_file 精准修复
- [x] `completed_stages` 在 retry 时重置为 `["manager"]`
- [x] 探针实验：DeepSeek V4 Flash 精准定位 `PORT = 8889` 并修复

**Manager 大循环** ✅ 已实现：
- [x] `MAX_MANAGER_REPLANS = 2`
- [x] `_append_retry_history()` 写入 `retry_history.json`（failure_type + qa_summary + files_written）
- [x] `run_manager_replan()` 读取失败历史 + 源码 → 覆盖 task.json
- [x] 去重检测：steps 完全相同 → failed
- [x] 主循环 `manager_replan` case
- [x] QA fallback qa_report（解析失败时也写 retry_history）

**验证命令**：
```bash
uv run pytest tests/ -q  # 18/18 ✅
uv run python3 -c "from opc.prompts import REPAIR_PROMPT_TEMPLATES; print(len(REPAIR_PROMPT_TEMPLATES))"  # 7
uv run python3 -c "from opc.config import MAX_MANAGER_REPLANS; print(MAX_MANAGER_REPLANS)"  # 2
```
