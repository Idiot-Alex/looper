"""
OPC 任务队列管理
支持 inbox/ 目录多任务 + FIFO 调度
"""
import hashlib
import json
import shutil
from pathlib import Path
from typing import List, Optional, Dict

from opc.config import INBOX_DIR, DONE_DIR, TASKS_DIR, INBOX_FILE


def ensure_dirs():
    """确保队列目录存在"""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    DONE_DIR.mkdir(parents=True, exist_ok=True)


def migrate_inbox_md():
    """
    如果 inbox.md 存在但 inbox/ 为空，自动迁移
    兼容 Stage 1 的单文件模式
    """
    ensure_dirs()
    
    if INBOX_FILE.exists():
        # 统计 inbox/ 中已有的文件
        inbox_files = list(INBOX_DIR.glob("*.md"))
        if not inbox_files:
            # 读取 inbox.md 内容
            content = INBOX_FILE.read_text(encoding="utf-8")
            
            # 生成 session_id（复用原逻辑）
            from datetime import datetime
            session_id = datetime.now().strftime("%Y-%m-%d") + "-001"
            
            # 写入 inbox/ 目录
            target = INBOX_DIR / f"{session_id}.md"
            target.write_text(content, encoding="utf-8")
            
            print(f"📦 从 inbox.md 迁移到 {target}")
            
            # 备份 inbox.md（不删除）
            INBOX_FILE.rename(INBOX_FILE.with_suffix(".md.bak"))
    
    # 清理备份
    backup = INBOX_FILE.with_suffix(".md.bak")
    if backup.exists() and INBOX_DIR.glob("*.md"):
        backup.unlink()


def scan_inbox() -> List[Dict]:
    """
    扫描 inbox/ 目录，返回 FIFO 排序的任务列表
    
    排序规则：
    1. 按文件 mtime 升序（先提交的先处理）
    2. mtime 相同则按文件名字典序
    
    Returns:
        [{"session_id": "2026-05-10-001", "path": Path(...), "mtime": float}, ...]
    """
    ensure_dirs()
    
    files = []
    for f in INBOX_DIR.glob("*.md"):
        mtime = f.stat().st_mtime
        session_id = f.stem  # 文件名去掉 .md
        files.append({
            "session_id": session_id,
            "path": f,
            "mtime": mtime,
        })
    
    # FIFO 排序：mtime 升序，mtime 相同则字典序
    files.sort(key=lambda x: (x["mtime"], x["session_id"]))
    
    return files


def get_next_task() -> Optional[Dict]:
    """
    获取下一个待处理任务
    
    Returns:
        {"session_id": "...", "path": Path(...)} 或 None
    """
    tasks = scan_inbox()
    return tasks[0] if tasks else None


def mark_done(session_id: str) -> bool:
    """
    将已完成的任务从 inbox/ 移到 done/
    
    Args:
        session_id: 会话 ID
    
    Returns:
        True: 成功移动
        False: 文件不存在
    """
    ensure_dirs()
    
    src = INBOX_DIR / f"{session_id}.md"
    if not src.exists():
        return False
    
    dst = DONE_DIR / f"{session_id}.md"
    
    # 避免覆盖（done 中已有同名文件则加序号）
    if dst.exists():
        counter = 1
        while dst.exists():
            dst = DONE_DIR / f"{session_id}_{counter}.md"
            counter += 1
    
    shutil.move(str(src), str(dst))
    print(f"✅ 任务 {session_id} 已移至 done/")
    return True


def get_task_inbox_path(session_id: str) -> Path:
    """获取任务的 inbox 文件路径"""
    return INBOX_DIR / f"{session_id}.md"


def get_session_dir(session_id: str) -> Path:
    """获取任务的 session 独立目录"""
    return TASKS_DIR / session_id


# 保留 inbox.md 引用（Stage 1 兼容）
from opc.config import INBOX_FILE


# =====================
# 回放保护：命令去重
# =====================

def command_hash(cmd: str) -> str:
    """生成命令的短 hash，用于去重"""
    return hashlib.md5(cmd.encode()).hexdigest()[:12]


def get_executed_commands_file(session_id: str) -> Path:
    """获取 session 的已执行命令记录文件"""
    return get_session_dir(session_id) / "executed_commands.json"


def is_command_executed(session_id: str, cmd: str) -> bool:
    """检查命令是否已执行过"""
    f = get_executed_commands_file(session_id)
    if not f.exists():
        return False
    
    with open(f, "r", encoding="utf-8") as fp:
        executed = json.load(fp)
    
    return command_hash(cmd) in executed


def mark_command_executed(session_id: str, cmd: str) -> None:
    """标记命令已执行"""
    f = get_executed_commands_file(session_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    
    executed = set()
    if f.exists():
        with open(f, "r", encoding="utf-8") as fp:
            executed = set(json.load(fp))
    
    executed.add(command_hash(cmd))
    
    with open(f, "w", encoding="utf-8") as fp:
        json.dump(list(executed), fp, ensure_ascii=False)


# =====================
# 回放保护：文件写入去重
# =====================

def get_written_files_file(session_id: str) -> Path:
    """获取 session 的已写入文件记录文件"""
    return get_session_dir(session_id) / "written_files.json"


def is_file_written(session_id: str, path: str) -> bool:
    """检查文件是否已写入过"""
    f = get_written_files_file(session_id)
    if not f.exists():
        return False
    
    with open(f, "r", encoding="utf-8") as fp:
        written = json.load(fp)
    
    return path in written


def mark_file_written(session_id: str, path: str) -> None:
    """标记文件已写入"""
    f = get_written_files_file(session_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    
    written = set()
    if f.exists():
        with open(f, "r", encoding="utf-8") as fp:
            written = set(json.load(fp))
    
    written.add(path)
    
    with open(f, "w", encoding="utf-8") as fp:
        json.dump(list(written), fp, ensure_ascii=False)
