"""
OPC 日志模块
会话、prompts、原始输出记录 + 结构化 JSONL 事件流
"""
import json
import time
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from opc.config import (
    LOGS_DIR, LOGS_SESSIONS, LOGS_PROMPTS, LOGS_RAW_OUTPUTS,
    STATUS_FILE, LOGS_JSONL,
)


# =====================
# 结构化 JSONL 事件流
# =====================

def log_event(
    event_type: str,
    session_id: str,
    data: Optional[Dict[str, Any]] = None,
    stage: Optional[str] = None,
) -> None:
    """
    记录结构化事件到 JSONL 文件
    
    事件 schema:
    {
        "timestamp": "2026-05-10T17:51:00+08:00",
        "event_type": "llm_call / file_write / command_run / qa_decision / session_timeout",
        "session_id": "2026-05-10-001",
        "stage": "manager",
        "event_id": "uuid",
        ...data
    }
    
    Args:
        event_type: 事件类型
        session_id: 会话 ID
        data: 事件数据
        stage: 当前阶段
    """
    event = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "session_id": session_id,
        "event_id": str(uuid.uuid4())[:8],
    }
    
    if stage:
        event["stage"] = stage
    
    if data:
        event.update(data)
    
    # 写入 JSONL
    LOGS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(LOGS_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def log_llm_call(
    session_id: str,
    role: str,
    model: str,
    tokens_used: Optional[int] = None,
    duration_ms: Optional[int] = None,
    success: bool = True,
    error: Optional[str] = None,
    stage: Optional[str] = None,
) -> None:
    """记录 LLM 调用事件"""
    log_event(
        "llm_call",
        session_id,
        {
            "role": role,
            "model": model,
            "tokens_used": tokens_used,
            "duration_ms": duration_ms,
            "success": success,
            "error": error,
        },
        stage,
    )


def log_file_write(
    session_id: str,
    file_path: str,
    size_bytes: int,
    skipped: bool = False,
) -> None:
    """记录文件写入事件"""
    log_event(
        "file_write",
        session_id,
        {
            "file_path": file_path,
            "size_bytes": size_bytes,
            "skipped": skipped,
        },
    )


def log_command_run(
    session_id: str,
    command: str,
    exit_code: int,
    stdout_preview: Optional[str] = None,
    stderr_preview: Optional[str] = None,
    duration_ms: Optional[int] = None,
    command_type: str = "foreground",  # foreground / background
) -> None:
    """记录命令执行事件"""
    log_event(
        "command_run",
        session_id,
        {
            "command": command,
            "exit_code": exit_code,
            "stdout_preview": (stdout_preview or "")[:200],
            "stderr_preview": (stderr_preview or "")[:200],
            "duration_ms": duration_ms,
            "command_type": command_type,
        },
    )


def log_qa_decision(
    session_id: str,
    passed: bool,
    reason: str,
    failure_type: Optional[str] = None,
) -> None:
    """记录 QA 判定事件"""
    log_event(
        "qa_decision",
        session_id,
        {
            "passed": passed,
            "reason": reason,
            "failure_type": failure_type,
        },
        "qa",
    )


def log_session_timeout(
    session_id: str,
    timeout_seconds: int,
    elapsed_seconds: int,
    stage: str,
) -> None:
    """记录 Session 超时事件"""
    log_event(
        "session_timeout",
        session_id,
        {
            "timeout_seconds": timeout_seconds,
            "elapsed_seconds": elapsed_seconds,
            "stage": stage,
        },
        stage,
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
