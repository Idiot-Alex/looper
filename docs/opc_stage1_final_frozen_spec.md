# OPC Stage 1 MVP（最终冻结版 / 协议化可执行版）

## 目标

构建一个真正可运行的 OPC 第一阶段系统，用最小复杂度跑通下面这个闭环：

需求 → 任务拆解 → 代码生成 → 文件落地 → 真实命令执行 → QA 判定 → 验收 / 重试

这一阶段不追求多虚拟机、不追求全自动公司，只追求一件事：

**给一个需求，系统能在单机环境里完成“拆、做、测、验”的完整闭环，并留下可审计记录。**

---

## 设计原则

1. 先跑通闭环，不做复杂系统
2. 用文件和日志驱动状态，不引入数据库
3. 用严格 JSON 协议，避免解析自由文本
4. Runner 负责执行，LLM 负责决策
5. QA 不执行命令，只分析真实执行结果
6. 所有交接物必须落盘
7. 必须有失败回路和重试上限
8. 协议失败和业务失败必须区分

---

## 系统架构

```text
1 台 macOS VM / 单机环境
├─ Runner（opc-run.sh 或 python runner）
├─ LLM Provider
│  ├─ DeepSeek：Manager / Engineer
│  └─ MiniMax：QA
├─ 项目代码目录
└─ opc/
   ├─ agents/
   ├─ tasks/
   ├─ runtime/
   ├─ logs/
   └─ memory/
```

---

## 角色定义

### Manager
职责：
- 读取需求
- 拆解任务
- 定义验收标准
- 在多次失败后重新拆任务
- 做最终验收结论

限制：
- 不写代码
- 不执行命令
- 不改项目文件

建议模型：
- DeepSeek

### Engineer
职责：
- 根据任务生成代码改动
- 输出要写入的文件内容
- 在失败后根据 QA 证据修复代码

限制：
- 不改需求
- 不跳过验收标准
- 不直接运行测试命令
- 不决定是否通过

建议模型：
- DeepSeek

### QA
职责：
- 接收 Runner 提供的真实命令执行结果
- 判断是否满足验收标准
- 输出通过/失败和理由

限制：
- 不写代码
- 不执行命令
- 不修改文件

建议模型：
- MiniMax

---

## Runner 的职责

Runner 是第一阶段的核心，不是附属品。

Runner 负责：
1. 读取任务状态
2. 调用不同角色的 LLM
3. 保存原始 prompt 和原始输出
4. 解析 JSON 输出
5. 将 Engineer 输出真正写入文件
6. 运行测试命令
7. 收集 stdout / stderr / exit code
8. 将真实执行结果提供给 QA
9. 更新状态机
10. 控制失败重试
11. 区分协议失败、执行失败和业务失败

一句话：

**Runner 是执行器和状态机，LLM 是“脑”，Runner 是“手和神经系统”。**

---

## 目录结构

```text
opc/
├─ agents/
│  ├─ manager.md
│  ├─ engineer.md
│  └─ qa.md
├─ tasks/
│  ├─ inbox.md
│  ├─ task.json
│  ├─ engineer_output.json
│  ├─ qa_report.json
│  └─ status.json
├─ runtime/
│  ├─ last_stdout.txt
│  ├─ last_stderr.txt
│  ├─ last_exit_code.txt
│  ├─ last_command.txt
│  └─ background_pids.json
├─ logs/
│  ├─ sessions/
│  ├─ prompts/
│  ├─ raw_outputs/
│  └─ command_runs/
└─ memory/
   ├─ product.md
   └─ decisions.md
```

---

## 状态机

`opc/tasks/status.json`

```json
{
  "stage": "inbox",
  "retry_count": 0,
  "parse_retry_count": 0,
  "session_id": "2026-05-07-001"
}
```

### 合法状态

```text
inbox
manager_done
engineer_done
engineer_retry
qa_done
success
failed
parse_error
```

### 基本流转

```text
inbox
→ manager_done
→ engineer_done
→ qa_done
→ success
```

### 失败流转

```text
qa_done and passed = false
→ retry_count + 1
→ 若 retry_count < 3，进入 engineer_retry
→ 若 retry_count >= 3，进入 failed
→ failed 后交给 Manager 重新拆任务或人工处理
```

### 协议失败流转

```text
LLM 输出 JSON 解析失败
→ 自动重调当前角色 1 次
→ 若仍失败，进入 parse_error
→ 保存 raw output
→ 停止流程，等待人工处理
```

---

## 协议要求：只允许 JSON 输出

为了避免 LLM 输出不稳定，三个角色都必须输出严格 JSON。

不要解析自由文本，不要依赖 markdown 代码块，不要依赖 “[File Write]” 这类脆弱格式。

---

## Manager 输出协议

保存到：`opc/tasks/task.json`

```json
{
  "goal": "实现一个 Node.js Hello API",
  "steps": [
    "创建 HTTP 服务",
    "监听 3000 端口",
    "返回 Hello OPC"
  ],
  "acceptance_criteria": [
    "服务可以成功启动",
    "curl http://localhost:3000 返回 Hello OPC"
  ],
  "background_commands": [
    "node src/index.js"
  ],
  "test_commands": [
    "curl -s http://localhost:3000"
  ],
  "startup_wait_seconds": 2,
  "notes": "优先最简单实现，不引入额外依赖"
}
```

字段说明：
- `goal`: 本次任务目标
- `steps`: 推荐实施步骤
- `acceptance_criteria`: QA 判断依据
- `background_commands`: 需要后台启动的命令
- `test_commands`: 前台验证命令
- `startup_wait_seconds`: 启动等待秒数
- `notes`: 其他约束或提示

### 命令执行约定
1. `background_commands` 先执行
2. Runner 等待 `startup_wait_seconds`
3. 再执行 `test_commands`
4. 测试结束后，Runner 负责清理后台进程

---

## Engineer 输出协议

保存到：`opc/tasks/engineer_output.json`

```json
{
  "files": [
    {
      "path": "src/index.js",
      "content": "const http = require('http');\nconst server = http.createServer((req, res) => {\n  res.end('Hello OPC');\n});\nserver.listen(3000);"
    }
  ],
  "summary": "新增了最小 HTTP 服务并监听 3000 端口"
}
```

字段说明：
- `files`: 要写入的文件数组
- `path`: 项目内相对路径
- `content`: 文件完整内容
- `summary`: 本轮改动摘要

### 文件写入规则
1. Runner 只接受 JSON 中的 `files`
2. Runner 只写入白名单目录中的文件
3. Runner 必须拒绝：
   - 绝对路径
   - `../` 跳目录
   - 隐藏的系统敏感路径
4. Runner 写入前要先备份旧文件或记录 diff

---

## QA 输出协议

保存到：`opc/tasks/qa_report.json`

```json
{
  "passed": true,
  "reason": "服务成功启动，curl 返回 Hello OPC，满足验收标准",
  "failed_checks": [],
  "evidence": {
    "stdout": "Hello OPC",
    "stderr": "",
    "exit_code": 0,
    "command": "curl -s http://localhost:3000"
  },
  "next_action": "accept"
}
```

失败示例：

```json
{
  "passed": false,
  "reason": "服务未成功启动，curl 无法得到预期结果",
  "failed_checks": [
    "服务可以成功启动",
    "curl http://localhost:3000 返回 Hello OPC"
  ],
  "evidence": {
    "stdout": "",
    "stderr": "Error: listen EADDRINUSE: address already in use :::3000",
    "exit_code": 1,
    "command": "node src/index.js"
  },
  "next_action": "send_back_to_engineer"
}
```

### QA 的定位
QA 不是命令执行者，QA 是命令结果解释者。

真实链路必须是：

```text
Runner 执行命令
→ Runner 收集 stdout / stderr / exit code
→ Runner 把结果和验收标准喂给 QA
→ QA 输出判断
```

---

## Prompt 设计建议

### Manager Prompt
Manager prompt 里必须强调：
- 你只输出 JSON
- 不要输出解释文字
- `background_commands` 和 `test_commands` 必须是 Runner 可执行的真实命令
- 验收标准必须可验证，不能抽象

### Engineer Prompt
Engineer prompt 里必须强调：
- 你只输出 JSON
- 不要输出 markdown
- 只给出完整文件内容，不给 patch
- 只能修改项目工作区内文件
- 修复模式下必须参考 QA 报告和实际 stderr

### QA Prompt
QA prompt 里必须强调：
- 你不会执行命令
- 你会收到实际命令输出
- 你只根据验收标准和执行结果做判断
- 你只输出 JSON

---

## 重试机制

当 QA 判定失败时，不是重新从头开始，而是进入修复模式。

### 修复模式时，Runner 必须提供给 Engineer 的上下文

1. 当前任务 `task.json`
2. 当前项目中相关文件的最新内容
3. 上一轮 `qa_report.json`（内含 evidence 数组，已覆盖每条命令的 stdout/stderr/exit_code）
4. 上一轮 `engineer_output.json`

> 注意：修正 3 已将 `evidence` 从单条记录改为数组，`qa_report.json` 包含所有执行结果，无需再单独传 `runtime/last_*` 文件。

这样 Engineer 才知道：
- 自己上次写了什么
- 错在什么地方
- 为什么没有通过

### 重试上限
- 最大重试次数：3
- 超过 3 次：标记为 `failed`
- 进入 `failed` 后，由 Manager 重新拆任务或交由人工处理

---

## JSON 解析失败处理

这是第一阶段必须单独定义的异常路径。

规则：
1. 任一角色输出 JSON 解析失败时，Runner 保存原始输出
2. 自动重调当前角色 1 次
3. 如果第二次仍然解析失败，写入 `stage = "parse_error"`
4. 停止流程，等待人工处理

目的：
把“协议不合法”和“代码实现失败”明确区分开。

---

## Runtime 文件说明

```text
opc/runtime/
├─ last_stdout.txt
├─ last_stderr.txt
├─ last_exit_code.txt
├─ last_command.txt
└─ background_pids.json
```

这些文件由 Runner 在执行测试命令后生成。

用途：
- 给 QA 提供证据
- 给 Engineer 提供修复上下文
- 方便人工排查问题
- 记录后台进程以便清理

---

## Logs 设计

这是第一阶段非常重要但容易忽略的一部分。

```text
opc/logs/
├─ sessions/
├─ prompts/
├─ raw_outputs/
└─ command_runs/
```

### 建议记录内容

#### sessions/
每轮完整会话摘要，例如：
- session id
- 当前阶段
- 模型选择
- 执行结果
- 重试次数
- 解析失败次数

#### prompts/
保存每次发给 LLM 的完整 prompt  
例如：
- `2026-05-07-001-manager.txt`
- `2026-05-07-001-engineer-retry-1.txt`

#### raw_outputs/
保存 LLM 原始输出，哪怕解析失败也要保留

#### command_runs/
保存命令执行记录，例如：
- 执行的命令
- 工作目录
- stdout
- stderr
- exit code
- 时间戳

### 为什么必须有日志
因为第一阶段最常见的翻车点不是“模型不会写”，而是：
- 输出格式不合法
- JSON 解析失败
- 文件写入异常
- 后台进程未清理
- 测试命令和预期不一致

没有完整日志，调试会非常痛苦。

---

## Memory 规则

### `product.md`
用途：
- 产品背景
- 项目目标
- 长期不变约束

写入规则：
- 只由人工维护
- 不允许每轮自动改写

### `decisions.md`
用途：
- 记录关键决策
- 记录重要教训

只允许记录：
- 架构变更
- 技术选型
- 关键 bug 结论
- 重要流程调整

不允许记录：
- 每次运行细节
- 每轮 QA 结果
- 临时调试信息

目的：
避免 memory 无限膨胀，污染后续上下文。

---

## 单轮执行流程

### Step 1：写入需求
`opc/tasks/inbox.md`

示例：

```md
实现一个 Node.js Hello API
要求：
- 监听 3000 端口
- 访问 / 时返回 Hello OPC
- 不引入额外依赖
```

### Step 2：Runner 调用 Manager
输入：
- `inbox.md`
- `memory/product.md`
- `memory/decisions.md`
- `agents/manager.md`

输出：
- `task.json`

状态：
- `stage = manager_done`

### Step 3：Runner 调用 Engineer
输入：
- `task.json`
- 相关项目文件内容
- `agents/engineer.md`

输出：
- `engineer_output.json`

Runner 行为：
- 校验 JSON
- 校验路径安全
- 写入文件
- 保存原始输出

状态：
- `stage = engineer_done`

### Step 4：Runner 执行命令
输入：
- `task.json.background_commands`
- `task.json.test_commands`
- `task.json.startup_wait_seconds`

Runner 行为：
1. 启动后台命令
2. 等待启动时间
3. 执行测试命令
4. 保存 stdout / stderr / exit code
5. 结束后台进程
6. 写入 `runtime/`
7. 写入 `logs/command_runs/`

### Step 5：Runner 调用 QA
输入：
- `task.json`
- `runtime/last_stdout.txt`
- `runtime/last_stderr.txt`
- `runtime/last_exit_code.txt`
- `runtime/last_command.txt`
- `agents/qa.md`

输出：
- `qa_report.json`

状态：
- `stage = qa_done`

### Step 6：判断结果
- 若 `passed = true`，则 `stage = success`
- 若 `passed = false`，则进入 `engineer_retry`

---

## 最小 Runner 伪代码

```python
load status.json

if stage == "inbox":
    call_manager()
    save task.json
    stage = "manager_done"

if stage in ["manager_done", "engineer_retry"]:
    call_engineer()
    parse engineer_output.json
    write files safely
    stage = "engineer_done"

if stage == "engineer_done":
    run background_commands
    wait startup_wait_seconds
    run test_commands
    save runtime artifacts
    cleanup background processes
    call_qa()
    save qa_report.json
    stage = "qa_done"

if stage == "qa_done":
    if qa_report["passed"]:
        stage = "success"
    else:
        retry_count += 1
        if retry_count < 3:
            stage = "engineer_retry"
        else:
            stage = "failed"

save status.json
```

---

## 安全边界

第一阶段虽然是 MVP，也要有基本边界。

Runner 必须限制：
1. 文件写入路径范围
2. 可执行命令范围
3. 工作目录范围
4. 最大执行时间
5. 后台进程清理
6. 端口占用冲突检测

建议：
- 只允许在项目目录内写文件
- 只允许执行 Manager 生成的白名单命令
- 每条命令设置 timeout
- 不允许 `rm -rf`、`sudo`、网络破坏性命令

---

## 第一阶段成功标准

如果这个阶段做成，应该达到下面效果：

1. 你写一个需求到 `inbox.md`
2. 运行一次 Runner
3. 系统自动生成任务
4. 系统自动落地代码
5. 系统自动跑后台启动命令和测试命令
6. 系统自动给出 QA 报告
7. 成功则结束，失败则自动重试
8. 协议错误会进入 `parse_error`
9. 全程有日志可审计、可复现、可调试

---

## 第一阶段不做什么

为了克制复杂度，以下内容不在第一阶段实现范围内：

- 多 VM 协作
- 多 Agent 并发
- 自动 PR / Gitea 集成
- 自动部署
- 动态模型路由
- 自主规划多个大任务
- 数据库状态管理
- 长期自治运行

---

## 推荐起步案例

建议从最简单任务开始，不要一上来做 SaaS。

推荐案例：
1. Node.js Hello API
2. Python CLI 工具
3. 简单静态网页
4. 小型脚本工具

先跑通一个成功闭环，再故意制造一个 bug，看系统能不能进入失败回路并修复。然后再故意制造一个 JSON 非法输出，验证 `parse_error` 是否生效。

---

## 推荐实现顺序

1. 初始化目录和 `status.json`
2. 先实现 Manager 调用 + JSON 解析
3. 实现安全文件写入模块
4. 实现命令执行模块
   - 后台进程
   - 启动等待
   - stdout/stderr/exit code 收集
   - 进程清理
5. 接入 Engineer
6. 接入 QA
7. 实现 `engineer_retry`
8. 跑 Hello API
9. 故意制造 bug 测失败回路
10. 故意制造 JSON 非法输出测 `parse_error`

---

## 一句话总结

这不是一个“prompt demo”，而是一个：

**以 Runner 为核心、以 JSON 协议为骨架、以真实执行结果为依据、能区分业务失败与协议失败的最小可执行 AI 工厂。**

---

## 附录三：冻结前修正

*来源：Claude 和 GPT 对终版 spec 的独立复审，合并修正如下。*

### 修正 1：`startup_wait_seconds` + `health_check_port`

**问题：** 主文用 `startup_wait_seconds`（固定 sleep），附录二用端口探测，两处矛盾，且端口探测时 Runner 不知道是哪个端口。

**修正：**

1. 保留 `startup_wait_seconds`，语义改为 **最大等待时间上限**（端口探测的超时兜底）
2. `task.json` 新增可选字段 `health_check_port`：

```json
{
  "health_check_port": 3000,
  "startup_wait_seconds": 10
}
```

3. Runner 行为：端口探测优先，超时后用 `startup_wait_seconds` 兜底

---

### 修正 2：`background_pids.json` 正式 schema

**问题：** 文件出现在目录结构中，但格式从未定义。

**修正：** Runtime 章节新增正式 schema：

```json
{
  "pids": [12345],
  "commands": ["node src/index.js"],
  "started_at": "2026-05-09T00:23:00Z"
}
```

注：清理时进程不存在要静默处理。

---

### 修正 3：`qa_report.json` 的 `evidence` 改为数组

**问题：** `test_commands` 是数组（可多条命令），但 `evidence` 只存了一条结果。两条测试命令时第二条没地方放。

**修正：** `evidence` 改为数组：

```json
{
  "passed": true,
  "reason": "所有测试通过",
  "failed_checks": [],
  "evidence": [
    {
      "command": "curl -s http://localhost:3000",
      "stdout": "Hello OPC",
      "stderr": "",
      "exit_code": 0
    },
    {
      "command": "curl -s -o /dev/null -w '%{http_code}' http://localhost:3000",
      "stdout": "200",
      "stderr": "",
      "exit_code": 0
    }
  ],
  "next_action": "accept"
}
```

Runner 将每条 `test_commands` 的执行结果填入 `evidence` 数组。QA 判断时基于全部 evidence。

---

### 修正 4：`parse_retry_count` 规则写死

**问题：** 规则散落在主文和附录二，未正式钉死，存在"全局/按角色"的歧义。

**修正：**

- 每次进入**新角色阶段**时，`parse_retry_count` 重置为 `0`
- 当前角色 JSON 解析失败时，`parse_retry_count += 1`
- 若 `parse_retry_count > 1`（即同一角色连续两次解析失败），进入 `parse_error`
- 特别地：`engineer_retry` 时该计数要显式重置为 `0`（因为是新角色调用，且这是特意提醒的坑点）

---

### 修正 5：`failed` 状态恢复路径

**问题：** 状态机写"failed 后交给 Manager 重新拆任务"，但未说明具体怎么回。实现时会不知道下一步。

**修正：**

`failed` 是**终态**（与 `success`、`parse_error` 并列）。进入 `failed` 后路径：

1. 保存 `status.json`（stage=「failed」）
2. 打印失败摘要
3. 流程终止

如需从 `failed` 恢复：
- 人工介入处理失败原因
- 手动将 `status.json` 重置为 `inbox`，`retry_count` 重置为 `0`
- 重新运行 Runner

---

### 修正 6：伪代码改为 `while` 循环

**问题：** 主文伪代码是 `if` 链，附录二用 `while`，读文档会看到两种写法。

**修正：** 主文伪代码改成与附录二一致的 `while` 结构：

```python
status = load_status()

while status["stage"] not in ("success", "failed", "parse_error"):
    stage = status["stage"]
    
    if stage == "inbox":
        call_manager()
    elif stage in ("manager_done", "engineer_retry"):
        call_engineer()
    elif stage == "engineer_done":
        execute_and_qa()
    elif stage == "qa_done":
        if qa_report["passed"]:
            status["stage"] = "success"
        elif status["retry_count"] < 3:
            status["retry_count"] += 1
            status["parse_retry_count"] = 0   # ← 修正 4
            status["stage"] = "engineer_retry"
        else:
            status["stage"] = "failed"        # ← 修正 5

    save_status(status)
```

---

### 修正 7：`command_runs/` 按命令分别记录

**问题：** 原文只说"保存命令执行记录"，未明确是每轮一份还是每条命令一份。

**修正：**

- `runtime/last_*` 只保存**最近一次**测试命令结果（供 QA 实时使用）
- `logs/command_runs/` 按**每条命令**分别落文件，文件名带 session_id + 序号：

```
logs/command_runs/2026-05-07-001-bg-0.node_start.log
logs/command_runs/2026-05-07-001-test-0.curl.log
logs/command_runs/2026-05-07-001-test-1.http_code.log
```

---

### 修正 8：JSON 解析严格度统一

**问题：** 主文说"只允许 JSON，不要解析自由文本"，附录二 `parse_json_safe()` 又剥 markdown code fence。两处严格度不一致。

**修正：** 统一为：

- **协议层**：角色必须输出纯 JSON（prompt 里声明强制）
- **Runner 兜底**：允许做**一次有限剥离**——仅移除 markdown code fence 后重试
- **禁止**：自动补括号、自动截取 `{...}`、自动猜测字段——这些一律不做

---

### 修正 9：推荐实现顺序统一

**问题：** 主文和附录二的推荐顺序有先后差异。

**修正：** 统一为附录二版本（日志提前）：

```
1. status.json 读写 + 日志模块
2. LLM 调用层（两个 openai 实例）
3. JSON 解析（严格 + markdown code fence 兜底）
4. 安全文件写入
5. 命令执行模块（后台启动 + 端口探测 + 清理）
6. Manager 调用 + 解析
7. Engineer 调用 + 文件落地
8. QA 调用 + 判定
9. 状态机主循环串联
10. engineer_retry（失败回路）
11. parse_error（协议失败）
```

---

## 文档版本

- Version: Stage 1 Final Frozen Spec
- Updated: 2026-05-09 00:34:00

## 附录：Runner 技术选型分析

### 主推方案：Python + openai SDK

Runner 由两部分组成：
1. **状态机 + 协议层**：自己写（Python），严格按本 spec 的 JSON 协议
2. **LLM 调用层**：直接用 `openai` Python SDK

```python
from openai import OpenAI

deepseek = OpenAI(api_key="sk-...", base_url="https://api.deepseek.com")
minimax  = OpenAI(api_key="sk-...", base_url="https://api.minimaxi.com")

# Runner 中各阶段调用
deepseek.chat.completions.create(model="deepseek-chat", messages=...)   # Manager / Engineer
minimax.chat.completions.create(model="abab6.5s-chat", messages=...)   # QA
```

**为什么这样选：**

| 层 | 方案 | 原因 |
|-----|------|------|
| 状态机 + 协议 | Python 手写 | OPC 需要严格 JSON 协议和白名单校验，通用框架不匹配 |
| LLM 调用 | openai SDK | DeepSeek 和 MiniMax 都兼容 OpenAI 格式，一个 SDK 搞定 |
| 命令执行 | Python subprocess | 后台进程、stdout/stderr 收集、超时控制一条龙 |
| 文件操作 | Python 原生 | 安全路径校验、备份/回滚 |

**核心原则：MVP 阶段，依赖越少越好，出问题越容易查越好。**

### 备选：pi-ai（Stage 2 可能引入）

如果后续需要以下能力，再考虑引入 `pi-ai`（来自 badlogic/pi-mono）：
- 统一的多模型 cost tracking
- 自动 model discovery
- 动态模型路由（不同任务动态选模型）

pi-ai 的真正价值在 Stage 2 多模型动态路由阶段才会体现。Stage 1 只是两个模型两个实例，用 pi-ai 属于杀鸡用牛刀。

### pi-mono 参考分析

pi-mono 是 GitHub 开源项目（badlogic/pi-mono），定位是"开源编码代理平台，类似 Claude Code"。有三个核心包：

| 包 | 是什么 | 能用在 OPC 吗 |
|------|------|------|
| **pi-ai** | 统一多模型 API（OpenAI/Anthropic/Google/DeepSeek 等） | ⏸️ Stage 2 再引入 |
| **pi-agent-core** | 通用 Agent 运行时（工具调用、事件流、状态管理） | ❌ OPC 需要专用状态机 |
| **pi-coding-agent** | 终端交互式编码代理 CLI | ❌ OPC 是 headless 状态机 |

---

---

## 附录二：LLM 实现建议汇总

*来源：GPT 和 Claude 对 Runner 实现的独立建议整合。*

### 一、项目结构

两份建议一致结论：Runner 必须分模块，不能一个文件堆到底。

**推荐第一版结构：**

```
runner/
├── main.py          # 入口，状态机主循环
├── state.py         # status.json 读写
├── llm.py           # LLM 调用封装
├── parser.py        # JSON 解析（严格 + 兜底）
├── writer.py        # 安全文件写入
├── executor.py      # 命令执行（最复杂）
├── logger.py        # 日志落盘
├── prompts.py       # 各角色 prompt 模板
└── config.py        # 路径常量、超时、模型配置
```

---

### 二、LLM 调用层（两份建议完全一致）

```python
from openai import OpenAI

deepseek = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com"
)
minimax = OpenAI(
    api_key=os.environ["MINIMAX_API_KEY"],
    base_url="https://api.minimaxi.com/v1"
)
```

**关键参数：**
- `response_format={"type": "json_object"}` — DeepSeek 支持，大幅降低 JSON 格式错误概率；MiniMax 不支持就靠 prompt 约束兜底
- `temperature=0` — 状态机不需要创意，要稳定输出

---

### 三、JSON 解析兜底

两份建议都强调：不要完全相信模型的 JSON 输出。

```python
def parse_json_safe(raw: str) -> dict | None:
    # 1. 直接 json.loads
    try: return json.loads(raw)
    except: pass
    
    # 2. 剥 markdown 代码块重试
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if match:
        try: return json.loads(match.group(1))
        except: pass
    
    # 3. 两次都失败返回 None，触发 parse_error
    return None
```

**原则：** 不解做"智能修复"（自动补括号、自动截取 `{...}`）。失败就进入 `parse_error` 流程。

---

### 四、安全文件写入

两份建议一致的核心约束：

1. 拒绝绝对路径
2. 拒绝 `../`（路径穿越检测）
3. 拒绝隐藏目录（`.env`、`.ssh` 等）
4. 写入前备份旧文件（`.bak`）

```python
def safe_write(project_root: Path, relative_path: str, content: str):
    target = (project_root / relative_path).resolve()
    
    # 路径穿越检测
    if not str(target).startswith(str(project_root)):
        raise ValueError(f"路径越界: {relative_path}")
    
    # 拒绝隐藏路径
    for part in target.parts:
        if part.startswith("."):
            raise ValueError(f"拒绝隐藏路径: {relative_path}")
    
    # 备份旧文件
    if target.exists():
        target.with_suffix(target.suffix + ".bak").write_text(target.read_text())
    
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
```

---

### 五、命令执行模块（最复杂，最容易翻车）

两份建议都认为这是 Runner 最难的部分，必须单独调通。

**5a. 后台进程**

GPT 建议用 `startup_wait_seconds`（固定 sleep）。  
Claude 建议用**端口探测**替代固定 sleep：

```python
def wait_for_port(port: int, timeout: int = 10) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False
```

**结论：** 用端口探测，比 sleep 更可靠。服务没起来 curl 会拿到空输出，QA 误判。

**5b. 测试命令**

```python
def run_command(cmd: str, timeout: int = 30) -> dict:
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode, "command": cmd}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"命令超时（>{timeout}s）", "exit_code": -1, "command": cmd}
```

**5c. 后台清理**

两份建议一致的兜底策略：

```python
def cleanup_background(procs):
    for proc in procs:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()       # terminate 不响应就强杀
        except Exception:
            pass              # 进程可能已崩，静默处理
```

**关键：** 必须静默处理异常——进程可能已经崩了，抛异常会干扰主流程。

---

### 六、状态机

GPT 建议用 `if/elif` 链，Claude 建议用 `while` 循环。

**结论：用 `while` 循环。** 好处是中断后重启能接上，不用从头跑。

```python
def main():
    status = load_status()
    
    while status["stage"] not in ("success", "failed", "parse_error"):
        stage = status["stage"]
        
        if stage == "inbox":
            run_manager(status)
        elif stage == "manager_done":
            run_engineer(status)
        elif stage == "engineer_done":
            run_commands_and_qa(status)
        elif stage == "qa_done":
            handle_qa_result(status)
        elif stage == "engineer_retry":
            run_engineer_retry(status)
        
        save_status(status)
    
    print(f"最终状态: {status['stage']}")
```

---

### 七、日志规范

两份建议都强调保留原始输出，且文件名要带 session_id + stage + retry_count：

```
logs/
├── prompts/
│   ├── 2026-05-07-001_manager_0.prompt.txt
│   ├── 2026-05-07-001_engineer_retry_1.prompt.txt
│   └── ...
├── raw_outputs/
│   └── ...
├── command_runs/
│   └── ...
└── sessions/
    └── ...
```

---

### 八、容易忽略的细节

1. **`parse_retry_count` 在 `engineer_retry` 时要重置为 0**，否则第一次重试如果 LLM 输出格式抖一下就触发 `parse_error`，逻辑不对
2. **macOS 平台的 `shell=True` 子进程 PID 问题**需要时间摸清楚，executor.py 单独调通是正确策略
3. **先跑通成功路径，再补失败回路**，不要同时调试三类 bug

---

### 九、实现先后顺序

两份建议合并后的推荐顺序：

```
1. status.json 读写 + 日志模块
2. LLM 调用层（两个 openai 实例）
3. JSON 解析（严格 + markdown code fence 兜底）
4. 安全文件写入
5. 命令执行模块（后台启动 + 端口探测 + 清理）
6. Manager 调用 + 解析
7. Engineer 调用 + 文件落地
8. QA 调用 + 判定
9. 状态机主循环串联
10. engineer_retry（失败回路）
11. parse_error（协议失败）
```

其中步骤 5（命令执行）最容易翻车，**必须单独调通**，不要和其他模块混着调试。

---

### 十、验证标准

三局测试全部通过才算 Stage 1 站住：

| 测试 | 预期 |
|------|------|
| 测试 1：正常路径 | Manager → Engineer → QA → `success` |
| 测试 2：业务失败 | 注入 bug → QA 失败 → `engineer_retry` → 修复 → `success` |
| 测试 3：协议失败 | 模型返回非法 JSON → 重试 1 次 → 仍失败 → `parse_error` |

---

## 文档版本

- Version: Stage 1 Final Frozen Spec
- Updated: 2026-05-09 00:23:00
