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
  "notes": "其他约束或提示"
}}
```

**字段说明**：
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
) -> str:
    """构建 Engineer prompt"""
    prompt = f"""# Engineer 角色

你是 OPC 系统的 Engineer，负责根据任务生成代码改动。

## 重要约束
1. **你只输出 JSON**，不要输出 markdown
2. **只给出完整文件内容**，不给 patch/diff
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
    
    if project_files:
        prompt += "\n## 当前项目文件\n"
        for path, content in project_files.items():
            prompt += f"\n### {path}\n```\n{content}\n```\n"
    
    if qa_report:
        # 导入修复上下文构建函数
        from opc.prompts import build_repair_context
        
        prompt += f"""
## QA 报告 (上一轮失败原因)

**Passed**: {qa_report.get('passed', False)}
**Reason**: {qa_report.get('reason', 'N/A')}
"""
        
        # 添加修复上下文
        if not qa_report.get('passed', False):
            failure_type = qa_report.get('failure_type', 'unknown')
            repair_context = build_repair_context(failure_type, qa_report, task_json)
            prompt += f"\n{repair_context}\n"
        else:
            # 即使通过了也给出证据供参考
            evidence = qa_report.get('evidence', [])
            if evidence and isinstance(evidence, list):
                prompt += "\n**Evidence**:\n"
                for ev in evidence:
                    if isinstance(ev, dict):
                        prompt += f"- Command: {ev.get('command', 'N/A')}\n"
                        prompt += f"  Stdout: {ev.get('stdout', 'N/A')[:200]}\n"
                        prompt += f"  Stderr: {ev.get('stderr', 'N/A')[:200]}\n"
                        prompt += f"  Exit Code: {ev.get('exit_code', 'N/A')}\n"
    
    prompt += """
## 输出要求

请输出以下格式的 JSON：

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

请直接输出 JSON：
"""
    
    return prompt


def build_qa_prompt(
    task_json: dict,
    evidence: list,
) -> str:
    """构建 QA prompt"""
    prompt = f"""# QA 角色

你是 OPC 系统的 QA，负责判断执行结果是否满足验收标准。

## 重要约束
1. **你不会执行命令**
2. **你会收到实际命令输出**
3. **你只根据验收标准和执行结果做判断**
4. **你只输出 JSON**

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
  "failure_type": "compile_error/test_failure/timeout/unknown",
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
    "compile_error": "检测到编译错误。请修复以下问题，专注于解决错误，不要改变其他功能。",
    "test_failure": "测试失败。请根据 QA 报告中的失败检查和证据，分析问题并修复代码。",
    "timeout": "命令执行超时。可能原因：代码死循环、等待时间过长或资源耗尽。请优化代码性能或增加超时处理。",
    "unknown": "验收失败。请分析 QA 报告中的失败原因，理解预期行为与实际行为的差异，然后修复问题。",
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
