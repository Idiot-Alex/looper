# Stage 3 验收清单

*最后更新：2026-05-17*

> 本文档逐项验证 Stage 3 各能力是否已实现。测试 → 证据 → 结论。

---

## 能力一：Engineer 小循环（QA fail → 自动重修复）

**设计文档**：`opc/prompts.py` `REPAIR_PROMPT_TEMPLATES`

### 验证项

- [x] `REPAIR_PROMPT_TEMPLATES` 包含 7 个 failure_type
  - ✅ `test_failure`, `compile_error`, `timeout`, `runtime_error`, `unknown`
  - ✅ `qa_parse_error`（新增）, `qa_validation_error`（新增）
- [x] `test_failure` 模板引导优先用 `read_file` + `edit_file`
  - 证据：`"read_file" in REPAIR_PROMPT_TEMPLATES["test_failure"]` → True
- [x] `handle_qa_result` 在 retry 时清空 `completed_stages`
  - 证据：`status["completed_stages"] = ["manager"]` 在 retry 分支
- [x] `tool_result` 后 prompt 明确要求输出 files JSON
  - 证据：`"直接输出 JSON" in continuation prompt`
- [x] 探针实验证据：DeepSeek V4 Flash 能精准修复端口错误
  - 证据：session 012 探针，read_file 定位 `PORT = 8889`，修复 → QA 通过

---

## 能力二：Manager 大循环（多轮 retry 后重规划）

**设计文档**：`opc/main.py` `run_manager_replan`

### 验证项

- [x] `MAX_MANAGER_REPLANS = 2` 在 config 中
  - 证据：`from opc.config import MAX_MANAGER_REPLANS; print(MAX_MANAGER_REPLANS)` → 2
- [x] `_append_retry_history` 在每次小循环失败时写入 `retry_history.json`
  - 证据：`failure_type` + `qa_summary` + `files_written` 三字段完整
- [x] `retry_history.json` 字段：`failure_type` + `qa_summary` + `files_written`
- [x] `run_manager_replan` 读取 `retry_history.json` 构建 prompt
  - 证据：`history_file = session_dir / "retry_history.json"` 存在
- [x] Manager replan 完全覆盖 `task.json`（goal 不变，steps 全新）
  - 证据：`with open(task_file, "w") as json.dump(data, f)` 直接覆盖
- [x] 去重检测：`steps` 完全相同 → `failed`
  - 证据：`"old_steps == new_steps" in src_main`
- [x] 主循环处理 `manager_replan` 状态
  - 证据：`elif stage == "manager_replan": run_manager_replan(status)`
- [x] 大循环上限达到后 → `failed`
  - 证据：`replan_count < MAX_MANAGER_REPLANS` 条件判断

---

## 能力三：retry_history 持久化

### 验证项

- [x] `retry_history.json` 文件在 session 目录下
- [x] 每次小循环失败追加一条记录
- [x] 字段完整：`failure_type`, `qa_summary`, `files_written`

---

## 能力四：QA 解析失败时正确处理

### 验证项

- [x] QA JSON 解析失败时，写入 fallback `qa_report.json`
  - 证据：`fallback_qa = {"failure_type": "qa_parse_error", ...}` in `run_qa`
- [x] `qa_parse_error` 有对应的 REPAIR_PROMPT_TEMPLATE
- [x] `qa_validation_error` 有对应的 REPAIR_PROMPT_TEMPLATE
- [x] QA prompt 的 failure_type 枚举包含所有新类型

---

## 真实任务验证（2026-05-17）

| # | 任务 | 验证点 | 结果 | 耗时 | 关键发现 |
|:-:|:-----|:-------|:----:|:----:|:---------|
| 1 | Flask 项目（`/` + `/health`，多文件） | 多文件、第三方依赖、端口声明 | ✅ **success** | 21s | port 5000 被 macOS AirPlay 占用→改 8000；Engineer 不再生成 shell 脚本 |
| 2 | CLI hello world（向后兼容） | 无服务任务、无端口、单文件 | ✅ **success** | 30s | Manager 不输出 `background_commands` → QA 自动 fallback |
| 3 | 难任务（触发大循环） | 3次retry → Manager replan | ✅ **replan × 2** | — | `replan_count: 2` 确认，`MAX_MANAGER_REPLANS` 限流正确 |
| 4 | 首页 HTML 设计（human_gate） | 主观审美、手动触发审批 | ✅ **success** | ~60s | QA 不主动标记；手动设 `needs_human_review=true` 后状态机正常运行 ✅✅ 两条路径: y→success, n→failed |

**数据来源**：001_flask、001_hello、task4_index 等 session 的实际运行记录。

## 端到端验证命令

```bash
# 验证 REPAIR_PROMPT_TEMPLATES
uv run python3 -c "from opc.prompts import REPAIR_PROMPT_TEMPLATES; print(list(REPAIR_PROMPT_TEMPLATES.keys()))"

# 验证配置
uv run python3 -c "from opc.config import MAX_MANAGER_REPLANS; print(MAX_MANAGER_REPLANS)"

# 验证 main.py
grep -n "manager_replan" opc/main.py

# 全量测试
uv run pytest tests/ -q
```

---

## 验证结果汇总

| 验证项 | 状态 | 证据 |
|--------|------|------|
| REPAIR_PROMPT_TEMPLATES 7类型 | ✅ | `keys()` 返回 7 个 | 实测: test_failure, compile_error, timeout, runtime_error, qa_parse_error, qa_validation_error, unknown |
| test_failure 引导策略 | ✅ | 包含 read_file + edit_file |
| completed_stages 重置 | ✅ | handle_qa_result 中 |
| tool_result continuation | ✅ | main.py continuation prompt |
| 探针实验证据 | ✅ | session 012, 精准修复端口 |
| MAX_MANAGER_REPLANS = 2 | ✅ | config.py |
| _append_retry_history | ✅ | 三字段完整 |
| retry_history 字段完整 | ✅ | failure_type + qa_summary + files_written |
| task.json 覆盖逻辑 | ✅ | json.dump(data) 直接覆盖 |
| 去重检测 | ✅ | old_steps == new_steps |
| manager_replan 主循环 | ✅ | elif stage == "manager_replan" |
| 大循环上限 → failed | ✅ | replan_count < MAX_MANAGER_REPLANS |
| QA fallback qa_report | ✅ | run_qa 中 fallback 写入 |
| qa_parse_error 模板 | ✅ | REPAIR_PROMPT_TEMPLATES 中 |
| 全量测试 | ✅ | 18/18 passed |

**结论**：Stage 3 ✅ 全部实现（2026-05-14）

---

## 端到端验证：Flask 项目完整跑通（2026-05-17）

**任务**：Flask 项目，`/` + `/health` 两个路由，多文件，`output/flask_app/` 目录

**结果**：✅ **success**（21 秒）

| 维度 | 状态 | 修复链 |
|:-----|:-----|:-------|
| Engineer 写代码到 `output/` | ✅ | 输出目录统一 |
| `run_info` 声明端口 8000 | ✅ | 不用 5000（macOS AirPlay 占用）|
| `start_command` 用 `uv run python` | ✅ | 禁止 shell 脚本 |
| QA 一步审计 (DeepSeek) | ✅ | 21 秒内完成 |
| 异步 MiniMax 审计 | ✅ | `qa_audit_minimax.txt` 写入 |
| curl `--retry 3` | ✅ | Flask 启动时序宽容 |
| `cleanup_background()` | ✅ | retry 间端口不冲突 |
| QA JSON 正确解析 | ✅ | reason 内嵌 JSON 已转义 |

---

---

## 全能力验证（2026-05-17）

| 能力 | 验证方式 | 结果 | 关键证据 |
|:-----|:---------|:----:|:---------|
| **read_file + edit_file** 改已有代码 | 给 `output/server.py` 新增 `/health` 端点，要求 Engineer 先读再改 | ✅ **success** (26s) | `🔧 工具调用: read_file(['path'])` → 精准输出修改后的 `output/server.py` |
| **Manager 大循环** 3 次 retry → 换思路 | Flask 任务故意触发 3 次 retry → 2 次 replan | ✅ **replan × 2** | `replan_count: 2`，`MAX_MANAGER_REPLANS` 限流正确 |
| **语言无关依赖** JS/Go/Rust | Node.js Express 项目，`npm install express` | ✅ **success** (39s) | `📦 安装 javascript 依赖: express` → `✅ express 安装成功` → QA 通过 |
| **search_code + list_files** | Engineer 在多个任务中自调用 | ✅ **已实锤** | task1_flask: `list_files(['path','pattern'])`、多个 retry 中 `read_file` 等 |
## 发现并修复的隐藏 bug

### Bug: QA 解析失败时不写 retry_history
**症状**：QA 输出 JSON 解析失败时，`handle_qa_result` 找不到 `qa_report.json`，直接走 `failed`，`_append_retry_history` 没被调用。

**修复**：`run_qa` 在 JSON 解析失败时写入 fallback `qa_report.json`（`failure_type="qa_parse_error"`），让 `handle_qa_result` 正常处理。

### Bug: macOS AirPlay 占用端口 5000
**症状**：Flask 任务反复失败，curl 返回空响应。调试发现端口 5000 被系统 AirPlay Receiver 占用。

**修复**：Engineer prompt 中明确标注「不要用 5000，推荐 8000、8888、8080」。

### Bug: Engineer 生成 shell 脚本作 start_command
**症状**：`run_info.start_command` 设为 `bash run.sh`，而 `run.sh` 用 `&` 后台起 Flask 后退出，cleanup_background 时误杀进程。

**修复**：Engineer prompt 约束「不要生成 shell 脚本，不要用 `&`，统一用 `uv run python <文件>`」。

### Bug: QA reason 字段内嵌 JSON 引号冲突
**症状**：QA 输出 `"reason": "...返回 JSON {"status":"ok"}..."`，JSON 解析失败。

**修复**：QA prompt 提示「reason 中含 JSON 内容时转义双引号为 `\"`」。

### Bug: 裸 python 找不到 uv venv 中的 Flask
**症状**：`start_command` 设为 `python app.py`，但 Flask 装在 uv 虚拟环境中。

**修复**：Engineer prompt 统一要求 `uv run python`。
