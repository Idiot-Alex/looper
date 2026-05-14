# Stage 2 / 2.5 阶段完成说明

*最后更新：2026-05-14*

> 本文档记录 Stage 2 + Stage 2.5 的实现点、测试证据、已知边界与风险。团队后续接手以此为准，不再靠口头同步。

---

## 一、实现清单

### Stage 2 ✅ 已完成

| 能力 | 核心文件 | PR/Commit | 测试 |
|------|---------|-----------|------|
| 队列化（inbox/ + FIFO） | `opc/queue.py` | `cd407b4` | `test_fifo_ordering` |
| 独立 session 状态 + 断点恢复 | `opc/state.py` | `10a59bf` | `test_empty_inbox` |
| 回放保护（命令/文件去重） | `opc/queue.py` | `cd407b4` | `test_command_dedup`, `test_file_write_dedup` |
| 沙箱强化（黑名单 + 资源限制 + session 超时） | `opc/sandbox.py`, `opc/executor.py` | `8be8b1c` | `test_forbidden_commands`, `test_session_timeout` |
| 资源释放验证（dequeue 前校验） | `opc/executor.py:verify_resources_released` | `10a59bf` | `test_unused_port_check` |
| JSONL 审计事件流 | `opc/logger.py` | `8be8b1c` | — |
| Git 快照与回滚 | `opc/git_snapshot.py` | `b2f39e4` | `test_successful_snapshot` |
| QA 可解释性（`failure_type` + `criterion_results`） | `opc/prompts.py` | `db57fc3` | — |
| 成本统计与 HTML 面板 | `opc/metrics.py`, `opc/dashboard.py` | `da8bad0` | — |
| `status.json` 原子写入 | `opc/state.py:save_status` | `10a59bf` | — |
| 启动时清理孤儿进程 | `opc/executor.py:cleanup_all_orphans` | `10a59bf` | `test_cleanup_background_*` |
| `STRICT_QUEUE_MODE` 开关 | `opc/config.py` | `98a78d3` | — |

### Stage 2.5 ✅ P0 + P1 已完成

| 能力 | 核心文件 | PR/Commit | 测试 |
|------|---------|-----------|------|
| Tool/ToolRegistry 抽象 | `opc/tools/__init__.py` | `658b0d4` | — |
| `read_file` 工具 | `opc/tools/file_tools.py` | `658b0d4` | — |
| `edit_file` 工具 | `opc/tools/file_tools.py` | `658b0d4` | — |
| `search_code` 工具（含统计） | `opc/tools/search_tools.py` | `89150cf` | — |
| `list_files` 工具 | `opc/tools/search_tools.py` | `89150cf` | — |
| `tool_call` 消息循环（最多 10 次） | `opc/main.py:run_engineer` | `658b0d4` | — |
| Engineer prompt 升级 | `opc/prompts.py` | `658b0d4` | — |
| QA 读 Engineer 源码辅助分析 | `opc/main.py:run_qa` | `89150cf` | — |
| `human_gate` 人工审批关卡 | `opc/main.py` | `89150cf` | — |
| `needs_human_review` 字段 | `opc/prompts.py` | `89150cf` | — |
| `tool_loop_exceeded` 独立错误类型 | `opc/main.py` | `2026-05-13 commit` | — |
| shell wildcard 防护（`*` 展开） | `opc/executor.py` | `2026-05-13 commit` | — |

---

## 二、测试证据（Day 1 前置验证 2026-05-13）

```
=== 文档一致性检查 ===
Registry 中: ['edit_file', 'list_files', 'read_file', 'search_code']
文档中提到: ['edit_file', 'list_files', 'read_file', 'search_code']
文档提到但未注册: 无
✅ 一致性检查通过

=== 全量测试 (18/18) ===
tests/test_git_snapshot.py::TestGitSnapshot::test_not_in_git_repo PASSED
tests/test_git_snapshot.py::TestGitSnapshot::test_successful_snapshot PASSED
tests/test_git_snapshot.py::TestGetCommitHash::test_no_commits PASSED
tests/test_queue_stage2.py::TestFIFOQueue::test_empty_inbox PASSED
tests/test_queue_stage2.py::TestFIFOQueue::test_fifo_ordering PASSED
tests/test_queue_stage2.py::TestReplayProtection::test_command_dedup PASSED
tests/test_queue_stage2.py::TestReplayProtection::test_command_hash_different PASSED
tests/test_queue_stage2.py::TestReplayProtection::test_file_write_dedup PASSED
tests/test_queue_stage2.py::TestResourceVerification::test_no_ports_check PASSED
tests/test_queue_stage2.py::TestResourceVerification::test_unused_port_check PASSED
tests/test_sandbox.py::TestCommandValidation::test_legal_commands PASSED
tests/test_sandbox.py::TestCommandValidation::test_forbidden_commands PASSED
tests/test_sandbox.py::TestCommandValidation::test_partial_match_no_false_positive PASSED
tests/test_sandbox.py::TestWorkingDirectoryValidation::test_none_cwd PASSED
tests/test_sandbox.py::TestSessionTimeout::test_no_session_start PASSED
tests/test_sandbox.py::TestResourceLimits::test_set_resource_limits_no_crash PASSED
tests/test_executor_cleanup.py::test_cleanup_background_skips_invalid_pids PASSED
tests/test_executor_cleanup.py::test_cleanup_background_escalates_to_sigkill PASSED

=== 真实任务演练 ===
任务: 实现一个 Python 脚本 calculator.py（从标准输入读取 num op num，输出计算结果）
会话: 2026-05-14-003
结果: ✅ success
关键链路:
  1. Manager 拆解任务
  2. Engineer 调用 list_files 工具（✅ 工具链生效）
  3. QA 判定失败 → 进入 retry (1/3)
  4. Engineer retry 时工具循环正常工作
  5. 最终 QA 通过，Git 快照创建
Git 快照: 74f59b0

任务: 实现一个 Python 脚本 reverse.py（读取标准输入倒序输出）
会话: 2026-05-14-004
结果: ✅ success
关键链路:
  1. Manager 拆解任务
  2. Engineer 写入 reverse.py
  3. QA 第一次判定失败（字符串倒序逻辑有误）→ retry (1/3)
  4. Engineer retry 时调用 read_file 工具读取现有代码（✅ 工具链生效）
  5. 读取结果 → 直接输出修复后的 files JSON（✅ parse_error 已修）
  6. QA 第二次判定通过
  7. Git 快照创建
Git 快照: deb78aa
```

---

## 三、已知边界

| 边界 | 说明 | 风险等级 |
|------|------|---------|
| tool_loop 最多 10 次/会话 | 超过返回 `tool_loop_exceeded` → failed | 低 |
| `read_file` 最多 3000 行截断 | 大文件无法整体读入 | 中 |
| `search_code` 不支持模糊匹配 | 需要精确关键词或正则 | 低 |
| `human_gate` 需手动在 tty 输入 y/n/r | 非 tty 环境会超时自动拒绝 | 中 |
| `STRICT_QUEUE_MODE` 默认为 False | 资源泄漏默认不中断队列 | 低 |
| Manager/Engineer 使用同一模型 | 成本优化空间未探索 | 低 |
| QA 使用 MiniMax M2.5 | 弱模型，无法处理复杂主观判断 | 中 |

---

## 四、Stage 3 未落地清单（风险提示）

| 能力 | 状态 | 备注 |
|------|------|------|
| **Engineer 小循环**（QA fail → 自动重修复） | ✅ 已实现（2026-05-14）| `REPAIR_PROMPT_TEMPLATES` 按 `failure_type` 提供专门修复策略，引导优先用 `read_file` + `edit_file` 精准修改 |
| **Manager 大循环**（多轮 retry 后重规划） | ✅ 已实现（2026-05-14）| `run_manager_replan()` + `retry_history.json`，完全覆盖 task.json，换思路，最多 2 次 |
| **主观/客观需求自动分流** | ❌ 未实现 | Manager 无法自动标记任务为主观/客观，human_gate 只能靠 QA 手动触发 |
| **patch/diff 智能化写入** | ❌ 未实现 | Stage 2 规划已明确后置 |
| **模型降级/升级策略** | ❌ 未实现 | Stage 2 P2 规划 |

---

## 五、下一步风险

1. ~~**Engineer 小循环**：当前 retry 只是重新调用 Engineer，没有针对 `failure_type` 的专门修复 prompt 模板。~~ ✅ 已修复（2026-05-14）
2. **human_gate 在非 tty 环境会超时**：需要实现基于文件的审批机制（写一个 flag 文件，外部脚本可以修改它）。
3. **测试覆盖缺口**：工具系统（`read_file`、`edit_file`、`search_code`）没有单元测试，只有集成测试验证。

---

## 六、快速验证命令

```bash
# 文档一致性
uv run python3 scripts/check_doc_consistency.py

# 全量测试
uv run pytest tests/ -v

# 快速功能演练
echo "实现一个 Python 脚本 reverse.py，读取一行文字并倒序输出" > opc/tasks/inbox/2026-05-14-999.md
uv run python -m opc.main
```
