# Looper

AI 代码工厂项目集合。

## OPC Stage 1

一个以 Runner 为核心的最小 AI 代码工厂，跑通「需求 → 拆解 → 写代码 → 执行 → QA」的闭环。

### 快速开始

```bash
# 安装依赖
uv sync

# 设置环境变量
export DEEPSEEK_API_KEY="your-deepseek-api-key"
export MINIMAX_API_KEY="your-minimax-api-key"

# 运行
uv run python -m opc.main
```

### 项目结构

```
looper/
├── opc/              # OPC 主包
│   ├── __init__.py
│   ├── main.py       # 入口
│   ├── config.py     # 配置
│   ├── state.py      # 状态管理
│   ├── llm.py        # LLM 调用
│   ├── parser.py     # JSON 解析
│   ├── writer.py     # 文件写入
│   ├── executor.py   # 命令执行
│   ├── logger.py     # 日志
│   ├── prompts.py    # Prompt 模板
│   ├── agents/       # 角色定义
│   ├── tasks/        # 任务文件
│   ├── runtime/      # 运行时
│   ├── logs/         # 日志
│   └── memory/       # 记忆
├── docs/             # 规格文档
├── pyproject.toml    # uv 项目配置
└── .python-version   # Python 版本
```

### 核心设计

- **Manager** - 拆解任务（DeepSeek）
- **Engineer** - 写代码（DeepSeek）
- **QA** - 验证结果（MiniMax）
- **Runner** - 执行器和状态机

### 状态流转

```
inbox → manager_done → engineer_done → qa_done → success
                                    ↘ engineer_retry (失败重试，最多3次)
parse_error (JSON解析失败)
failed (重试超限)
```

## License

MIT
