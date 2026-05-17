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
    MAX_MANAGER_REPLANS, TERMINAL_STAGES,
    DEEPSEEK_MODEL,
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
from opc.llm import call_manager, call_engineer, call_qa, call_qa_formatter
from opc.parser import (
    parse_json_safe, parse_json_strict,
    validate_manager_output, validate_engineer_output,
    validate_qa_output,
)
from opc.writer import write_files
from opc.executor import (
    execute_background_commands, execute_test_commands,
    cleanup_background, load_background_pids,
    verify_resources_released, cleanup_all_orphans,
)
from opc.logger import (
    log_session, log_prompt, log_raw_output,
    log_parse_error, log_event, log_llm_call,
    log_file_write, log_command_run, log_qa_decision,
    log_session_timeout,
)
from opc.prompts import (
    build_manager_prompt, build_engineer_prompt,
    build_qa_prompt, build_qa_analysis_prompt, build_qa_format_prompt,
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


def _read_project_files(max_files: int = 5) -> dict:
    """读取项目中修改过的文件列表和内容，供 Manager 大循环参考"""
    files = {}
    for entry in sorted(Path(".").iterdir())[:max_files]:
        if entry.is_file() and entry.suffix in (".py", ".html", ".js", ".css", ".json", ".md"):
            try:
                files[entry.name] = entry.read_text(encoding="utf-8")[:2000]
            except Exception:
                pass
    return files


def run_manager_replan(status: dict) -> tuple[bool, str]:
    """
    执行 Manager 大循环重新规划

    小循环（3次 retry）全部失败后，Manager 读取失败历史重新规划。
    完全覆盖 task.json，换思路，不重复上一次的方案。
    """
    from opc.prompts import build_manager_replan_prompt

    session_id = status.get("session_id", "unknown")
    session_dir = get_session_dir(session_id)
    history_file = session_dir / "retry_history.json"

    # 读取失败历史
    retry_history = []
    if history_file.exists():
        with open(history_file, encoding="utf-8") as f:
            retry_history = json.load(f)

    # 读取原始 goal
    task_file = session_dir / "task.json"
    original_goal = ""
    if task_file.exists():
        with open(task_file, encoding="utf-8") as f:
            old_task = json.load(f)
            original_goal = old_task.get("goal", "")

    # 读取项目文件（供 Manager 参考）
    project_files = _read_project_files()

    # 构建 prompt
    prompt = build_manager_replan_prompt(
        original_goal=original_goal,
        retry_history=retry_history,
        project_files=project_files,
    )

    log_prompt(session_id, "manager_replan", prompt, 0)

    print("🤖 调用 Manager (大循环重规划)...")
    try:
        raw_output = call_manager([{"role": "user", "content": prompt}])
        log_llm_call(session_id, "manager_replan", "deepseek-v4-flash",
                     success=True, stage="manager_replan")
    except Exception as e:
        print(f"❌ Manager 大循环调用失败: {e}")
        log_llm_call(session_id, "manager_replan", "deepseek-v4-flash",
                     success=False, error=str(e), stage="manager_replan")
        return False, "api_error"

    log_raw_output(session_id, "manager_replan", raw_output, 0)

    # 解析 JSON
    data = parse_json_safe(raw_output)
    if data is None:
        print("❌ Manager 大循环输出 JSON 解析失败")
        log_parse_error(session_id, "manager_replan", raw_output, 0)
        status["stage"] = "parse_error"
        return False, "parse_error"

    # 验证格式
    if not validate_manager_output(data):
        print("❌ Manager 大循环输出格式验证失败")
        status["stage"] = "parse_error"
        return False, "validation_error"

    # 去重检测：steps 完全一样 = 没换思路
    if task_file.exists():
        old_steps = json.load(open(task_file, encoding="utf-8")).get("steps", [])
        new_steps = data.get("steps", [])
        if old_steps == new_steps and old_steps:
            print("⚠️ Manager 未换思路，跳过本轮 replan")
            status["stage"] = "failed"
            return False, "duplicate_plan"

    # 完全覆盖 task.json
    with open(task_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # replan 计数 +1，重置小循环 retry_count
    status["replan_count"] = status.get("replan_count", 0) + 1
    status["retry_count"] = 0

    # 清空 written_files 和 executed_commands（让 Engineer 重跑）
    for f in ["written_files.json", "executed_commands.json"]:
        try:
            (session_dir / f).unlink()
        except FileNotFoundError:
            pass

    # 保留 retry_history 供下一轮大循环用
    mark_stage_completed(status, "manager")
    log_session(session_id, "manager_replan_done", {
        "replan_count": status["replan_count"],
        "goal": data.get("goal", ""),
    })

    print(f"✅ Manager 大循环完成 (第 {status['replan_count']} 次)：{data.get('goal', '')}")
    print(f"   新 steps: {data.get('steps', [])[:2]}...")
    return True, ""


def _install_dependencies(task_data: dict) -> None:
    """按 language + dependencies 安装第三方依赖，失败不阻塞"""
    from opc.config import PACKAGE_MANAGER_MAP
    import subprocess, shlex

    language = task_data.get("language", "python")
    deps = task_data.get("dependencies", [])
    if not deps:
        return

    cmd_template = PACKAGE_MANAGER_MAP.get(language)
    if not cmd_template:
        print(f"⚠️  未知语言 '{language}'，跳过依赖安装")
        return

    print(f"📦 安装 {language} 依赖: {', '.join(deps)}")
    for dep in deps:
        # 先检查是否已安装（避免 uv 锁冲突）
        try:
            check = subprocess.run(
                shlex.split(f"uv pip show {dep.split('==')[0]}"),
                capture_output=True, text=True, timeout=15,
            )
            if check.returncode == 0:
                print(f"   ✅ {dep} 已安装，跳过")
                continue
        except Exception:
            pass

        cmd = cmd_template.format(pkg=dep)
        print(f"   运行: {cmd}")
        try:
            result = subprocess.run(
                shlex.split(cmd),
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                print(f"   ✅ {dep} 安装成功")
            else:
                print(f"   ⚠️  {dep} 安装可能失败: {result.stderr[:100]}")
        except subprocess.TimeoutExpired:
            print(f"   ⚠️  {dep} 安装超时（120s 未完成，跳过）")
        except FileNotFoundError:
            print(f"   ⚠️  {language} 包管理器未安装（跳过）")
            break
        except Exception as e:
            print(f"   ⚠️  安装 {dep} 失败: {e}")


def run_engineer(status: dict, is_retry: bool = False) -> tuple[bool, str]:
    """
    执行 Engineer 阶段（支持工具调用循环，Stage 2.5）

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

    # 前置步骤：按 language + dependencies 装依赖（Stage 3 P1）
    _install_dependencies(task_data)

    # 读取 QA 报告（重试时需要）
    qa_report = None
    qa_file = session_dir / "qa_report.json"
    if is_retry and qa_file.exists():
        with open(qa_file, "r", encoding="utf-8") as f:
            qa_report = json.load(f)

    # 重试时加载上一次的源码，让 Engineer 不必多一轮 read_file（问题三）
    project_files = None
    if is_retry:
        eng_file = session_dir / "engineer_output.json"
        if eng_file.exists():
            try:
                with open(eng_file, encoding="utf-8") as f:
                    prev = json.load(f)
                project_files = {
                    p["path"]: p.get("content", "")
                    for p in prev.get("files", [])
                    if p.get("content")
                }
            except Exception:
                pass

    # 工具调用循环（Stage 2.5）
    from opc.tools import get_registry

    role_name = "engineer_retry" if is_retry else "engineer"
    messages = [
        {"role": "user", "content": build_engineer_prompt(
            task_data, qa_report, project_files=project_files
        )}
    ]
    max_tool_calls = 10  # 防止无限循环
    tool_call_count = 0
    final_attempt = False  # 工具上限到达后的最后一次机会

    while True:  # 循环条件在内部处理
        # 防止无限循环
        if tool_call_count >= max_tool_calls:
            if final_attempt:
                # 已经给过一次机会了，这次必须返回错误
                print(f"❌ 工具调用循环超过 {max_tool_calls} 次仍未输出代码")
                status["stage"] = "failed"
                return False, "tool_loop_exceeded"
            # 给一次机会，要求直接输出代码
            print(f"⚠️ 工具调用已达上限，追加 final prompt 要求输出代码")
            messages.append({
                "role": "user",
                "content": (
                    "已达到工具调用上限。请立即输出最终代码，不要再调用任何工具。\n"
                    "格式：{\"files\": [{\"path\": \"...\", \"content\": \"...\"}], \"summary\": \"...\"}"
                ),
            })
            tool_call_count += 1
            final_attempt = True

        # 记录 prompt
        log_prompt(
            session_id, role_name,
            messages[-1]["content"],
            retry_count + tool_call_count
        )

        # 调用 LLM
        print(f"🤖 调用 Engineer {'(重试模式)' if is_retry else ''}...")
        try:
            raw_output = call_engineer(messages)
        except Exception as e:
            print(f"❌ Engineer 调用失败: {e}")
            return False, "api_error"

        # 记录原始输出
        log_raw_output(
            session_id, role_name,
            raw_output,
            retry_count + tool_call_count
        )

        # 解析 JSON
        data = parse_json_safe(raw_output)
        if data is None:
            print("❌ Engineer 输出 JSON 解析失败")
            log_parse_error(
                session_id, role_name,
                raw_output,
                retry_count + tool_call_count
            )
            status["stage"] = "parse_error"
            return False, "parse_error"

        # 验证格式
        if not validate_engineer_output(data):
            print("❌ Engineer 输出格式验证失败")
            status["stage"] = "parse_error"
            return False, "validation_error"

        # 检查是否是工具调用
        if "tool_call" in data:
            tool_name = data["tool_call"].get("name", "")
            tool_args = data["tool_call"].get("args", {})

            print(f"🔧 工具调用: {tool_name}({list(tool_args.keys())})")

            # 执行工具
            registry = get_registry()
            tool_result = registry.execute(tool_name, tool_args)

            # 打印结果（截断避免太长）
            if len(tool_result) > 300:
                print(f"📄 工具结果: {tool_result[:300]}...")
            else:
                print(f"📄 工具结果: {tool_result}")

            # 添加到消息历史
            # tool_result 后要明确告知输出 files 格式，不要再调用工具
            messages.append({"role": "assistant", "content": raw_output})
            continuation = (
                f"工具执行结果：\n{tool_result}\n\n"
                "请根据上述结果输出修复后的代码，格式如下：\n"
                '{"files": [{"path": "xxx", "content": "..."}], "summary": "..."}\n\n'
                "不要再次调用工具，直接输出 JSON。"
            )
            messages.append({"role": "user", "content": continuation})

            tool_call_count += 1
            continue

        # 不是工具调用 → 写入文件
        break

    # 写入文件（回放保护：跳过已写入文件）
    try:
        files_to_write = []
        for f in data.get("files", []):
            path = f.get("path", "")
            if is_file_written(session_id, path):
                print(f"⏭️ 跳过已写入文件: {path}")
            else:
                files_to_write.append(f)

        written_files = (
            write_files(PROJECT_ROOT, files_to_write)
            if files_to_write else []
        )

        # 标记所有文件为已写入（包括之前跳过的）
        for f in data.get("files", []):
            path = f.get("path", "")
            mark_file_written(session_id, path)
            log_file_write(
                session_id, path, len(f.get("content", "")),
                skipped=(path not in [ff.get("path") for ff in files_to_write])
            )

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
        "tool_calls": tool_call_count,
    })

    print(f"✅ Engineer 完成 (工具调用 {tool_call_count} 次)")
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
    
    # 从 Engineer 的 engineer_output.json 读取 run_info（问题二）
    # fallback: 没有 run_info 时退回到 task.json 的旧字段
    background_commands = []
    health_port = None
    startup_wait = 10
    test_commands = task_data.get("test_commands", [])
    run_info = {}  # Engineer 的 run_info（提供给 QA analysis prompt 使用）

    eng_file = session_dir / "engineer_output.json"
    if eng_file.exists():
        try:
            with open(eng_file, encoding="utf-8") as f:
                eng_data = json.load(f)
            run_info = eng_data.get("run_info", {}) or {}
            if run_info.get("start_command"):
                background_commands = [run_info["start_command"]]
            if run_info.get("port"):
                health_port = run_info["port"]
                # port 存在 → 自动构造 curl 测试命令
                if not test_commands:
                    test_commands = [
                        f"curl -s http://localhost:{run_info['port']}/",
                        f"curl -s http://localhost:{run_info['port']}/health",
                    ]
        except Exception:
            pass

    # fallback: 没有 run_info 时用 Manager 的旧字段
    if not background_commands:
        background_commands = task_data.get("background_commands", [])
    if not health_port:
        health_port = task_data.get("health_check_port")
    if not test_commands:
        test_commands = task_data.get("test_commands", [])
    startup_wait = task_data.get("startup_wait_seconds", 10)

    # 执行 background_commands
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
                    # 只有非空 stdout 才记录为已执行，避免服务未就绪时错误缓存
                    stdout_empty = not result[0].get("stdout", "").strip() if result else True
                    if not stdout_empty:
                        mark_command_executed(session_id, cmd)
                    else:
                        print(f"⚠️ 命令 stdout 为空，不计入回放保护: {cmd[:50]}")
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

    # 加载 Engineer 写的源码给 QA 参考（Stage 2.5 P1）
    source_code = None
    engineer_file = session_dir / "engineer_output.json"
    if engineer_file.exists():
        try:
            with open(engineer_file, "r", encoding="utf-8") as f:
                engineer_data = json.load(f)
            files = engineer_data.get("files", [])
            if files:
                source_code = {
                    f["path"]: f["content"]
                    for f in files
                    if f.get("path") and f.get("content")
                }
        except Exception:
            pass  # 源码不可用时继续

    # === 两阶段 QA 流程 ===
    # 阶段1：MiniMax 做自由格式分析（无 parse_error 风险）
    analysis_prompt = build_qa_analysis_prompt(task_data, evidence, source_code, run_info)
    log_prompt(session_id, "qa_analysis", analysis_prompt, 0)

    print("🤖 QA 分析 (MiniMax)...")
    try:
        raw_analysis = call_qa([{"role": "user", "content": analysis_prompt}])
        log_llm_call(session_id, "qa", "MiniMax-M2.5", success=True, stage="qa_analysis")
    except Exception as e:
        print(f"❌ QA 分析失败: {e}")
        log_llm_call(session_id, "qa", "MiniMax-M2.5", success=False, error=str(e), stage="qa_analysis")
        return False, "api_error"

    log_raw_output(session_id, "qa_analysis", raw_analysis, 0)

    # 阶段2：DeepSeek 将分析报告格式化为严格 JSON
    format_prompt = build_qa_format_prompt(raw_analysis, task_data)
    log_prompt(session_id, "qa_format", format_prompt, 0)

    print("🤖 QA 格式化 (DeepSeek)...")
    try:
        raw_json = call_qa_formatter([{"role": "user", "content": format_prompt}])
        log_llm_call(session_id, "qa", DEEPSEEK_MODEL, success=True, stage="qa_format")
    except Exception as e:
        print(f"❌ QA 格式化失败: {e}")
        log_llm_call(session_id, "qa", DEEPSEEK_MODEL, success=False, error=str(e), stage="qa_format")
        # DeepSeek 失败时才退回到 fallback（异常情况，不是解析失败）
        return False, "api_error"

    log_raw_output(session_id, "qa_format", raw_json, 0)

    # 解析 JSON（DeepSeek 格式化的，很少失败）
    data = parse_json_safe(raw_json)
    if data is None:
        print("❌ QA 格式化输出 JSON 解析失败")
        log_parse_error(session_id, "qa_format", raw_json, 0)
        fallback_qa = {
            "passed": False,
            "reason": f"DeepSeek 格式化为 JSON 失败。原始分析摘要: {raw_analysis[:300]}",
            "failure_type": "qa_parse_error",
            "evidence": evidence,
        }
        qa_file = session_dir / "qa_report.json"
        with open(qa_file, "w", encoding="utf-8") as f:
            json.dump(fallback_qa, f, ensure_ascii=False, indent=2)
        status["stage"] = "parse_error"
        return False, "parse_error"

    # 验证格式
    if not validate_qa_output(data):
        print("❌ QA 格式化输出格式验证失败")
        fallback_qa = {
            "passed": False,
            "reason": "DeepSeek 格式化输出不符合 schema",
            "failure_type": "qa_validation_error",
            "evidence": evidence,
        }
        qa_file = session_dir / "qa_report.json"
        with open(qa_file, "w", encoding="utf-8") as f:
            json.dump(fallback_qa, f, ensure_ascii=False, indent=2)
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


def _append_retry_history(session_dir: Path, session_id: str, qa_data: dict, failure_type: str) -> None:
    """把小循环失败记录追加到 retry_history，用于 Manager 大循环上下文"""
    history_file = session_dir / "retry_history.json"
    history = []
    if history_file.exists():
        with open(history_file, encoding="utf-8") as f:
            history = json.load(f)

    # 读取上一轮写的文件（从 session 目录下的 written_files）
    written_files = []
    wf_file = session_dir / "written_files.json"
    if wf_file.exists():
        with open(wf_file, encoding="utf-8") as f:
            wf_data = json.load(f)
            if isinstance(wf_data, list):
                if wf_data and isinstance(wf_data[0], dict):
                    written_files = [f"{w.get('path', '')}" for w in wf_data]
                else:
                    written_files = [str(p) for p in wf_data]
            else:
                written_files = list(wf_data.keys())

    history.append({
        "failure_type": failure_type,
        "qa_summary": qa_data.get("reason", "")[:200],
        "files_written": written_files,
    })
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


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
        # 检查是否需要人工审批（human_gate）
        if qa_data.get("needs_human_review", False):
            status["stage"] = "human_review"
            print("🚦 QA 通过，但需要人工审批（human_gate）")
            return

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
        # 统一获取 failure_type（在 if 之前，避免 else 分支未定义）
        failure_type = qa_data.get("failure_type", "unknown")

        if retry_count < MAX_RETRIES:
            status["stage"] = "engineer_retry"
            # 杀后台进程，释放端口，避免 retry 之间端口冲突（问题一）
            cleanup_background()
            # 关键修复：清空 completed_stages 让 Engineer 重新运行
            # 否则 completed_stages 中的 'engineer' 会导致 Engineer 阶段被跳过
            status["completed_stages"] = ["manager"]
            print(f"🔄 进入重试模式 ({retry_count}/{MAX_RETRIES})")
            print(f"📋 失败类型: {failure_type}")
        else:
            # 小循环全部失败 → 写 retry_history，准备进入 Manager 大循环
            _append_retry_history(session_dir, session_id, qa_data, failure_type)
            replan_count = status.get("replan_count", 0)

            if replan_count < MAX_MANAGER_REPLANS:
                status["stage"] = "manager_replan"
                status["completed_stages"] = []  # 清空让 Manager 重新跑
                print(f"🔄 进入 Manager 大循环 ({replan_count + 1}/{MAX_MANAGER_REPLANS})")
            else:
                status["stage"] = "failed"
                print(f"❌ 大循环次数超限，任务失败")
            
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
    from opc.config import DEEPSEEK_API_KEY
    
    errors = []
    
    if not DEEPSEEK_API_KEY:
        errors.append("❌ DEEPSEEK_API_KEY 未设置")
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
            
            elif stage == "manager_replan":
                success, error_type = run_manager_replan(status)
                if success:
                    status["stage"] = "manager_done"
                    status["api_retry_count"] = 0
                    status["parse_retry_count"] = 0
                elif error_type == "parse_error":
                    status["parse_retry_count"] += 1
                    if status["parse_retry_count"] > 1:
                        print("❌ Manager 大循环 JSON 解析连续失败，进入 failed")
                        status["stage"] = "failed"
                    else:
                        print("⚠️ Manager 大循环 JSON 解析失败，重试")
                else:
                    # api_error / duplicate_plan
                    status["api_retry_count"] += 1
                    if status["api_retry_count"] >= MAX_API_RETRIES:
                        print(f"❌ Manager 大循环 API 调用失败超限，进入 failed")
                        status["stage"] = "failed"
                    else:
                        print(f"⚠️ Manager 大循环失败 (api_error/duplicate)，重试 ({status['api_retry_count']}/{MAX_API_RETRIES})")

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
                elif error_type == "tool_loop_exceeded":
                    # tool_loop_exceeded 不重试，直接标记失败
                    increment_retry(status)
                    retry_count = status.get("retry_count", 0)
                    if retry_count >= MAX_RETRIES:
                        print(f"❌ 工具调用循环超限，进入 failed")
                        status["stage"] = "failed"
                    else:
                        print(f"🔄 工具调用循环超限，重试 ({retry_count}/{MAX_RETRIES})")
                        status["stage"] = "engineer_retry"
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
                        # QA 连续失败 2 次 → 强制写入 qa_report（fallback 已在 run_qa 写入）
                        # 调用 handle_qa_result 走正常失败流程（写 retry_history + 决定下一步）
                        print(f"❌ QA JSON 解析连续失败 2 次，调用 handle_qa_result")
                        status["stage"] = "qa_done"  # 伪装成 qa_done，让 handle_qa_result 处理
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

            elif stage == "human_review":
                # human_gate: 等待人工审批
                session_id = status.get("session_id", "unknown")
                session_dir = get_session_dir(session_id)
                qa_file = session_dir / "qa_report.json"
                task_file = session_dir / "task.json"

                print("\n" + "=" * 50)
                print("🚦 HUMAN GATE — 需要人工审批")
                print("=" * 50)

                if qa_file.exists():
                    with open(qa_file, "r") as f:
                        qa_data = json.load(f)
                    print(f"\nQA 判定: {qa_data.get('passed', False)}")
                    print(f"理由: {qa_data.get('reason', 'N/A')[:200]}")
                    print(f"变更摘要: {qa_data.get('summary', 'N/A')}")

                if task_file.exists():
                    with open(task_file, "r") as f:
                        task_data = json.load(f)
                    print(f"\n任务目标: {task_data.get('goal', 'N/A')}")

                print("\n请确认是否接受当前结果:")
                print("  输入 [y/yes] 接受 → success")
                print("  输入 [n/no] 拒绝 → failed")
                print("  输入 [r/retry] 重试 → engineer_retry")
                print(f"  (超时 {60} 秒，自动拒绝)")
                print("> ", end="", flush=True)

                try:
                    import select
                    import sys
                    rlist, _, _ = select.select([sys.stdin], [], [], 60)
                    if rlist:
                        user_input = sys.stdin.readline().strip().lower()
                    else:
                        print("⏰ 超时，自动拒绝")
                        user_input = "n"
                except Exception:
                    # Windows 或非 tty 环境fallback
                    print("(无法读取输入，尝试 tty)")
                    try:
                        user_input = input("> ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        user_input = "n"

                if user_input in ("y", "yes"):
                    status["stage"] = "success"
                    print("✅ 人工审批通过")
                    task_goal = ""
                    if task_file.exists():
                        with open(task_file, "r") as f:
                            task_data = json.load(f)
                            task_goal = task_data.get("goal", "")
                    create_snapshot(session_id, f"Task completed (human approved): {task_goal}", task_goal)
                elif user_input in ("r", "retry"):
                    status["stage"] = "engineer_retry"
                    print("🔄 人工要求重试")
                else:
                    status["stage"] = "failed"
                    print("❌ 人工审批拒绝")
            
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
    
    # 启动时清理所有孤儿后台进程
    orphans = cleanup_all_orphans()
    if orphans > 0:
        print(f"🧹 启动时清理了 {orphans} 个孤儿进程")
    
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
            from opc.config import STRICT_QUEUE_MODE
            if STRICT_QUEUE_MODE:
                print("❌ 严格模式：资源释放验证失败，停止队列")
                break
            else:
                print("⚠️ 资源释放验证失败，继续处理下一个任务（设置 STRICT_QUEUE_MODE=True 可改为中断）")
        
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
