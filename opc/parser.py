"""
OPC JSON 解析
严格解析 + 一次 markdown code fence 剥离兜底
禁止自动修复、智能补全
"""
import json
import re
from typing import Optional


def parse_json_safe(raw: str) -> Optional[dict]:
    """
    安全解析 JSON
    
    策略：
    1. 直接 json.loads
    2. 剥离 markdown code fence 后重试（一次）
    3. 两次都失败返回 None
    
    Args:
        raw: 原始输出字符串
    
    Returns:
        解析后的 dict，失败返回 None
    """
    # 策略 1: 直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    
    # 策略 2: 剥离 markdown code fence
    # 匹配 ```json ... ``` 或 ``` ... ```
    pattern = r"```(?:json)?\s*([\s\S]*?)```"
    match = re.search(pattern, raw)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    
    # 两次都失败
    return None


def parse_json_strict(raw: str) -> Optional[dict]:
    """
    严格 JSON 解析（不做任何兜底）
    
    Args:
        raw: 原始输出字符串
    
    Returns:
        解析后的 dict，失败返回 None
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def validate_manager_output(data: dict) -> bool:
    """验证 Manager 输出格式"""
    required_fields = ["goal", "steps", "acceptance_criteria"]
    for field in required_fields:
        if field not in data:
            return False
    
    # steps 必须是列表
    if not isinstance(data.get("steps"), list):
        return False
    
    # acceptance_criteria 必须是列表
    if not isinstance(data.get("acceptance_criteria"), list):
        return False
    
    return True


def validate_engineer_output(data: dict) -> bool:
    """
    验证 Engineer 输出格式

    支持两种格式：
    - tool_call 格式：{"tool_call": {"name": "...", "args": {...}}}
    - files 格式：{"files": [{"path": "...", "content": "..."}], "summary": "..."}
    """
    # 工具调用格式
    if "tool_call" in data:
        if not isinstance(data["tool_call"], dict):
            return False
        if "name" not in data["tool_call"]:
            return False
        # args 可以是空 dict
        return True

    # 文件输出格式（原有逻辑）
    if "files" not in data:
        return False

    if not isinstance(data.get("files"), list):
        return False

    # 每个文件必须有 path 和 content
    for f in data["files"]:
        if not isinstance(f, dict):
            return False
        if "path" not in f or "content" not in f:
            return False

    return True


def validate_qa_output(data: dict) -> bool:
    """
    验证 QA 输出格式
    
    支持新旧两种格式：
    - 新格式（有 criterion_results）
    - 旧格式（仅有 passed + reason）
    """
    # 基础字段
    if "passed" not in data:
        return False
    
    # 新格式：有 criterion_results
    if "criterion_results" in data:
        if not isinstance(data["criterion_results"], list):
            return False
        for result in data["criterion_results"]:
            if not isinstance(result, dict):
                return False
            if "criterion" not in result or "passed" not in result:
                return False
    
    # 旧格式：有 evidence
    if "evidence" in data:
        if not isinstance(data["evidence"], list):
            return False
    
    # 至少要有 reason 或 failed_checks 之一
    if not data.get("reason") and not data.get("failed_checks"):
        return False
    
    return True
