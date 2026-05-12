"""
OPC 状态管理 - status.json 读写
支持 Stage 2 多 session + completed_stages 断点恢复
"""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from opc.config import STATUS_FILE, VALID_STAGES, TERMINAL_STAGES, TASKS_DIR


def get_session_id() -> str:
    """生成 session ID: YYYY-MM-DD-NNN"""
    today = datetime.now().strftime("%Y-%m-%d")
    return f"{today}-001"


def get_status_file(session_id: str) -> Path:
    """获取指定 session 的状态文件路径（Stage 2）"""
    return TASKS_DIR / session_id / "status.json"


def load_status(session_id: Optional[str] = None) -> dict:
    """
    加载状态文件
    
    Stage 2: 每个 session 有独立状态文件
    Stage 1 兼容: 如果 session_id=None 且旧状态文件存在，迁移到新路径
    
    Args:
        session_id: 会话 ID，为 None 则使用 STATUS_FILE（Stage 1 兼容）
    
    Returns:
        状态字典
    """
    if session_id:
        status_file = get_status_file(session_id)
    else:
        status_file = STATUS_FILE
    
    # Stage 1 兼容：如果新路径不存在但旧路径存在，迁移
    if session_id and not status_file.exists() and STATUS_FILE.exists():
        # 读取旧状态
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            old_status = json.load(f)
        
        # 迁移到新路径
        session_id_from_old = old_status.get("session_id", session_id)
        new_status_file = get_status_file(session_id_from_old)
        new_status_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(new_status_file, "w", encoding="utf-8") as f:
            json.dump(old_status, f, ensure_ascii=False, indent=2)
        
        # 备份旧文件
        STATUS_FILE.rename(STATUS_FILE.with_suffix(".json.bak"))
        
        return old_status
    
    if not status_file.exists():
        return {
            "stage": "inbox",
            "retry_count": 0,
            "parse_retry_count": 0,
            "session_id": session_id or get_session_id(),
            "completed_stages": [],
        }
    
    with open(status_file, "r", encoding="utf-8") as f:
        status = json.load(f)
    
    # 兼容旧版 status.json（没有 completed_stages）
    if "completed_stages" not in status:
        status["completed_stages"] = _infer_completed_stages(status.get("stage", "inbox"))
    
    return status


def save_status(status: dict, session_id: Optional[str] = None) -> None:
    """
    保存状态文件（原子写入）
    
    Args:
        status: 状态字典
        session_id: 会话 ID，为 None 则保存到 STATUS_FILE（Stage 1 兼容）
    """
    if session_id:
        status_file = get_status_file(session_id)
    else:
        status_file = STATUS_FILE
    
    status_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 原子写入：先写临时文件，再 rename（POSIX 保证原子性）
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=status_file.parent, suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, status_file)  # atomic on POSIX
    except Exception:
        # 写入失败时清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def init_status(session_id: Optional[str] = None) -> dict:
    """初始化状态"""
    session_id = session_id or get_session_id()
    status = {
        "stage": "inbox",
        "retry_count": 0,
        "parse_retry_count": 0,
        "session_id": session_id,
        "completed_stages": [],
    }
    save_status(status, session_id)
    return status


def _infer_completed_stages(stage: str) -> list:
    """根据当前阶段推断已完成阶段"""
    stage_order = ["inbox", "manager", "engineer", "qa"]
    
    if stage == "inbox":
        return []
    elif stage == "manager_done":
        return ["manager"]
    elif stage in ("engineer_done", "engineer_retry"):
        return ["manager", "engineer"]
    elif stage == "qa_done":
        return ["manager", "engineer", "qa"]
    elif stage in ("success", "failed", "parse_error"):
        return ["manager", "engineer", "qa"]
    
    return []


def mark_stage_completed(status: dict, stage_name: str) -> dict:
    """
    标记阶段已完成
    
    Args:
        status: 当前状态
        stage_name: 阶段名 (manager/engineer/qa)
    
    Returns:
        更新后的状态
    """
    if "completed_stages" not in status:
        status["completed_stages"] = []
    
    if stage_name not in status["completed_stages"]:
        status["completed_stages"].append(stage_name)
    
    return status


def is_stage_completed(status: dict, stage_name: str) -> bool:
    """检查阶段是否已完成"""
    return stage_name in status.get("completed_stages", [])


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
    status["parse_retry_count"] = 0
    return status


def increment_parse_retry(status: dict) -> dict:
    """增加解析失败计数"""
    status["parse_retry_count"] = status.get("parse_retry_count", 0) + 1
    return status
