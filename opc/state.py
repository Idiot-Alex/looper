"""
OPC 状态管理 - status.json 读写
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from opc.config import STATUS_FILE, VALID_STAGES, TERMINAL_STAGES


def get_session_id() -> str:
    """生成 session ID: YYYY-MM-DD-NNN"""
    today = datetime.now().strftime("%Y-%m-%d")
    # 简单计数，实际可用更复杂逻辑
    return f"{today}-001"


def load_status() -> dict:
    """加载状态文件"""
    if not STATUS_FILE.exists():
        return {
            "stage": "inbox",
            "retry_count": 0,
            "parse_retry_count": 0,
            "session_id": get_session_id(),
        }
    
    with open(STATUS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_status(status: dict) -> None:
    """保存状态文件"""
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def init_status(session_id: Optional[str] = None) -> dict:
    """初始化状态"""
    status = {
        "stage": "inbox",
        "retry_count": 0,
        "parse_retry_count": 0,
        "session_id": session_id or get_session_id(),
    }
    save_status(status)
    return status


def is_terminal(stage: str) -> bool:
    """判断是否终态"""
    return stage in TERMINAL_STAGES


def validate_stage(stage: str) -> bool:
    """验证状态是否合法"""
    return stage in VALID_STAGES


def reset_retry(status: dict) -> dict:
    """重置重试计数（进入 engineer_retry 时调用）"""
    status["retry_count"] = 0
    status["parse_retry_count"] = 0
    return status


def increment_retry(status: dict) -> dict:
    """增加重试计数"""
    status["retry_count"] = status.get("retry_count", 0) + 1
    status["parse_retry_count"] = 0  # 新角色调用，重置解析重试计数
    return status


def increment_parse_retry(status: dict) -> dict:
    """增加解析失败计数"""
    status["parse_retry_count"] = status.get("parse_retry_count", 0) + 1
    return status
