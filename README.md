# Looper

最小可执行 AI 代码工厂。

*最后更新：2026-05-13*

> 以 Runner 为核心、以 JSON 协议为骨架、以真实执行结果为依据。

> 📌 **战略总览**：本文档聚焦快速上手与架构概览。完整定位、差异化分析、发展路线见 [docs/looper_positioning_and_roadmap.md](docs/looper_positioning_and_roadmap.md)（Stage 2.5 进行中）

## OPC Stage 1

一个以 Runner 为核心的最小 AI 代码工厂，跑通「需求 → 拆解 → 写代码 → 执行 → QA」的完整闭环。

### 快速开始

> 运行环境：最低支持 **Python 3.9**（`pyproject.toml`），推荐使用 **Python 3.11** 进行本地开发。


```bash
# 1. 安装依赖
uv sync

# 2. 配置 API keys
cp .env.example .env
# 编辑 .env 填入你的 DeepSeek 和 MiniMax key

# 3. 写需求（放到 inbox/ 目录）
echo "实现一个 Python HTTP 服务，监听 8080 端口，返回 Hello OPC" > opc/tasks/inbox/001.md

# 4. 运行
uv run python -m opc.main

# 5. 验证环境健康（首次运行前建议执行）
uv run pytest tests/ -q && uv run python3 scripts/check_doc_consistency.py
```

### 开发者下一步

遇到问题或想了解当前进度？先看：

1. **短期执行手册** → [`docs/sprint_guide.md`](docs/sprint_guide.md)（能力→测试→命令映射）
2. **战略总览** → [`docs/looper_positioning_and_roadmap.md`](docs/looper_positioning_and_roadmap.md)（定位、差异化、路线图）
3. **Stage 2 细则** → [`docs/stage2_next_phase_plan.md`](docs/stage2_next_phase_plan.md)（历史冻结文档）

### 运行示例

`opc/tasks/inbox.md` 写入：
```markdown
实现一个简单的 Python HTTP 服务
要求：
- 监听 8080 端口
- 根路径返回 'Hello OPC'
```

运行输出：
```
🆕 新会话: 2026-05-10-001

Stage: inbox          → 🤖 Manager 拆任务
Stage: manager_done   → 🤖 Engineer 写代码
Stage: engineer_done  → 🚀 启动服务 | ⏳ 端口探测 | 🧪 curl 测试
Stage: qa_done        → 🤖 QA 判定
🎉 任务成功完成！
```

### 配置

| 环境变量 | 说明 |
|----------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API key（Manager + Engineer） |
| `MINIMAX_API_KEY` | MiniMax API key（QA） |

模型：DeepSeek V4 Flash (`deepseek-v4-flash`) + MiniMax M2.5 (`MiniMax-M2.5`)

> **macOS 注意**：如果你开启了系统代理但代理进程没跑，Python HTTP 库会连不上 API。项目已内置 `no_proxy=*` 规避这个问题。

### 项目结构

```
looper/
├── opc/              # OPC 主包
│   ├── main.py       # 入口 + 状态机主循环
│   ├── config.py     # 配置 + dotenv 加载
│   ├── state.py      # status.json 读写
│   ├── llm.py        # LLM 调用封装
│   ├── parser.py     # JSON 解析（严格 + markdown fence 兜底）
│   ├── writer.py     # 安全文件写入（路径校验 + 备份）
│   ├── executor.py   # 命令执行（后台启动 + 端口探测 + 清理）
│   ├── logger.py     # 日志落盘
│   ├── prompts.py    # 各角色 Prompt 模板
│   ├── agents/       # 角色定义
│   ├── tasks/        # 任务文件
│   ├── runtime/      # 运行时状态
│   ├── logs/         # 审计日志
│   └── memory/       # 产品记忆
├── docs/             # 规格文档
├── pyproject.toml    # uv 项目配置
└── .env.example      # 环境变量模板
```

### 核心角色

| 角色 | 模型 | 职责 |
|------|------|------|
| **Manager** | DeepSeek | 读需求 → 拆任务 → 定义验收标准 |
| **Engineer** | DeepSeek | 根据任务写代码 → 修复失败 |
| **QA** | MiniMax | 分析执行结果 → 判定 pass/fail |
| **Runner** | — | 状态机 + 命令执行 + 协议解析 |

### 状态流转

```
inbox
  → manager_done
    → engineer_done (tool_call 循环: read_file / edit_file / search_code)
      → qa_done → success    ✅
      → qa_done → human_review → 🚦 人工审批 → success / failed

qa_done (失败)
  → engineer_retry (最多 3 次) → success / failed ❌

任一角色 JSON 解析失败
  → 重试当前角色 1 次
    → 仍失败 → parse_error   ⚠️
```

### 错误处理

| 错误类型 | 行为 |
|----------|------|
| **API 调用失败** | 重试 3 次，超限退出 |
| **JSON 解析失败** | 重试 1 次，仍失败 → `parse_error` |
| **配置缺失** | 启动时检查 API keys，缺失直接退出 |
| **QA 判定失败** | 自动重试工程师修复，最多 3 次 |

### 关键设计

- **JSON 协议驱动**：所有 LLM 输出必须是严格 JSON
- **端口探测优先**：后台服务启动后先探端口再跑测试（非固定 sleep）
- **日志全审计**：每步落盘，可复现可调试
- **安全文件写入**：拒绝绝对路径、路径穿越、隐藏目录

## License

MIT
