"""
OPC Git 快照模块
每个任务完成后自动创建本地 commit
"""
import subprocess
from pathlib import Path
from typing import Optional

from opc.config import PROJECT_ROOT


def create_snapshot(
    session_id: str,
    summary: str,
    task_goal: Optional[str] = None,
) -> bool:
    """
    创建本地 Git 快照
    
    Args:
        session_id: 会话 ID
        summary: 变更摘要
        task_goal: 任务目标（可选）
    
    Returns:
        True: 成功
        False: 失败
    """
    try:
        # 检查是否在 git 仓库中
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip() != "true":
            print("⚠️ 不是 Git 仓库，跳过快照")
            return False
        
        # 添加变更（排除 runtime 文件）
        # 只添加代码文件，不添加日志和状态文件
        subprocess.run(
            ["git", "add", "opc/*.py", "opc/**/*.md"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            shell=True,
        )
        
        # 检查是否有变更
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=PROJECT_ROOT,
        )
        if result.returncode != 0:
            # 有变更，创建 commit
            msg = f"[{session_id}] {summary}"
            if task_goal:
                msg = f"[{session_id}] {summary}\n\nGoal: {task_goal}"
            
            subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
            )
            
            # 获取 commit hash
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )
            commit_hash = result.stdout.strip()
            
            print(f"📸 Git 快照创建: {commit_hash}")
            return True
        else:
            print("📸 无变更，跳过快照")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Git 快照失败: {e}")
        return False


def get_last_commit_hash() -> Optional[str]:
    """获取最后一次 commit 的 hash"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def rollback_to_snapshot(session_id: str) -> bool:
    """
    回滚到指定 session 的快照
    
    注意：这会丢弃当前所有未提交的变更！
    
    Args:
        session_id: 会话 ID
    
    Returns:
        True: 成功
    """
    try:
        # 查找对应的 commit
        result = subprocess.run(
            ["git", "log", "--all", "--oneline", "--grep", f"[{session_id}]"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        
        if not result.stdout.strip():
            print(f"❌ 未找到 session {session_id} 的快照")
            return False
        
        # 获取第一个匹配的 commit hash
        commit_hash = result.stdout.strip().split()[0]
        
        # 确认操作
        print(f"⚠️ 将回滚到: {commit_hash}")
        
        subprocess.run(
            ["git", "reset", "--hard", commit_hash],
            cwd=PROJECT_ROOT,
            check=True,
        )
        
        print(f"✅ 已回滚到 {commit_hash}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ 回滚失败: {e}")
        return False
