#!/usr/bin/env python3
"""
OPC Runner 主程序
状态机驱动，支持 Stage 2 队列 + 断点恢复 + 回放保护
"""
import json
import os
import sys
from pathlib import Path

from opc.config import (
    PROJECT_ROOT, TASKS_DIR, RUNTIME_DIR,
    STATUS_FILE, INBOX_FILE, MAX_RETRIES, MAX_API_RETRIES,
    TERMINAL_STAGES,
)
from opc.state import (
    load_status, save_status, init_status,
    increment_retry, increment_parse_retry,
    is_terminal, mark_stage_completed, is_stage_completed,
)
from opc.queue import (
    migrate_inbox_md, scan_inbox, get_next_task, mark_done,
    get_task_inbox_path, get_session_dir,
    is_command_executed, mark_command_executed,
    is_file_written, mark_file_written,
)
from opc.llm import call_manager, call_engineer, call_qa
from opc.parser import (
    parse_json_safe, parse_json_strict,
    validate_manager_output, validate_engineer_output,
    validate_qa_output,
)
from opc.writer import write_files
from opc.executor import (
    execute_background_commands, execute_test_commands,
    cleanup_background, load_background_pids,
    verify_resources_released,
)
from opc.logger import (
    log_session, log_prompt, log_raw_output,
    log_parse_error, log_event, log_llm_call,
    log_file_write, log_command_run, log_qa_decision,
    log_session_timeout,
)
from opc.prompts import (
    build_manager_prompt, build_engineer_prompt, build_qa_prompt,
    infer_task_type,
)
from opc.config import SESSION_TIMEOUT_SECONDS
from opc.git_snapshot import create_snapshot


def run_manager(status: dict) -> tuple[bool, str]:
    """
    执行 Manager 阶段
    
    Returns:
        (True, ""): 成功
        (False, "parse_error"): JSON 解析失败
        (False, "api_error"): API 调用失败
        (False, "validation_error"): 格式验证失败
    """
    session_id = status.get("session_id", "unknown")
    
    # 读取 inbox（Stage 2: 按 session_id 找，Stage 1 兼容: 用 INBOX_FILE）
    inbox_path = get_task_inbox_path(session_id)
    if not inbox_path.exists():
        inbox_path = INBOX_FILE  # Stage 1 兼容
    
    if not inbox_path.exists():
        print(f"❌ Inbox 文件不存在: {inbox_path}")
        return False, "inbox_error"
    
    inbox_content = inbox_path.read_text(encoding="utf-8")
    
    # 构建 prompt
    prompt = build_manager_prompt(inbox_content)
    
    # 记录 prompt
    log_prompt(session_id, "manager", prompt, 0)
    
    # 调用 LLM
    print("🤖 调用 Manager...")
    try:
        raw_output = call_manager([{"role": "user", "content": prompt}])
        log_llm_call(session_id, "manager", "deepseek-v4-flash", success=True, stage="manager")
    except Exception as e:
        print(f"❌ Manager 调用失败: {e}")
        log_llm_call(session_id, "manager", "deepseek-v4-flash", success=False, error=str(e), stage="manager")
        return False, "api_error"
    
    # 记录原始输出
    log_raw_output(session_id, "manager", raw_output, 0)
    
    # 解析 JSON
    data = parse_json_safe(raw_output)
    if data is None:
        print("❌ Manager 输出 JSON 解析失败")
        log_parse_error(session_id, "manager", raw_output, 0)
        status["stage"] = "parse_error"
        return False, "parse_error"
    
    # 验证格式
    if not validate_manager_output(data):
        print("❌ Manager 输出格式验证失败")
        status["stage"] = "parse_error"
        return False, "validation_error"
    
    # 保存 task.json（Stage 2: session 独立目录）
    session_dir = get_session_dir(session_id)
    task_file = session_dir / "task.json"
    task_file.parent.mkdir(parents=True, exist_ok=True)
    with open(task_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 标记 manager 阶段已完成
    mark_stage_completed(status, "manager")
    
    # 记录会话
    log_session(session_id, "manager_done", {
        "goal": data.get("goal", ""),
    })
    
    print(f"✅ Manager 完成: {data.get('goal', '')}")
    return True, ""


def run_engineer(status: dict, is_retry: bool = False) -> tuple[bool, str]:
    """
    执行 Engineer 阶段
    
    Args:
        status: 当前状态
        is_retry: 是否是重试模式
    
    Returns:
        (True, ""): 成功
        (False, "api_error"): API 调用失败
        (False, "parse_error"): JSON 解析失败
        (False, "validation_error"): 格式验证失败
        (False, "file_error"): 文件写入失败
    """
    session_id = status.get("session_id", "unknown")
    retry_count = status.get("retry_count", 0)
    
    # 读取 task.json（Stage 2: session 独立目录）
    session_dir = get_session_dir(session_id)
    task_file = session_dir / "task.json"
    if not task_file.exists():
        print("❌ task.json 不存在")
        return False, "task_error"
    
    with open(task_file, "r", encoding="utf-8") as f:
        task_data = json.load(f)
    
    # 读取 QA 报告（重试时需要）
    qa_report = None
    qa_file = session_dir / "qa_report.json"
    if is_retry and qa_file.exists():
        with open(qa_file, "r", encoding="utf-8") as f:
            qa_report = json.load(f)
    
    # 构建 prompt
    prompt = build_engineer_prompt(task_data, qa_report)
    
    # 记录 prompt
    log_prompt(session_id, "engineer", prompt, retry_count)
    
    # 调用 LLM
    role_name = "engineer_retry" if is_retry else "engineer"
    print(f"🤖 调用 Engineer {'(重试模式)' if is_retry else ''}...")
    try:
        raw_output = call_engineer([{"role": "user", "content": prompt}])
    except Exception as e:
        print(f"❌ Engineer 调用失败: {e}")
        return False, "api_error"
    
    # 记录原始输出
    log_raw_output(session_id, role_name, raw_output, retry_count)
    
    # 解析 JSON
    data = parse_json_safe(raw_output)
    if data is None:
        print("❌ Engineer 输出 JSON 解析失败")
        log_parse_error(session_id, role_name, raw_output, retry_count)
        status["stage"] = "parse_error"
        return False, "parse_error"
    
    # 验证格式
    if not validate_engineer_output(data):
        print("❌ Engineer 输出格式验证失败")
        status["stage"] = "parse_error"
        return False, "validation_error"
    
    # 写入文件（回放保护：跳过已写入文件）
    try:
        files_to_write = []
        for f in data.get("files", []):
            path = f.get("path", "")
            if is_file_written(session_id, path):
                print(f"⏭️ 跳过已写入文件: {path}")
            else:
                files_to_write.append(f)
        
        written_files = write_files(PROJECT_ROOT, files_to_write) if files_to_write else []
        
        # 标记所有文件为已写入（包括之前跳过的）
        for f in data.get("files", []):
            path = f.get("path", "")
            mark_file_written(session_id, path)
            log_file_write(session_id, path, len(f.get("content", "")), skipped=(path not in [ff.get("path") for ff in files_to_write]))
        
        if written_files:
            print(f"✅ 写入文件: {', '.join(written_files)}")
    except Exception as e:
        print(f"❌ 文件写入失败: {e}")
        return False, "file_error"
    
    # 保存 engineer_output.json（Stage 2: session 独立目录）
    engineer_file = session_dir / "engineer_output.json"
    with open(engineer_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 标记 engineer 阶段已完成
    mark_stage_completed(status, "engineer")
    
    # 记录会话
    log_session(session_id, "engineer_done", {
        "files": written_files,
        "summary": data.get("summary", ""),
    })
    
    print(f"✅ Engineer 完成")
    return True, ""


def run_qa(status: dict) -> tuple[bool, str]:
    """
    执行 QA 阶段
    
    Returns:
        (True, ""): 成功
        (False, "api_error"): API 调用失败
        (False, "parse_error"): JSON 解析失败
        (False, "validation_error"): 格式验证失败
    """
    session_id = status.get("session_id", "unknown")
    
    # 读取 task.json（Stage 2: session 独立目录）
    session_dir = get_session_dir(session_id)
    task_file = session_dir / "task.json"
    if not task_file.exists():
        print("❌ task.json 不存在")
        return False, "task_error"
    
    with open(task_file, "r", encoding="utf-8") as f:
        task_data = json.load(f)
    
    # 收集 evidence
    evidence = []
    
    # Session 超时检测
    import time as time_module
    session_start = float(os.environ.get("OPC_SESSION_START", "0"))
    elapsed = time_module.time() - session_start if session_start > 0 else 0
    
    if elapsed > SESSION_TIMEOUT_SECONDS:
        print(f"⏰ Session 超时 ({elapsed:.0f}s > {SESSION_TIMEOUT_SECONDS}s)")
        log_session_timeout(session_id, SESSION_TIMEOUT_SECONDS, int(elapsed), "engineer_done")
        cleanup_background()
        status["stage"] = "failed"
        return False, "timeout"
    
    # 先执行 background_commands
    background_commands = task_data.get("background_commands", [])
    health_port = task_data.get("health_check_port")
    startup_wait = task_data.get("startup_wait_seconds", 10)
    
    if background_commands:
        print(f"🚀 启动后台进程: {len(background_commands)} 个")
        if health_port:
            print(f"   健康检查端口: {health_port}")
        try:
            execute_background_commands(
                background_commands,
                startup_wait,
                session_id,
                str(PROJECT_ROOT),
                health_check_port=health_port,
            )
        except Exception as e:
            print(f"⚠️ 后台启动失败: {e}")
    
    # 执行 test_commands（回放保护：跳过已执行命令）
    test_commands = task_data.get("test_commands", [])
    if test_commands:
        print(f"🧪 执行测试命令: {len(test_commands)} 个")
        try:
            results = []
            for cmd in test_commands:
                if is_command_executed(session_id, cmd):
                    print(f"⏭️ 跳过已执行命令: {cmd}")
                    results.append({
                        "command": cmd,
                        "stdout": "(skipped - already executed)",
                        "stderr": "",
                        "exit_code": 0,
                    })
                else:
                    result = execute_test_commands([cmd], session_id, str(PROJECT_ROOT))
                    results.extend(result)
                    mark_command_executed(session_id, cmd)
            evidence = results
        except Exception as e:
            print(f"❌ 测试执行失败: {e}")
    
    # 注意：不在这里清理后台进程，等任务完全结束再清理
    # cleanup_background() 在 run_single_task 返回后由主循环统一处理
    
    if not evidence:
        print("⚠️ 没有执行结果")
        evidence = [{
            "command": "",
            "stdout": "",
            "stderr": "无执行结果",
            "exit_code": -1,
        }]
    
    # 构建 QA prompt
    prompt = build_qa_prompt(task_data, evidence)
    
    # 记录 prompt
    log_prompt(session_id, "qa", prompt, 0)
    
    # 调用 QA
    print("🤖 调用 QA...")
    try:
        raw_output = call_qa([{"role": "user", "content": prompt}])
        log_llm_call(session_id, "qa", "MiniMax-M2.5", success=True, stage="qa")
    except Exception as e:
        print(f"❌ QA 调用失败: {e}")
        log_llm_call(session_id, "qa", "MiniMax-M2.5", success=False, error=str(e), stage="qa")
        return False, "api_error"
    
    # 记录原始输出
    log_raw_output(session_id, "qa", raw_output, 0)
    
    # 解析 JSON
    data = parse_json_safe(raw_output)
    if data is None:
        print("❌ QA 输出 JSON 解析失败")
        log_parse_error(session_id, "qa", raw_output, 0)
        status["stage"] = "parse_error"
        return False, "parse_error"
    
    # 验证格式
    if not validate_qa_output(data):
        print("❌ QA 输出格式验证失败")
        status["stage"] = "parse_error"
        return False, "validation_error"
    
    # 保存 qa_report.json（Stage 2: session 独立目录）
    qa_file = session_dir / "qa_report.json"
    with open(qa_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 标记 qa 阶段已完成
    mark_stage_completed(status, "qa")
    
    # 记录会话
    log_session(session_id, "qa_done", {
        "passed": data.get("passed", False),
        "reason": data.get("reason", ""),
    })
    
    passed = data.get("passed", False)
    print(f"{'✅' if passed else '❌'} QA 判定: {data.get('reason', '')}")
    
    # 记录 QA 判定到 JSONL
    log_qa_decision(
        session_id,
        passed,
        data.get("reason", ""),
        data.get("failure_type"),
    )
    
    return True, ""


def handle_qa_result(status: dict) -> None:
    """处理 QA 结果"""
    session_id = status.get("session_id", "unknown")
    session_dir = get_session_dir(session_id)
    qa_file = session_dir / "qa_report.json"
    task_file = session_dir / "task.json"
    
    if not qa_file.exists():
        print("❌ qa_report.json 不存在")
        status["stage"] = "failed"
        return
    
    with open(qa_file, "r", encoding="utf-8") as f:
        qa_data = json.load(f)
    
    if qa_data.get("passed", False):
        status["stage"] = "success"
        print("🎉 任务成功完成！")
        
        # 创建成功快照
        task_goal = ""
        if task_file.exists():
            with open(task_file, "r") as f:
                task_data = json.load(f)
                task_goal = task_data.get("goal", "")
        
        create_snapshot(
            session_id,
            f"Task completed: {task_goal}",
            task_goal,
        )
    else:
        # 增加重试计数
        increment_retry(status)
        retry_count = status.get("retry_count", 0)
        
        if retry_count < MAX_RETRIES:
            status["stage"] = "engineer_retry"
            print(f"🔄 进入重试模式 ({retry_count}/{MAX_RETRIES})")
            
            # 记录 failure_type 用于选择修复 prompt
            failure_type = qa_data.get("failure_type", "unknown")
            print(f"📋 失败类型: {failure_type}")
        else:
            status["stage"] = "failed"
            print(f"❌ 重试次数超限，任务失败")
            
            # 创建失败快照（方便回滚）
            task_goal = ""
            if task_file.exists():
                with open(task_file, "r") as f:
                    task_data = json.load(f)
                    task_goal = task_data.get("goal", "")
            
            create_snapshot(
                session_id,
                f"Task failed after {MAX_RETRIES} retries: {task_goal}",
                task_goal,
            )


def check_config():
    """检查必需配置"""
    from opc.config import DEEPSEEK_API_KEY, MINIMAX_API_KEY
    
    errors = []
    
    if not DEEPSEEK_API_KEY:
        errors.append("❌ DEEPSEEK_API_KEY 未设置")
        errors.append("   请在 .env 文件或环境变量中配置")
    
    if not MINIMAX_API_KEY:
        errors.append("❌ MINIMAX_API_KEY 未设置")
        errors.append("   请在 .env 文件或环境变量中配置")
    
    if errors:
        print("=" * 50)
        print("⚠️  配置检查失败")
        print("=" * 50)
        for err in errors:
            print(err)
        print()
        print("获取 Key 地址:")
        print("  DeepSeek: https://platform.deepseek.com/")
        print("  MiniMax:  https://www.minimaxi.com/")
        print()
        print("配置方式:")
        print("  1. 编辑 .env 文件填入 key")
        print("  2. 或设置环境变量 export DEEPSEEK_API_KEY=xxx")
        return False
    
    return True


def run_single_task(session_id: str) -> str:
    """
    运行单个任务
    
    Returns:
        最终状态 (success/failed/parse_error)
    """
    import os
    import time as time_module
    
    # 设置 session 开始时间（用于超时检测）
    os.environ["OPC_SESSION_START"] = str(time_module.time())
    
    status = load_status(session_id)
    print(f"📂 恢复会话: {session_id}")
    print(f"📍 当前状态: {status.get('stage', 'inbox')}")
    print(f"✅ 已完成阶段: {status.get('completed_stages', [])}")
    
    # 初始化重试计数
    if "api_retry_count" not in status:
        status["api_retry_count"] = 0
    if "parse_retry_count" not in status:
        status["parse_retry_count"] = 0
    
    # 初始化重试计数
    if "api_retry_count" not in status:
        status["api_retry_count"] = 0
    if "parse_retry_count" not in status:
        status["parse_retry_count"] = 0
    
    # 主循环（支持 completed_stages 断点恢复）
    while not is_terminal(status.get("stage", "")):
        stage = status.get("stage", "")
        
        print(f"\n{'=' * 30}")
        print(f"Stage: {stage}")
        print(f"{'=' * 30}")
        
        try:
            if stage == "inbox":
                success, error_type = run_manager(status)
                status["parse_retry_count"] = 0  # 新角色阶段，重置 parse 计数
                if success:
                    status["stage"] = "manager_done"
                    status["api_retry_count"] = 0
                elif error_type == "parse_error":
                    # parse 失败 → 重试当前角色 1 次
                    status["parse_retry_count"] += 1
                    if status["parse_retry_count"] > 1:
                        print(f"❌ Manager JSON 解析连续失败 2 次，进入 parse_error")
                        status["stage"] = "parse_error"
                    else:
                        print(f"⚠️ Manager JSON 解析失败，重试 (1/1)")
                else:
                    status["api_retry_count"] += 1
                    if status["api_retry_count"] >= MAX_API_RETRIES:
                        print(f"❌ API 调用失败次数过多 ({status['api_retry_count']}/{MAX_API_RETRIES})，退出")
                        print(f"   错误类型: {error_type}")
                        save_status(status, session_id)
                        sys.exit(1)
                    print(f"⚠️ API 调用失败，重试 ({status['api_retry_count']}/{MAX_API_RETRIES})")
            
            elif stage in ("manager_done", "engineer_retry"):
                is_retry = (stage == "engineer_retry")
                # engineer_retry 进入新角色调用，重置 parse 计数 (修正4)
                if is_retry:
                    status["parse_retry_count"] = 0
                success, error_type = run_engineer(status, is_retry)
                if success:
                    status["stage"] = "engineer_done"
                    status["api_retry_count"] = 0
                    status["parse_retry_count"] = 0
                elif error_type == "parse_error":
                    status["parse_retry_count"] += 1
                    if status["parse_retry_count"] > 1:
                        print(f"❌ Engineer JSON 解析连续失败 2 次，进入 parse_error")
                        status["stage"] = "parse_error"
                    else:
                        print(f"⚠️ Engineer JSON 解析失败，重试 (1/1)")
                else:
                    status["api_retry_count"] += 1
                    if status["api_retry_count"] >= MAX_API_RETRIES:
                        print(f"❌ API 调用失败次数过多 ({status['api_retry_count']}/{MAX_API_RETRIES})，退出")
                        print(f"   错误类型: {error_type}")
                        save_status(status, session_id)
                        sys.exit(1)
                    print(f"⚠️ API 调用失败，重试 ({status['api_retry_count']}/{MAX_API_RETRIES})")
            
            elif stage == "engineer_done":
                status["parse_retry_count"] = 0  # 新角色阶段
                success, error_type = run_qa(status)
                if success:
                    status["stage"] = "qa_done"
                    status["api_retry_count"] = 0
                elif error_type == "parse_error":
                    status["parse_retry_count"] += 1
                    if status["parse_retry_count"] > 1:
                        print(f"❌ QA JSON 解析连续失败 2 次，进入 parse_error")
                        status["stage"] = "parse_error"
                    else:
                        print(f"⚠️ QA JSON 解析失败，重试 (1/1)")
                else:
                    status["api_retry_count"] += 1
                    if status["api_retry_count"] >= MAX_API_RETRIES:
                        print(f"❌ API 调用失败次数过多 ({status['api_retry_count']}/{MAX_API_RETRIES})，退出")
                        print(f"   错误类型: {error_type}")
                        save_status(status, session_id)
                        sys.exit(1)
                    print(f"⚠️ API 调用失败，重试 ({status['api_retry_count']}/{MAX_API_RETRIES})")
            
            elif stage == "qa_done":
                handle_qa_result(status)
                status["api_retry_count"] = 0
                status["parse_retry_count"] = 0
            
            else:
                print(f"❌ 未知状态: {stage}")
                break
            
            # 保存状态
            save_status(status, session_id)
            
            # 检查终态
            if is_terminal(status.get("stage", "")):
                save_status(status, session_id)  # 显式保存终态
                break
        
        except KeyboardInterrupt:
            print("\n⚠️ 用户中断")
            save_status(status, session_id)
            sys.exit(0)
        except Exception as e:
            print(f"❌ 异常: {e}")
            import traceback
            traceback.print_exc()
            save_status(status, session_id)
            sys.exit(1)
    
    # 最终状态
    final_stage = status.get("stage", "unknown")
    print(f"\n{'=' * 50}")
    print(f"🏁 最终状态: {final_stage}")
    print(f"{'=' * 50}")
    
    return 0 if final_stage == "success" else 1


def main():
    """队列主循环"""
    print("=" * 50)
    print("OPC Runner")
    print("=" * 50)
    
    # 检查配置
    if not check_config():
        sys.exit(1)
    
    # 迁移 Stage 1 inbox.md 到 inbox/ 目录
    migrate_inbox_md()
    
    # 扫描队列
    tasks = scan_inbox()
    if not tasks:
        print("📭 inbox/ 为空，无待处理任务")
        sys.exit(0)
    
    print(f"📋 发现 {len(tasks)} 个待处理任务（FIFO 顺序）")
    for i, task in enumerate(tasks, 1):
        print(f"  {i}. {task['session_id']}")
    
    print()
    
    # 逐个处理任务
    results = {}
    for task in tasks:
        session_id = task["session_id"]
        print(f"\n{'#' * 50}")
        print(f"# 任务 {len(results) + 1}/{len(tasks)}: {session_id}")
        print(f"{'#' * 50}")
        
        # 运行单个任务
        exit_code = run_single_task(session_id)
        final_status = load_status(session_id).get("stage", "unknown")
        results[session_id] = final_status
        
        # 任务完成后移动 inbox 文件到 done/
        mark_done(session_id)
        
        # 任务完成后清理后台进程
        print("🧹 清理后台进程...")
        cleanup_background()
        
        # 硬校验资源已释放（如果有健康检查端口，确认已释放）
        ports_to_check = []
        task_file_path = get_session_dir(session_id) / "task.json"
        if task_file_path.exists():
            with open(task_file_path) as f:
                td = json.load(f)
                if td.get("health_check_port"):
                    ports_to_check.append(td["health_check_port"])
        
        if not verify_resources_released(ports_to_check if ports_to_check else None):
            print("⚠️ 资源释放验证失败，但继续处理下一个任务")
        
        print(f"\n✅ 任务 {session_id} 完成: {final_status}")
    
    # 汇总结果
    print(f"\n{'=' * 50}")
    print("📊 队列执行汇总")
    print(f"{'=' * 50}")
    success_count = sum(1 for v in results.values() if v == "success")
    failed_count = sum(1 for v in results.values() if v == "failed")
    error_count = sum(1 for v in results.values() if v == "parse_error")
    
    print(f"  成功: {success_count}")
    print(f"  失败: {failed_count}")
    print(f"  协议错误: {error_count}")
    print(f"  总计: {len(results)}")
    
    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
