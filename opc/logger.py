"""
OPC 日志模块
会话、prompts、原始输出记录
"""
import json
import time
from pathlib import Path
from datetime import datetime

from opc.config import (
    LOGS_DIR, LOGS_SESSIONS, LOGS_PROMPTS, LOGS_RAW_OUTPUTS,
    STATUS_FILE,
)


def ensure_log_dirs():
    """确保日志目录存在"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_SESSIONS.mkdir(parents=True, exist_ok=True)
    LOGS_PROMPTS.mkdir(parents=True, exist_ok=True)
    LOGS_RAW_OUTPUTS.mkdir(parents=True, exist_ok=True)


def log_session(session_id: str, stage: str, data: dict) -> None:
    """
    记录会话摘要
    
    Args:
        session_id: 会话 ID
        stage: 当前阶段
        data: 其他数据
    """
    ensure_log_dirs()
    
    filename = f"{session_id}-session.json"
    filepath = LOGS_SESSIONS / filename
    
    # 读取已有数据
    sessions = []
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            sessions = json.load(f)
    
    # 添加新记录
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stage": stage,
        **data,
    }
    sessions.append(entry)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)


def log_prompt(
    session_id: str, 
    role: str, 
    prompt: str, 
    retry_count: int = 0
) -> None:
    """
    记录发送给 LLM 的 prompt
    
    Args:
        session_id: 会话 ID
        role: 角色名 (manager/engineer/qa)
        prompt: 完整 prompt
        retry_count: 重试次数
    """
    ensure_log_dirs()
    
    filename = f"{session_id}-{role}-retry-{retry_count}.prompt.txt"
    filepath = LOGS_PROMPTS / filename
    
    content = f"""# OPC Prompt Log
# Session: {session_id}
# Role: {role}
# Retry: {retry_count}
# Timestamp: {time.strftime("%Y-%m-%d %H:%M:%S")}

{prompt}
"""
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def log_raw_output(
    session_id: str, 
    role: str, 
    output: str, 
    retry_count: int = 0
) -> None:
    """
    记录 LLM 原始输出
    
    Args:
        session_id: 会话 ID
        role: 角色名
        output: 原始输出
        retry_count: 重试次数
    """
    ensure_log_dirs()
    
    filename = f"{session_id}-{role}-retry-{retry_count}.raw.txt"
    filepath = LOGS_RAW_OUTPUTS / filename
    
    content = f"""# OPC Raw Output Log
# Session: {session_id}
# Role: {role}
# Retry: {retry_count}
# Timestamp: {time.strftime("%Y-%m-%d %H:%M:%S")}

{output}
"""
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def log_parse_error(
    session_id: str,
    role: str,
    raw_output: str,
    retry_count: int,
) -> None:
    """
    记录 JSON 解析错误
    
    Args:
        session_id: 会话 ID
        role: 角色名
        raw_output: 原始输出
        retry_count: 当前重试次数
    """
    ensure_log_dirs()
    
    filename = f"{session_id}-{role}-retry-{retry_count}-parse-error.log"
    filepath = LOGS_RAW_OUTPUTS / filename
    
    content = f"""# JSON Parse Error
# Session: {session_id}
# Role: {role}
# Retry: {retry_count}
# Timestamp: {time.strftime("%Y-%m-%d %H:%M:%S")}

## Raw Output
{raw_output}

## Error
JSON 解析失败，请检查输出格式。
"""
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
