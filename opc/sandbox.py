"""
OPC 命令执行沙箱
命令安全校验 + 资源限制
"""
import os
import signal
import subprocess
import resource
from pathlib import Path
from typing import List, Optional

from opc.config import FORBIDDEN_COMMANDS, ALLOWED_WORK_DIRS, PROJECT_ROOT


class SandboxError(Exception):
    """沙箱违规异常"""
    pass


def validate_command(cmd: str) -> bool:
    """
    校验命令是否安全
    
    Args:
        cmd: 命令字符串
    
    Returns:
        True: 安全
        False: 违规
    """
    cmd_lower = cmd.lower()
    
    # 检查黑名单
    for forbidden in FORBIDDEN_COMMANDS:
        if forbidden.lower() in cmd_lower:
            raise SandboxError(f"命令包含禁止内容: {forbidden}")
    
    return True


def validate_working_directory(cwd: Optional[str]) -> bool:
    """
    校验工作目录是否在白名单内
    
    Args:
        cwd: 工作目录路径
    
    Returns:
        True: 合法
    """
    if cwd is None:
        return True
    
    cwd_path = Path(cwd).resolve()
    
    for allowed in ALLOWED_WORK_DIRS:
        if str(cwd_path).startswith(str(allowed)):
            return True
    
    raise SandboxError(f"工作目录不在白名单内: {cwd}")


def set_resource_limits():
    """
    设置进程资源限制
    - CPU 时间限制
    - 内存限制
    """
    try:
        # 限制最大 CPU 时间（60秒）
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        
        # 限制最大内存（512MB）
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        
        # 限制最大文件大小（100MB）
        resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024 * 1024, 100 * 1024 * 1024))
        
        # 限制最大进程数
        resource.setrlimit(resource.RLIMIT_NPROC, (50, 50))
        
    except Exception as e:
        # 资源限制设置失败不阻止执行，只记录
        print(f"⚠️ 资源限制设置失败: {e}")


def get_session_start_time() -> float:
    """获取 session 开始时间"""
    return float(os.environ.get("OPC_SESSION_START", "0"))


def check_session_timeout(timeout_seconds: int) -> bool:
    """
    检查是否超过 session 超时
    
    Args:
        timeout_seconds: 超时秒数
    
    Returns:
        True: 已超时
        False: 未超时
    """
    start = get_session_start_time()
    if start == 0:
        return False
    
    import time
    elapsed = time.time() - start
    return elapsed > timeout_seconds
