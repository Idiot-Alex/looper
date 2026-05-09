#!/usr/bin/env python3
"""
OPC Stage 1 Runner 主程序
状态机驱动，循环执行直到终态
"""
import json
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
    is_terminal,
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
)
from opc.logger import (
    log_session, log_prompt, log_raw_output,
    log_parse_error,
)
from opc.prompts import (
    build_manager_prompt, build_engineer_prompt, build_qa_prompt,
)


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
    
    # 读取 inbox
    if not INBOX_FILE.exists():
        print(f"❌ Inbox 文件不存在: {INBOX_FILE}")
        return False, "inbox_error"
    
    inbox_content = INBOX_FILE.read_text(encoding="utf-8")
    
    # 构建 prompt
    prompt = build_manager_prompt(inbox_content)
    
    # 记录 prompt
    log_prompt(session_id, "manager", prompt, 0)
    
    # 调用 LLM
    print("🤖 调用 Manager...")
    try:
        raw_output = call_manager([{"role": "user", "content": prompt}])
    except Exception as e:
        print(f"❌ Manager 调用失败: {e}")
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
    
    # 保存 task.json
    task_file = TASKS_DIR / "task.json"
    task_file.parent.mkdir(parents=True, exist_ok=True)
    with open(task_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
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
    
    # 读取 task.json
    task_file = TASKS_DIR / "task.json"
    if not task_file.exists():
        print("❌ task.json 不存在")
        return False, "task_error"
    
    with open(task_file, "r", encoding="utf-8") as f:
        task_data = json.load(f)
    
    # 读取 QA 报告（重试时需要）
    qa_report = None
    qa_file = TASKS_DIR / "qa_report.json"
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
    
    # 写入文件
    try:
        written_files = write_files(PROJECT_ROOT, data.get("files", []))
        print(f"✅ 写入文件: {', '.join(written_files)}")
    except Exception as e:
        print(f"❌ 文件写入失败: {e}")
        return False, "file_error"
    
    # 保存 engineer_output.json
    engineer_file = TASKS_DIR / "engineer_output.json"
    with open(engineer_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
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
    
    # 读取 task.json
    task_file = TASKS_DIR / "task.json"
    if not task_file.exists():
        print("❌ task.json 不存在")
        return False, "task_error"
    
    with open(task_file, "r", encoding="utf-8") as f:
        task_data = json.load(f)
    
    # 收集 evidence
    evidence = []
    
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
    
    # 执行 test_commands
    test_commands = task_data.get("test_commands", [])
    if test_commands:
        print(f"🧪 执行测试命令: {len(test_commands)} 个")
        try:
            results = execute_test_commands(
                test_commands,
                session_id,
                str(PROJECT_ROOT),
            )
            evidence = results
        except Exception as e:
            print(f"❌ 测试执行失败: {e}")
    
    # 清理后台进程
    cleanup_background()
    
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
    except Exception as e:
        print(f"❌ QA 调用失败: {e}")
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
    
    # 保存 qa_report.json
    qa_file = TASKS_DIR / "qa_report.json"
    with open(qa_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 记录会话
    log_session(session_id, "qa_done", {
        "passed": data.get("passed", False),
        "reason": data.get("reason", ""),
    })
    
    passed = data.get("passed", False)
    print(f"{'✅' if passed else '❌'} QA 判定: {data.get('reason', '')}")
    return True, ""


def handle_qa_result(status: dict) -> None:
    """处理 QA 结果"""
    qa_file = TASKS_DIR / "qa_report.json"
    
    if not qa_file.exists():
        print("❌ qa_report.json 不存在")
        status["stage"] = "failed"
        return
    
    with open(qa_file, "r", encoding="utf-8") as f:
        qa_data = json.load(f)
    
    if qa_data.get("passed", False):
        status["stage"] = "success"
        print("🎉 任务成功完成！")
    else:
        # 增加重试计数
        increment_retry(status)
        retry_count = status.get("retry_count", 0)
        
        if retry_count < MAX_RETRIES:
            status["stage"] = "engineer_retry"
            print(f"🔄 进入重试模式 ({retry_count}/{MAX_RETRIES})")
        else:
            status["stage"] = "failed"
            print(f"❌ 重试次数超限，任务失败")


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


def main():
    """主循环"""
    print("=" * 50)
    print("OPC Stage 1 Runner")
    print("=" * 50)
    
    # 检查配置
    if not check_config():
        sys.exit(1)
    
    # 加载或初始化状态
    if STATUS_FILE.exists():
        status = load_status()
        print(f"📂 恢复会话: {status.get('session_id', 'unknown')}")
        print(f"📍 当前状态: {status.get('stage', 'inbox')}")
    else:
        status = init_status()
        print(f"🆕 新会话: {status.get('session_id')}")
    
    # 初始化重试计数
    if "api_retry_count" not in status:
        status["api_retry_count"] = 0
    if "parse_retry_count" not in status:
        status["parse_retry_count"] = 0
    
    # 主循环
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
                        save_status(status)
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
                        save_status(status)
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
                        save_status(status)
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
            save_status(status)
            
            # 检查终态
            if is_terminal(status.get("stage", "")):
                break
        
        except KeyboardInterrupt:
            print("\n⚠️ 用户中断")
            save_status(status)
            sys.exit(0)
        except Exception as e:
            print(f"❌ 异常: {e}")
            import traceback
            traceback.print_exc()
            save_status(status)
            sys.exit(1)
    
    # 最终状态
    final_stage = status.get("stage", "unknown")
    print(f"\n{'=' * 50}")
    print(f"🏁 最终状态: {final_stage}")
    print(f"{'=' * 50}")
    
    return 0 if final_stage == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
