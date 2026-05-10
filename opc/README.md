# OPC 模块说明

> **主入口文档**：项目根目录 [README.md](../README.md)
> **规格文档**：[docs/opc_stage1_final_frozen_spec.md](../docs/opc_stage1_final_frozen_spec.md)

*最后更新：2026-05-11*

## 模块一览

```
opc/
├── main.py          # 入口 + 状态机主循环
├── config.py        # 全局配置
├── state.py         # 状态文件读写
├── queue.py         # 任务队列管理
├── llm.py           # LLM 调用封装
├── parser.py        # JSON 解析（严格 + 兜底）
├── writer.py        # 安全文件写入
├── executor.py      # 命令执行（后台 + 端口探测 + 清理）
├── sandbox.py       # 命令安全沙箱
├── logger.py        # 日志（文本 + JSONL 结构化）
├── prompts.py       # Prompt 模板 + 修复策略
├── metrics.py       # 成本/时延统计
├── dashboard.py     # HTML 可视化面板
├── git_snapshot.py  # 本地 Git 快照
├── agents/          # 角色定义
├── tasks/           # 任务队列 + 状态
├── runtime/         # 运行时状态
├── logs/            # 审计日志
└── memory/          # 产品记忆
```

## 环境要求

```bash
uv sync  # Python 3.11+, openai, python-dotenv
```

配置 `.env` 文件（参考 `.env.example`）：
```
DEEPSEEK_API_KEY=your-key
MINIMAX_API_KEY=your-key
```

## 运行

```bash
# 单任务模式（从 opc/tasks/inbox/ 读取第一个任务）
uv run python -m opc.main

# 查看统计
uv run python -c "from opc import get_metrics_summary; print(get_metrics_summary())"

# 生成面板
uv run python -c "from opc import generate_dashboard; generate_dashboard()"
# 然后 open opc/logs/dashboard.html
```
