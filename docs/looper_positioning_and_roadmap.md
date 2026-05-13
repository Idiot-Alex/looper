# Looper 项目定位与发展路线

*最后更新：2026-05-13*

> 📌 **文档关系**：本文档是战略总览。Stage 2 细节以 `docs/stage2_next_phase_plan.md` 为准，避免双文档漂移。

---

## 一、项目定位

### 一句话

**Looper 是以确定性状态机调度多个 LLM 角色、以 JSON 协议为通信骨架、以全审计日志为质量保障的自主编程系统。**

用户只管描述需求，Looper 自动完成：理解需求 → 拆解任务 → 编写代码 → 真实执行 → 独立审计 → 失败修复 → 循环直到交付。

### 我们不是

| 不是 | 原因 |
|:---|:---|
| 代码补全工具 | 不嵌在编辑器里，不做下一行预测 |
| 聊天机器人 | 不做对话式编程，用户不需要盯着屏幕 |
| 另一个 OpenCode / Claude Code | 架构不同——他们是单 Agent 工具，我们是多角色系统 |
| 另一个 pi | pi 是单 Agent + 工具调用的 TypeScript CLI，我们是多角色流水线 |

### 核心差异化

| 维度 | 别人 | Looper |
|:---|:---|:---|
| 架构 | 单 Agent，用户指挥 AI 干活 | Multi-Role 流水线，系统自己调度 |
| 质量保障 | AI 写完自己说"好了" | 独立 QA 角色做第三方审计 |
| 可追溯 | 黑盒，崩了不知道怎么崩的 | 每步 JSON + 日志落盘，永远可回放 |
| 模型策略 | 单一模型从头用到尾 | 重型脑力给强模型，轻量判定给弱模型 |
| 失败处理 | 人工介入，手动修 | 自动回退重试，按失败类型走不同修复策略 |

### 护城河不是“写代码”，是“闭环”

1. 写完代码后由独立裁判（QA）验证。
2. 验证失败后自动定位问题、自动修复。
3. 修复后再次验证，循环直到通过。
4. 全过程全审计，任何时候都能回放。

---

## 二、设计哲学

### 三条铁律

| 原则 | 含义 | 边界 |
|:---|:---|:---|
| **全审计** | 每一步都有 JSON 记录 + 日志落盘 | 日志只增不删，审计链不断裂 |
| **确定性调度** | Runner 是确定性状态机，LLM 是不确定性执行器 | 状态机永远知道“现在在哪一步、下一步是什么” |
| **多模型分工** | 重型脑力活给强模型，轻量判定给弱模型 | 不追求单一模型包打天下 |

### 极简依赖

Looper 核心坚持极简依赖，优先标准库实现，非必要不引入第三方包。

```text
openai >= 1.0.0
python-dotenv >= 1.2.1
```

### 不追求的功能（红线）

- 不嵌进 IDE/编辑器
- 不做实时对话式编程
- 不做 GUI 操作系统级 Agent 能力
- 不做云端 SaaS（本地优先）
- 不按竞品功能列表做对标开发

---

## 三、架构设计

### 整体架构

```text
Runner（确定性状态机 + 工具调度）
├─ Manager（需求拆解）
├─ Engineer（代码实现）
├─ QA（独立审计）
└─ Tool Registry（read/write/edit/run/search/git_diff 等）
```

### 状态流转（Stage 3 目标态）

```text
inbox
→ manager_done
→ engineer_done
→ qa_done
  ├─ pass + 客观需求 → success
  ├─ pass + 主观需求 → human_gate
  └─ fail → engineer_retry / manager_replan
```

### QA 的边界

- ✅ 能判：端口响应、exit_code、输出格式、编译错误、关键词匹配等客观指标。
- ❌ 不能判：UI 美观、交互体验、文案专业度、架构“好不好”等主观判断。
- ⚠️ 对主观任务，通过 `human_gate` 进入人工确认。

### Multi-Role ≠ Multi-Agent

当前坚持 Multi-Role（Runner 统一调度，角色经由 JSON 交接），待模型能力足够强再评估演进 Multi-Agent。

---

## 四、角色定义

### Manager（规划者）

- 模型：DeepSeek V4 Flash
- 职责：读需求、拆任务、定义可验证验收标准
- 输出：`task.json`
- 权限：只读，不写代码，不执行命令

### Engineer（实现者）

- 模型：DeepSeek V4 Flash
- 职责：根据 `task.json` 实现代码并修复失败
- 输出：代码文件、`engineer_output.json`
- 权限：读写与执行工具（按策略限制）

### QA（审计者）

- 模型：MiniMax M2.5
- 职责：基于真实执行证据判定是否通过
- 输出：`qa_report.json`（含 `failure_type`、`criterion_results`）
- 权限：只读与验证，不写代码

---

## 五、发展路线图

### Stage 1（已完成 ✅）

跑通闭环：需求 → 拆解 → 编码 → 执行 → 审计 → 验收。

### Stage 2（已完成 ✅）

从“能跑一次”升级为“可稳定跑多任务”：队列、恢复、沙箱、结构化日志、Git 快照、可视化。

### Stage 2.5（进行中 🔴）

目标：补齐工具化能力，让 Engineer 在已有项目中"先读后改"，并引入人工审批关卡。

**P0（已完成 ✅）：**
- ✅ Tool/ToolRegistry 抽象 (`opc/tools/`)
- ✅ `read_file` / `edit_file` 实现
- ✅ `tool_call` 消息循环（最大 10 次/会话）
- ✅ prompt 升级为"先读后写"

**P1（已完成 ✅）：**
- ✅ `search_code` + `list_files` 工具
- ✅ QA 可读 Engineer 源码辅助分析
- ✅ `human_gate` 人工审批关卡

**P2：**
- Manager 标记客观/主观需求

### Stage 3（自主循环）

目标：从“单次修复”升级为“循环直到完成”。

- Engineer 小循环：失败→修复→再验收
- Manager 大循环：小循环多次失败后重规划
- 客观需求全自动，主观需求半自动（含 human_gate）

---

## 六、工具系统设计

### 设计原则

1. 核心工具优先自研，复杂能力再集成。
2. 保持统一接口，平台差异在实现层消化。
3. 最小权限原则：每个角色只看到需要的工具。
4. 工具调用全量进入统一审计日志。

### 第一批工具（Stage 2.5）

- `read_file`
- `write_file`
- `edit_file`
- `run_command`
- `search_code`
- `get_file_tree`

---

## 七、当前已落地 vs 规划中

### Stage 1 ✅

| 能力 | 落地文件 | 状态 |
|------|---------|------|
| Manager 拆解任务 | `opc/llm.py`, `opc/prompts.py` | ✅ |
| Engineer 写代码 | `opc/main.py` | ✅ |
| QA 独立审计 | `opc/main.py` | ✅ |
| JSON 协议驱动 | `opc/parser.py` | ✅ |
| 安全文件写入 | `opc/writer.py` | ✅ |

### Stage 2 ✅

| 能力 | 落地文件 | 状态 |
|------|---------|------|
| 队列化（inbox/ + FIFO） | `opc/queue.py` | ✅ |
| 独立 session 状态 + 断点恢复 | `opc/state.py` | ✅ |
| 回放保护（命令/文件去重） | `opc/queue.py` | ✅ |
| 沙箱强化（黑名单 + 资源限制 + session 超时） | `opc/sandbox.py`, `opc/executor.py` | ✅ |
| 资源释放验证（dequeue 前校验） | `opc/executor.py` | ✅ |
| JSONL 审计事件流 | `opc/logger.py` | ✅ |
| Git 快照与回滚 | `opc/git_snapshot.py` | ✅ |
| QA 可解释性（`failure_type` + `criterion_results`） | `opc/prompts.py` | ✅ |
| 成本统计与 HTML 面板 | `opc/metrics.py`, `opc/dashboard.py` | ✅ |
| `status.json` 原子写入 | `opc/state.py` | ✅ |
| 启动时清理孤儿进程 | `opc/executor.py`, `opc/main.py` | ✅ |

### Stage 2.5 🔴（进行中）

| 能力 | 落地文件 | 状态 | 备注 |
|------|---------|------|------|
| Tool/ToolRegistry 抽象 | `opc/tools/__init__.py` | ✅ | 单例注册模式 |
| `read_file` 工具 | `opc/tools/file_tools.py` | ✅ | 3000 行截断 |
| `edit_file` 工具 | `opc/tools/file_tools.py` | ✅ | 备份自动生成 |
| `search_code` 工具 | `opc/tools/search_tools.py` | ✅ | 正则+上下文 |
| `list_files` 工具 | `opc/tools/search_tools.py` | ✅ | 目录树 |
| `tool_call` 消息循环 | `opc/main.py` | ✅ | 最多 10 次/会话 |
| Engineer prompt 升级 | `opc/prompts.py` | ✅ | 含工具说明 |
| QA 读源码辅助分析 | `opc/prompts.py`, `opc/main.py` | ✅ | 传入 source_code |
| `human_gate` 人工审批关卡 | `opc/main.py` | ✅ | y/n/r 三选一 |
| `needs_human_review` 字段 | `opc/prompts.py` | ✅ | QA 输出格式 |
| Manager 标记客观/主观需求 | — | ⏳ P2 | |

> P0 bug 已全部修完：原子写入 ✅、孤儿清理 ✅、git snapshot 路径 ✅

---

## 八、竞品格局

策略：不比功能数量，专注把“闭环 + 全审计 + 独立 QA”做到极致。

---

## 九、开发节奏

- Stage 2.5：能力补全（读代码 + 改代码）
- Stage 3：自主循环（失败自动修复直到通过）
- 持续传播：Demo / 文章 / 社区

---

## 十、项目元信息

- 语言：Python 3.11+
- 依赖：openai、python-dotenv
- 许可证：MIT
- 模型：DeepSeek V4 Flash（Manager + Engineer）、MiniMax M2.5（QA）
- 运行环境：单机（当前以 macOS 流程为主）
- 包管理：uv
- 测试：pytest
