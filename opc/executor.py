"""
OPC 命令执行模块
后台启动 + 端口探测 + 清理 + 沙箱集成
"""
import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

from opc.config import (
    RUNTIME_DIR, RUNTIME_STDOUT, RUNTIME_STDERR, 
    RUNTIME_EXIT_CODE, RUNTIME_COMMAND, RUNTIME_BACKGROUND_PIDS,
    DEFAULT_COMMAND_TIMEOUT, DEFAULT_STARTUP_TIMEOUT,
    LOGS_COMMAND_RUNS, SESSION_TIMEOUT_SECONDS,
)


class ExecutorError(Exception):
    """执行器异常"""
    pass


from opc.sandbox import validate_command, validate_working_directory, check_session_timeout, set_resource_limits


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
) -> Dict[str, Any]:
    """
    执行命令并收集结果（带沙箱校验）
    
    Args:
        cmd: 命令字符串
        timeout: 超时秒数
        cwd: 工作目录
    
    Returns:
        {"stdout": str, "stderr": str, "exit_code": int, "command": str}
    """
    # 沙箱校验
    validate_command(cmd)
    validate_working_directory(cwd)
    
    # 检查 session 超时
    if check_session_timeout(SESSION_TIMEOUT_SECONDS):
        return {
            "stdout": "",
            "stderr": f"Session 超时（>{SESSION_TIMEOUT_SECONDS}s）",
            "exit_code": -1,
            "command": cmd,
        }
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            preexec_fn=set_resource_limits,
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
    启动后台进程（带沙箱校验）
    
    Args:
        cmd: 命令字符串
        cwd: 工作目录
    
    Returns:
        Popen 对象
    """
    # 沙箱校验
    validate_command(cmd)
    validate_working_directory(cwd)
    
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=set_resource_limits,
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
    cleaned = 0
    skipped = 0
    
    for pid in pids_info.get("pids", []):
        if not isinstance(pid, int):
            skipped += 1
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            skipped += 1
            continue  # 进程已不存在
        except PermissionError:
            skipped += 1
            continue  # 无权限结束该进程，跳过
        except OSError:
            skipped += 1
            continue  # 其他系统错误，跳过

        # 等待进程退出（最多 3 秒）
        deadline = time.time() + 3
        exited = False
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                exited = True
                break
            except OSError:
                exited = True
                break
        if not exited:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass  # 进程可能已退出或无权限，静默处理
        cleaned += 1
    
    # 清空记录
    save_background_pids({"pids": [], "commands": [], "started_at": None})
    if cleaned or skipped:
        print(f"🧹 后台清理完成: cleaned={cleaned}, skipped={skipped}")


def save_runtime_result(result: Dict[str, Any]) -> None:
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
    result: Dict[str, Any],
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


# =====================
# 资源释放验证
# =====================

def verify_resources_released(ports: Optional[List[int]] = None) -> bool:
    """
    验证端口和资源是否已释放（dequeue 前硬校验）
    
    Args:
        ports: 要检查的端口列表，默认检查 BACKGROUND_PIDS 中记录的
    
    Returns:
        True: 资源已释放，可以安全交接
        False: 仍有残留
    """
    import socket
    
    # 如果没指定端口，从 background_pids 推断
    if ports is None:
        pids_info = load_background_pids()
        # 尝试从 pid 检查进程是否还在
        for pid in pids_info.get("pids", []):
            try:
                os.kill(pid, 0)  # 信号 0 只检查进程是否存在
                print(f"⚠️ 进程 {pid} 仍在运行，资源未释放")
                return False
            except OSError:
                continue
    
    # 检查指定端口是否还在监听
    if ports:
        for port in ports:
            try:
                with socket.create_connection(("localhost", port), timeout=1):
                    print(f"⚠️ 端口 {port} 仍被占用，资源未释放")
                    return False
            except OSError:
                continue
    
    return True

