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
    """验证 Engineer 输出格式"""
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
    """验证 QA 输出格式"""
    required_fields = ["passed", "reason", "evidence", "next_action"]
    for field in required_fields:
        if field not in data:
            return False
    
    # evidence 必须是列表
    if not isinstance(data.get("evidence"), list):
        return False
    
    return True
