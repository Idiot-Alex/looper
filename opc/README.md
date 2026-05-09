# OPC Stage 1 Runner

OPC = Operator-Powered Code factory，一个以 Runner 为核心的最小 AI 代码工厂。

## 快速开始

### 1. 安装依赖

```bash
pip install openai
```

### 2. 设置环境变量

```bash
export DEEPSEEK_API_KEY="your-deepseek-api-key"
export MINIMAX_API_KEY="your-minimax-api-key"
```

### 3. 编写需求

编辑 `opc/tasks/inbox.md`:

```markdown
实现一个 Node.js Hello API
要求：
- 监听 3000 端口
- 访问 / 时返回 Hello OPC
```

### 4. 运行

```bash
python -m opc.main
# 或
python opc/main.py
```

## 目录结构

```
opc/
├── agents/           # 角色定义
├── tasks/           # 任务状态
│   ├── inbox.md     # 需求
│   ├── status.json  # 状态
│   ├── task.json    # Manager 输出
│   ├── engineer_output.json  # Engineer 输出
│   └── qa_report.json       # QA 报告
├── runtime/         # 执行结果
├── logs/           # 审计日志
└── memory/        # 产品记忆
```

## 状态流转

```
inbox
→ manager_done
→ engineer_done
→ qa_done
→ success ✓

qa_done (失败)
→ engineer_retry (最多3次)
→ success ✓ 或 failed ✗

任意阶段 JSON 解析失败
→ parse_error ⚠️
```

## API Keys

- **DeepSeek**: 用于 Manager 和 Engineer
  - 获取: https://platform.deepseek.com/
  
- **MiniMax**: 用于 QA
  - 获取: https://www.minimaxi.com/

## 测试

```bash
# 正常运行测试
python -m opc.main

# 模拟失败测试（注入 bug）
# 在 inbox.md 中写入不可能完成的需求

# 模拟协议失败测试
# 手动修改 LLM 返回非 JSON 格式
```
