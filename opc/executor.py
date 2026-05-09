"""
OPC 命令执行模块
后台启动 + 端口探测 + 清理
"""
import json
import socket
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Dict

from opc.config import (
    RUNTIME_DIR, RUNTIME_STDOUT, RUNTIME_STDERR, 
    RUNTIME_EXIT_CODE, RUNTIME_COMMAND, RUNTIME_BACKGROUND_PIDS,
    DEFAULT_COMMAND_TIMEOUT, DEFAULT_STARTUP_TIMEOUT,
    LOGS_COMMAND_RUNS,
)


class ExecutorError(Exception):
    """执行器异常"""
    pass


def wait_for_port(port: int, timeout: int = DEFAULT_STARTUP_TIMEOUT) -> bool:
    """
    端口探测等待
    
    优先使用端口探测，比固定 sleep 更可靠
    
    Args:
        port: 端口号
        timeout: 超时秒数
    
    Returns:
        True: 端口可用
        False: 超时
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def run_command(
    cmd: str, 
    timeout: int = DEFAULT_COMMAND_TIMEOUT,
    cwd: Optional[str] = None
) -> Dict[str, any]:
    """
    执行命令并收集结果
    
    Args:
        cmd: 命令字符串
        timeout: 超时秒数
        cwd: 工作目录
    
    Returns:
        {"stdout": str, "stderr": str, "exit_code": int, "command": str}
    """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "command": cmd,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"命令超时（>{timeout}s）",
            "exit_code": -1,
            "command": cmd,
        }


def start_background_process(cmd: str, cwd: Optional[str] = None) -> subprocess.Popen:
    """
    启动后台进程
    
    Args:
        cmd: 命令字符串
        cwd: 工作目录
    
    Returns:
        Popen 对象
    """
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
    )
    return proc


def save_background_pids(pids_info: dict) -> None:
    """保存后台进程信息"""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with open(RUNTIME_BACKGROUND_PIDS, "w", encoding="utf-8") as f:
        json.dump(pids_info, f, ensure_ascii=False, indent=2)


def load_background_pids() -> dict:
    """加载后台进程信息"""
    if not RUNTIME_BACKGROUND_PIDS.exists():
        return {"pids": [], "commands": [], "started_at": None}
    
    with open(RUNTIME_BACKGROUND_PIDS, "r", encoding="utf-8") as f:
        return json.load(f)


def cleanup_background() -> None:
    """清理后台进程"""
    pids_info = load_background_pids()
    
    for pid in pids_info.get("pids", []):
        try:
            proc = subprocess.Process(pid)
            proc.terminate()
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass  # 进程可能已崩溃，静默处理
        except Exception:
            pass  # 进程不存在，静默处理
    
    # 清空记录
    save_background_pids({"pids": [], "commands": [], "started_at": None})


def save_runtime_result(result: Dict[str, any]) -> None:
    """保存执行结果到 runtime 目录"""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(RUNTIME_STDOUT, "w", encoding="utf-8") as f:
        f.write(result.get("stdout", ""))
    
    with open(RUNTIME_STDERR, "w", encoding="utf-8") as f:
        f.write(result.get("stderr", ""))
    
    with open(RUNTIME_EXIT_CODE, "w", encoding="utf-8") as f:
        f.write(str(result.get("exit_code", -1)))
    
    with open(RUNTIME_COMMAND, "w", encoding="utf-8") as f:
        f.write(result.get("command", ""))


def log_command_run(
    session_id: str, 
    stage: str, 
    result: Dict[str, any],
    index: int = 0
) -> None:
    """记录命令执行到日志"""
    LOGS_COMMAND_RUNS.mkdir(parents=True, exist_ok=True)
    
    # 文件名格式: session_id-stage-index.log
    filename = f"{session_id}-{stage}-{index}.log"
    filepath = LOGS_COMMAND_RUNS / filename
    
    content = f"""# Command Execution Log
# Session: {session_id}
# Stage: {stage}
# Timestamp: {time.strftime("%Y-%m-%d %H:%M:%S")}

## Command
{result.get('command', '')}

## Exit Code
{result.get('exit_code', -1)}

## Stdout
{result.get('stdout', '')}

## Stderr
{result.get('stderr', '')}
"""
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def execute_background_commands(
    commands: List[str],
    startup_wait: int = DEFAULT_STARTUP_TIMEOUT,
    session_id: str = "default",
    cwd: Optional[str] = None,
    health_check_port: Optional[int] = None,
) -> List[subprocess.Popen]:
    """
    执行后台命令列表
    
    Args:
        commands: 命令列表
        startup_wait: 最大等待秒数
        session_id: 会话 ID
        cwd: 工作目录
        health_check_port: 健康检查端口（优先用端口探测）
    
    Returns:
        Popen 对象列表
    """
    procs = []
    pids = []
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    for i, cmd in enumerate(commands):
        # 去掉末尾 &，subprocess.Popen 本身就是后台运行
        cmd = cmd.rstrip().rstrip("&").strip()
        proc = start_background_process(cmd, cwd)
        procs.append(proc)
        pids.append(proc.pid)
        
        # 记录日志
        log_command_run(
            session_id, 
            f"bg-{i}",
            {"command": cmd, "stdout": "", "stderr": "", "exit_code": 0},
            0
        )
    
    # 保存进程信息
    save_background_pids({
        "pids": pids,
        "commands": commands,
        "started_at": started_at,
    })
    
    # 等待启动：端口探测优先，超时兜底
    if health_check_port:
        print(f"⏳ 端口探测 {health_check_port}...")
        ok = wait_for_port(health_check_port, timeout=startup_wait)
        if ok:
            print(f"✅ 端口 {health_check_port} 已就绪")
            time.sleep(1.0)  # 端口通了不代表 HTTP 就绪，多等1秒
        else:
            print(f"⚠️ 端口 {health_check_port} 探测超时 ({startup_wait}s)，继续执行测试")
    else:
        time.sleep(startup_wait)
    
    return procs


def execute_test_commands(
    commands: List[str],
    session_id: str = "default",
    cwd: Optional[str] = None
) -> List[Dict[str, any]]:
    """
    执行测试命令列表
    
    Args:
        commands: 命令列表
        session_id: 会话 ID
        cwd: 工作目录
    
    Returns:
        结果列表
    """
    results = []
    
    for i, cmd in enumerate(commands):
        result = run_command(cmd, cwd=cwd)
        results.append(result)
        
        # 如果是最后一条命令，保存到 runtime
        if i == len(commands) - 1:
            save_runtime_result(result)
        
        # 记录到日志
        log_command_run(session_id, f"test-{i}", result, i)
    
    return results
