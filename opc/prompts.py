"""
OPC Prompt 模板
"""
from pathlib import Path
from typing import Optional

from opc.config import (
    PROJECT_ROOT, TASKS_DIR, AGENTS_DIR, MEMORY_DIR, RUNTIME_DIR,
)


def load_memory(product_md: Optional[str] = None, decisions_md: Optional[str] = None) -> dict:
    """加载 memory 文件"""
    memory = {}
    
    product_path = MEMORY_DIR / "product.md"
    if product_path.exists() and product_md is None:
        product_md = product_path.read_text(encoding="utf-8")
    
    if product_md:
        memory["product"] = product_md
    
    decisions_path = MEMORY_DIR / "decisions.md"
    if decisions_path.exists() and decisions_md is None:
        decisions_md = decisions_path.read_text(encoding="utf-8")
    
    if decisions_md:
        memory["decisions"] = decisions_md
    
    return memory


def build_manager_prompt(
    inbox_content: str,
    product_md: Optional[str] = None,
    decisions_md: Optional[str] = None,
) -> str:
    """构建 Manager prompt"""
    memory = load_memory(product_md, decisions_md)
    
    prompt = f"""# Manager 角色

你是 OPC 系统的 Manager，负责将需求拆解为可执行的任务。

## 重要约束
1. **你只输出 JSON**，不要输出任何解释文字
2. **不要用 markdown 代码块包裹 JSON**
3. 所有命令必须是 Runner 可执行的真实命令
4. 验收标准必须可验证，不能抽象

## Memory

"""
    
    if memory.get("product"):
        prompt += f"### Product\n{memory['product']}\n\n"
    
    if memory.get("decisions"):
        prompt += f"### Decisions\n{memory['decisions']}\n\n"
    
    prompt += f"""## 需求 (inbox.md)

{inbox_content}

## 输出要求

请输出以下格式的 JSON：

```json
{{
  "goal": "本次任务目标",
  "steps": ["步骤1", "步骤2", "..."],
  "acceptance_criteria": ["验收标准1", "验收标准2", "..."],
  "background_commands": ["需要后台启动的命令"],
  "test_commands": ["前台验证命令"],
  "startup_wait_seconds": 启动最大等待秒数,
  "health_check_port": 服务端口号,
  "language": "python / javascript / typescript / go / rust / shell / other",
  "dependencies": ["包名列表，无需依赖则为空数组"],
  "notes": "其他约束或提示"
}}
```

**字段说明**：
- `language`：项目实现语言。如不确定可以从 `python / javascript / typescript / go / rust / shell / other` 选一个最接近的
- `dependencies`：需要的第三方依赖包名。Python 用 `pip install flask==3.0` 格式，JS 用 npm 包名
- `background_commands`：后台命令用 `&` 结尾，如 `python3 server.py &`
- `health_check_port`：服务端口号（必须设置），Runner 会先探端口再执行测试
- `startup_wait_seconds`：端口探测的最大超时秒数，默认 10
- `test_commands`：用 `curl` 验证的命令

**注意**：
- `background_commands` 先执行
- Runner 等待 `startup_wait_seconds` 后执行 `test_commands`
- 命令要写完整（如 `node src/index.js`，不是 `npm start`）

请直接输出 JSON：
"""
    
    return prompt


def build_engineer_prompt(
    task_json: dict,
    qa_report: Optional[dict] = None,
    project_files: Optional[dict] = None,
    tool_result: Optional[str] = None,
) -> str:
    """构建 Engineer prompt（支持工具调用循环）"""
    prompt = f"""# Engineer 角色

你是 OPC 系统的 Engineer，负责根据任务生成代码改动。

## 重要约束
1. **你只输出 JSON**，不要输出 markdown
2. **可以调用工具读取现有文件**
3. 只能修改项目工作区内文件
4. 不改需求，不跳过验收标准

## 当前任务

**Goal**: {task_json.get('goal', '')}

**Steps**:
"""

    for i, step in enumerate(task_json.get('steps', []), 1):
        prompt += f"{i}. {step}\n"

    prompt += "\n**Acceptance Criteria**:\n"
    for criteria in task_json.get('acceptance_criteria', []):
        prompt += f"- {criteria}\n"

    if task_json.get('notes'):
        prompt += f"\n**Notes**: {task_json['notes']}\n"

    # 工具说明（Stage 2.5）
    try:
        from opc.tools import build_tools_description

        prompt += f"\n{build_tools_description()}\n"
    except Exception:
        # 工具系统不可用时降级
        pass

    if project_files:
        prompt += "\n## 当前项目文件\n"
        for path, content in project_files.items():
            prompt += f"\n### {path}\n```\n{content}\n```\n"

    if tool_result:
        prompt += f"""
## 工具执行结果

{tool_result}

请继续调用工具读取需要修改的文件，或者输出最终代码。
"""

    if qa_report:
        from opc.prompts import build_repair_context

        prompt += f"""
## QA 报告 (上一轮失败原因)

**Passed**: {qa_report.get('passed', False)}
**Reason**: {qa_report.get('reason', 'N/A')}
"""

        if not qa_report.get('passed', False):
            failure_type = qa_report.get('failure_type', 'unknown')
            repair_context = build_repair_context(
                failure_type, qa_report, task_json
            )
            prompt += f"\n{repair_context}\n"
        else:
            evidence = qa_report.get('evidence', [])
            if evidence and isinstance(evidence, list):
                prompt += "\n**Evidence**:\n"
                for ev in evidence:
                    if isinstance(ev, dict):
                        prompt += f"- Command: {ev.get('command', 'N/A')}\n"
                        prompt += (
                            f"  Stdout: {ev.get('stdout', 'N/A')[:200]}\n"
                        )
                        prompt += (
                            f"  Stderr: {ev.get('stderr', 'N/A')[:200]}\n"
                        )
                        prompt += f"  Exit Code: {ev.get('exit_code', 'N/A')}\n"

    prompt += """
## 输出要求

可以选择以下两种输出格式：

**格式 1: 调用工具**（推荐用于读取现有文件后再修改）
```json
{"tool_call": {"name": "read_file", "args": {"path": "src/index.js"}}}
```

**格式 2: 输出最终代码**（所有工具调用完成后）
```json
{
  "files": [
    {
      "path": "src/index.js",
      "content": "完整文件内容..."
    }
  ],
  "summary": "本轮改动摘要"
}
```

注意：
- 可以多次调用工具（每次一个）
- 完成所有读取后，输出最终代码
- 不要在 tool_call 输出中包含 files

请直接输出 JSON：
"""

    return prompt


def build_qa_prompt(
    task_json: dict,
    evidence: list,
    source_code: Optional[dict] = None,
) -> str:
    """构建 QA prompt（支持源码上下文）"""
    prompt = f"""# QA 角色

你是 OPC 系统的 QA，负责判断执行结果是否满足验收标准。

## 重要约束
1. **你不会执行命令**
2. **你会收到实际命令输出**
3. **你会收到 Engineer 写的源码作为参考**
4. **你只根据验收标准和执行结果做判断**
5. **你只输出 JSON**

## 当前任务

**Goal**: {task_json.get('goal', '')}

**Acceptance Criteria**:
"""

    for i, criteria in enumerate(task_json.get('acceptance_criteria', []), 1):
        prompt += f"{i}. {criteria}\n"

    prompt += """
## 实际执行结果 (Evidence)

"""
    
    if isinstance(evidence, list):
        for i, ev in enumerate(evidence, 1):
            if isinstance(ev, dict):
                prompt += f"### Command {i}: {ev.get('command', 'N/A')}\n"
                prompt += f"- Exit Code: {ev.get('exit_code', 'N/A')}\n"
                prompt += f"- Stdout: {ev.get('stdout', 'N/A')[:500]}\n"
                prompt += f"- Stderr: {ev.get('stderr', 'N/A')[:500]}\n\n"
    elif isinstance(evidence, dict):
        prompt += f"- Command: {evidence.get('command', 'N/A')}\n"
        prompt += f"- Exit Code: {evidence.get('exit_code', 'N/A')}\n"
        prompt += f"- Stdout: {evidence.get('stdout', 'N/A')[:500]}\n"
        prompt += f"- Stderr: {evidence.get('stderr', 'N/A')[:500]}\n"

    # 源码上下文（Stage 2.5 P1: QA 可读源码辅助分析）
    if source_code:
        prompt += "\n## Engineer 写的源码（供参考）\n\n"
        for path, content in source_code.items():
            truncated = content[:1500] if len(content) > 1500 else content
            if len(content) > 1500:
                truncated += f"\n... [truncated, {len(content)} total chars]"
            prompt += f"### {path}\n```\n{truncated}\n```\n\n"

    prompt += """
## 输出要求

请输出以下格式的 JSON：

```json
{
  "passed": true/false,
  "reason": "判断理由",
  "failed_checks": ["未通过的验收标准"],
  "evidence": [
    {
      "command": "实际执行的命令",
      "stdout": "标准输出",
      "stderr": "标准错误",
      "exit_code": 退出码
    }
  ],
  "next_action": "accept/send_back_to_engineer",
  "failure_type": "compile_error/test_failure/timeout/runtime_error/qa_parse_error/qa_validation_error/unknown",
  "needs_human_review": false,
  "suggested_fix": "建议修复方向（失败时必填）",
  "criterion_results": [
    {
      "criterion": "验收标准原文",
      "passed": true/false,
      "evidence": "对应的运行证据",
      "risk": "high/medium/low"
    }
  ]
}
```

**注意**：`evidence` 必须包含每条 `test_command` 的执行结果。

**关于 `needs_human_review`**：如果任务涉及主观判断（如 UI 美观、文案质量、架构选择），且你无法仅凭客观标准判定，请设置 `needs_human_review: true`，系统将暂停等待人工审批。

请直接输出 JSON：
"""
    
    return prompt


def save_agent_prompt(role: str, content: str) -> None:
    """保存角色 prompt 到文件"""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    
    role_file = AGENTS_DIR / f"{role}.md"
    with open(role_file, "w", encoding="utf-8") as f:
        f.write(content)


def load_agent_prompt(role: str) -> str:
    """加载角色 prompt"""
    role_file = AGENTS_DIR / f"{role}.md"
    if role_file.exists():
        return role_file.read_text(encoding="utf-8")
    return ""


# =====================
# 任务类型模板
# =====================

TASK_TYPE_TEMPLATES = {
    "http_api": {
        "name": "HTTP API 服务",
        "keywords": ["端口", "监听", "HTTP", "curl", "localhost", "GET", "POST", "REST"],
        "test_template": 'curl -s http://localhost:{port}/',
        "health_check": True,
    },
    "cli": {
        "name": "命令行工具",
        "keywords": ["CLI", "命令行", "参数", "--help", "-h", "usage"],
        "test_template": 'python3 {script} --help',
        "health_check": False,
    },
    "script": {
        "name": "脚本工具",
        "keywords": ["脚本", "shell", "bash", "./"],
        "test_template": './{script}',
        "health_check": False,
    },
}


def infer_task_type(inbox_content: str) -> str:
    """
    根据 inbox 内容推断任务类型
    
    Returns:
        http_api / cli / script
    """
    content_lower = inbox_content.lower()
    
    scores = {}
    for task_type, template in TASK_TYPE_TEMPLATES.items():
        score = sum(1 for keyword in template["keywords"] if keyword.lower() in content_lower)
        scores[task_type] = score
    
    if not any(scores.values()):
        return "script"  # 默认类型
    
    return max(scores, key=scores.get)


# =====================
# 修复 Prompt 模板
# =====================

REPAIR_PROMPT_TEMPLATES = {
    "test_failure": """这是测试失败修复轮次。上一步 QA 已经运行了测试并给出了失败原因。

**你的策略**：
1. 先用 `read_file` 读取相关代码，理解 QA 失败的那一行
2. 如果明确知道问题所在，用 `edit_file` 精准改那一行（不要重写整个文件）
3. 如果需要确认，用 `search_code` 或 `list_files` 了解上下文
4. 改完后输出 `files` JSON，**不要再调用工具**

**禁止**：在没有 read_file 的情况下直接输出完整的 files JSON（那只是重复了上一次的错误）。""",

    "compile_error": """这是编译错误修复轮次。上一步的代码有语法或导入错误。

**你的策略**：
1. 先用 `read_file` 定位报错文件和行号
2. 修复语法错误或缺失的 import
3. 保持其他功能不变，只做最小修改
4. 改完后输出 `files` JSON，**不要再调用工具**

**重点**：Python 常见编译错误包括：缩进问题、拼写错误、缺失引号、括号不匹配、缺少 import。""",

    "timeout": """这是超时错误修复轮次。上一步的代码可能存在死循环或阻塞。

**你的策略**：
1. 先用 `read_file` 读取代码，找到可能导致超时的位置
2. 常见原因：无限循环、无限递归、缺少超时保护、外部调用阻塞
3. 加入超时处理或修复循环逻辑
4. 改完后输出 `files` JSON，**不要再调用工具**

**性能优先**：能用简单循环就不用复杂递归，能设置超时就不要无限等待。""",

    "runtime_error": """这是运行时错误修复轮次。代码执行时崩溃了。

**你的策略**：
1. 先用 `read_file` 读取代码，找到可能崩溃的位置
2. 常见原因：除零、访问 None 属性、列表越界、类型不匹配
3. 添加防御性检查（如 `if x is None`）或修正逻辑
4. 改完后输出 `files` JSON，**不要再调用工具**

**防御性编程**：不要假设输入总是合法的。""",

    "unknown": """这是通用修复轮次。验收失败但原因未知。

**你的策略**：
1. 用 `read_file` 读取所有相关代码
2. 用 `search_code` 搜索与验收标准相关的逻辑
3. 结合 QA 报告中的证据，理解"预期"和"实际"的差异
4. 制定修复计划，一次只改一个点
5. 改完后输出 `files` JSON，**不要再调用工具**

**不要**：猜测原因而不读代码就重写整个文件。""",

    "qa_parse_error": """这是 QA 评估错误修复轮次。QA 模型无法将输出解析为有效 JSON。

**你的策略**：
1. 用 `read_file` 读取 Engineer 写的代码
2. 确认代码逻辑是否正确实现了验收标准
3. 如果代码本身有问题，用 `edit_file` 修复
4. 如果代码看起来正确，可能是测试命令问题，考虑用 `search_code` 检查
5. 改完后输出 `files` JSON，**不要再调用工具**

**重点**：QA 解析失败不一定代表代码有问题，可能是 QA 模型太弱或测试命令格式不对。""",

    "qa_validation_error": """这是 QA 评估错误修复轮次。QA 输出格式不符合要求（缺少必填字段）。

**你的策略**：
1. 先确认代码本身是否正确实现了验收标准
2. 如果代码有问题，用 `edit_file` 精准修复
3. 如果代码正确，问题可能在测试命令或验收标准定义上
4. 改完后输出 `files` JSON，**不要再调用工具**""",
}


def build_repair_context(
    failure_type: str,
    qa_report: dict,
    task_data: dict,
) -> str:
    """
    构建修复上下文的提示词
    
    Args:
        failure_type: 失败类型
        qa_report: QA 报告
        task_data: 任务数据
    
    Returns:
        修复提示词
    """
    template = REPAIR_PROMPT_TEMPLATES.get(failure_type, REPAIR_PROMPT_TEMPLATES["unknown"])
    
    context = f"## 修复提示\n{template}\n\n"
    
    # 添加失败检查
    failed_checks = qa_report.get("failed_checks", [])
    if failed_checks:
        context += "## 失败的检查\n"
        for check in failed_checks:
            context += f"- {check}\n"
        context += "\n"
    
    # 添加证据
    evidence = qa_report.get("evidence", [])
    if evidence and isinstance(evidence, list):
        context += "## 执行证据\n"
        for ev in evidence:
            if isinstance(ev, dict):
                context += f"命令: {ev.get('command', 'N/A')}\n"
                context += f"退出码: {ev.get('exit_code', 'N/A')}\n"
                context += f"Stdout: {ev.get('stdout', 'N/A')[:300]}\n"
                context += f"Stderr: {ev.get('stderr', 'N/A')[:300]}\n\n"
    
    # 添加逐条判定结果（如果有）
    criterion_results = qa_report.get("criterion_results", [])
    if criterion_results:
        context += "## 逐条判定结果\n"
        for result in criterion_results:
            status = "✅" if result.get("passed") else "❌"
            context += f"{status} {result.get('criterion', 'N/A')}\n"
            if result.get("evidence"):
                context += f"   证据: {result.get('evidence')}\n"
        context += "\n"
    
    # 添加建议修复方向（如果有）
    suggested_fix = qa_report.get("suggested_fix")
    if suggested_fix:
        context += f"## 建议的修复方向\n{suggested_fix}\n\n"
    
    return context


def build_manager_replan_prompt(
    original_goal: str,
    retry_history: list,
    project_files: Optional[dict] = None,
) -> str:
    """
    构建 Manager 大循环重新规划的 prompt

    Args:
        original_goal: 原始任务目标（不可偏离）
        retry_history: 小循环失败历史
            [{"failure_type": "...", "qa_summary": "...", "files_written": ["..."]}, ...]
        project_files: 当前项目文件 dict[path, content]
    """
    prompt = """# Manager 角色（重新规划）

你是 OPC 系统的 Manager。小循环（3次 Engineer retry）全部失败，现在需要你介入重新规划。

## 重要约束
1. **你只输出 JSON**，不要输出任何解释文字
2. **不要用 markdown 代码块包裹 JSON**
3. 原始目标不可偏离
4. 必须换思路，不要重复上一次的方案

## 原始目标（不可偏离）

{original_goal}

## 小循环失败历史

请仔细分析以下失败记录，理解"为什么之前的方案失败了"：

{retry_history}

"""

    # 格式化失败历史
    history_text = ""
    for i, record in enumerate(retry_history, 1):
        history_text += f"**第 {i} 次小循环**\n"
        history_text += f"- 失败类型: {record.get('failure_type', 'unknown')}\n"
        history_text += f"- QA 摘要: {record.get('qa_summary', 'N/A')}\n"
        history_text += f"- 修改过的文件: {', '.join(record.get('files_written', [])) or '无'}\n\n"

    if not history_text:
        history_text = "（无失败历史记录）\n"

    prompt = prompt.format(
        original_goal=original_goal,
        retry_history=history_text,
    )

    # 当前项目文件
    if project_files:
        prompt += "## 当前项目文件\n"
        for path, content in project_files.items():
            prompt += f"\n### {path}\n```\n{content[:2000]}\n```\n"

    prompt += """
## 重新规划要求

之前的方案都失败了。请换一个完全不同的思路重新规划。

**换思路的要点**：
- 分析每次失败的根本原因，不要只看表面
- 如果是算法逻辑错误，换一个算法思路
- 如果是边界条件处理失败，重新审视输入约束
- 如果是实现方式有问题，考虑完全不同的技术方案

## 输出要求

请输出以下格式的 JSON：

```json
{
  "goal": "本次任务目标（与原始目标保持一致）",
  "steps": ["步骤1", "步骤2", "..."],
  "acceptance_criteria": ["标准1", "标准2", "..."],
  "notes": "实现注意事项（重点说明如何避免之前的失败原因）"
}
```

**注意**：
- goal 必须与原始目标一致
- steps 和 acceptance_criteria 可以完全不同
- notes 里要明确写出"如何避免重蹈覆辙"
"""
    return prompt
