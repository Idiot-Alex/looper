# Sprint 执行指南（Stage 2.5 → Stage 3）

*最后更新：2026-05-14*

> 本文档是开发者的短期执行手册，不是战略愿景。目标能力 → 对应文件 → 成功判定命令，逐一对应。

---

## Stage 2.5 当前状态

**已落地** ✅

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

| 能力 | 规划阶段 | 状态 |
|------|---------|------|
| Manager 标记主观/客观需求 | Stage 2.5 P2 | 未开始 |
| Stage 3: Engineer 小循环 | Stage 3 | 未开始 |
| Stage 3: Manager 大循环 | Stage 3 | 未开始 |

---

## Stage 3 预备清单

在开始 Stage 3 前，建议先确认以下前置条件：

### 工具行为稳定性
```bash
# 1. 文档一致性检查
uv run python3 scripts/check_doc_consistency.py

# 2. 全量测试
uv run pytest tests/ -v

# 3. 手动功能验证（一个真实任务）
echo "实现一个计算器，支持加减乘除" > opc/tasks/inbox/2026-05-14-001.md
uv run python -m opc.main
```

### Stage 3 核心改动预判

| 改动点 | 当前实现 | Stage 3 目标 |
|--------|---------|------------|
| `engineer_done` → QA fail | → `engineer_retry` | → 小循环（自动重修复）最多 N 次 |
| 多次小循环失败 | → `failed` | → Manager 大循环重规划 |
| QA 主观判定 | → `needs_human_review` | → `human_gate` 审批后继续 |
| 客观需求 | → QA pass → success | 不变 |

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
