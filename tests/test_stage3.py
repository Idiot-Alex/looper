"""
测试 Stage 3: Engineer 小循环 + Manager 大循环
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from opc.prompts import (
    REPAIR_PROMPT_TEMPLATES,
    build_repair_context,
    build_manager_replan_prompt,
)
from opc.config import MAX_MANAGER_REPLANS, MAX_RETRIES


class TestRepairPromptTemplates:
    """REPAIR_PROMPT_TEMPLATES 各类型非空 + 策略有效"""

    def test_all_7_types_exist(self):
        """7 个 failure_type 全部存在"""
        assert len(REPAIR_PROMPT_TEMPLATES) == 7
        assert "test_failure" in REPAIR_PROMPT_TEMPLATES
        assert "compile_error" in REPAIR_PROMPT_TEMPLATES
        assert "timeout" in REPAIR_PROMPT_TEMPLATES
        assert "runtime_error" in REPAIR_PROMPT_TEMPLATES
        assert "unknown" in REPAIR_PROMPT_TEMPLATES
        assert "qa_parse_error" in REPAIR_PROMPT_TEMPLATES
        assert "qa_validation_error" in REPAIR_PROMPT_TEMPLATES

    def test_test_failure_guides_read_and_edit(self):
        """test_failure 引导用 read_file + edit_file"""
        tpl = REPAIR_PROMPT_TEMPLATES["test_failure"]
        assert "read_file" in tpl
        assert "edit_file" in tpl
        assert len(tpl) > 100  # 不是一句话模板

    def test_compile_error_has_focus_hint(self):
        """compile_error 有定位错误的引导"""
        tpl = REPAIR_PROMPT_TEMPLATES["compile_error"]
        assert "read_file" in tpl

    def test_timeout_guides_performance(self):
        """timeout 引导处理死循环"""
        tpl = REPAIR_PROMPT_TEMPLATES["timeout"]
        assert "read_file" in tpl

    def test_runtime_error_guides_defensive(self):
        """runtime_error 引导防御性编程"""
        tpl = REPAIR_PROMPT_TEMPLATES["runtime_error"]
        assert "read_file" in tpl

    def test_qa_parse_error_mentions_code_check(self):
        """qa_parse_error 引导先确认代码本身是否正确"""
        tpl = REPAIR_PROMPT_TEMPLATES["qa_parse_error"]
        assert "read_file" in tpl

    def test_qa_validation_error_mentions_code_check(self):
        """qa_validation_error 引导先确认代码本身"""
        tpl = REPAIR_PROMPT_TEMPLATES["qa_validation_error"]
        assert "确认代码" in tpl


class TestBuildRepairContext:
    """build_repair_context 根据 failure_type 选择模板"""

    def test_unknown_falls_back_to_unknown_template(self):
        """未知 failure_type 回退到 unknown 模板"""
        qa_report = {"failure_type": "unknown", "reason": "something"}
        task_data = {"goal": "test"}
        result = build_repair_context("unknown", qa_report, task_data)
        assert REPAIR_PROMPT_TEMPLATES["unknown"] in result

    def test_test_failure_uses_test_failure_template(self):
        """test_failure 类型使用对应模板，evidence 被写入"""
        qa_report = {
            "failure_type": "test_failure",
            "reason": "wrong output",
            "evidence": [
                {"command": "python calc.py", "stdout": "0", "exit_code": 0}
            ],
        }
        result = build_repair_context("test_failure", qa_report, {})
        # 模板内容 + evidence 命令都在结果里
        assert REPAIR_PROMPT_TEMPLATES["test_failure"] in result
        assert "python calc.py" in result
        assert "exit_code" in result or "退出码" in result

    def test_build_repair_context_includes_evidence(self):
        """evidence 被包含在修复上下文里"""
        qa_report = {
            "failure_type": "test_failure",
            "reason": "fails",
            "evidence": [{"command": "python fib.py 10", "stdout": "wrong", "exit_code": 0}],
        }
        result = build_repair_context("test_failure", qa_report, {})
        assert "fib.py" in result or "python" in result

    def test_build_repair_context_includes_criterion_results(self):
        """逐条判定结果被包含"""
        qa_report = {
            "failure_type": "test_failure",
            "reason": "criterion failed",
            "criterion_results": [
                {"criterion": "N=10 输出 55", "passed": False, "evidence": "输出 0"}
            ],
        }
        result = build_repair_context("test_failure", qa_report, {})
        assert "❌" in result or "failed" in result.lower()


class TestBuildManagerReplanPrompt:
    """build_manager_replan_prompt 包含失败历史"""

    def test_includes_original_goal(self):
        """prompt 包含原始 goal"""
        prompt = build_manager_replan_prompt(
            original_goal="实现斐波那契",
            retry_history=[],
        )
        assert "实现斐波那契" in prompt

    def test_includes_retry_history(self):
        """prompt 包含 retry_history"""
        history = [
            {
                "failure_type": "test_failure",
                "qa_summary": "输出格式不对",
                "files_written": ["fib.py"],
            }
        ]
        prompt = build_manager_replan_prompt(
            original_goal="实现斐波那契",
            retry_history=history,
        )
        assert "test_failure" in prompt
        assert "输出格式不对" in prompt
        assert "fib.py" in prompt

    def test_includes_multiple_history_entries(self):
        """多条失败历史都包含"""
        history = [
            {"failure_type": "test_failure", "qa_summary": "第一次失败", "files_written": ["a.py"]},
            {"failure_type": "compile_error", "qa_summary": "第二次失败", "files_written": ["b.py"]},
        ]
        prompt = build_manager_replan_prompt(
            original_goal="test",
            retry_history=history,
        )
        assert "第一次失败" in prompt
        assert "第二次失败" in prompt

    def test_includes_project_files(self):
        """包含项目文件"""
        files = {"fib.py": "def fib(n): return 1"}
        prompt = build_manager_replan_prompt(
            original_goal="test",
            retry_history=[],
            project_files=files,
        )
        assert "fib.py" in prompt
        assert "def fib" in prompt

    def test_mentions_different_approach(self):
        """prompt 明确要求换思路"""
        prompt = build_manager_replan_prompt(
            original_goal="test",
            retry_history=[{"failure_type": "test_failure", "qa_summary": "fail", "files_written": []}],
        )
        assert "换" in prompt or "不同" in prompt or "思路" in prompt


class TestAppendRetryHistory:
    """_append_retry_history 写入正确字段"""

    def test_append_retry_history_writes_3_fields(self, tmp_path, monkeypatch):
        """失败记录包含 failure_type + qa_summary + files_written"""
        # mock session_dir
        history_file = tmp_path / "retry_history.json"
        monkeypatch.setattr("opc.main.get_session_dir", lambda s: tmp_path)

        from opc.main import _append_retry_history

        qa_data = {
            "reason": "输出为 0 而不是 55",
            "failure_type": "test_failure",
        }

        _append_retry_history(tmp_path, "test", qa_data, "test_failure")

        assert history_file.exists()
        history = json.loads(history_file.read_text())
        assert len(history) == 1
        assert history[0]["failure_type"] == "test_failure"
        assert "55" in history[0]["qa_summary"]
        assert "files_written" in history[0]

    def test_append_retry_history_appends_not_overwrites(self, tmp_path, monkeypatch):
        """追加而非覆盖"""
        history_file = tmp_path / "retry_history.json"
        history_file.write_text(json.dumps([{"failure_type": "first", "qa_summary": "a", "files_written": []}]))

        from opc.main import _append_retry_history

        qa_data = {"reason": "second", "failure_type": "compile_error"}
        _append_retry_history(tmp_path, "test", qa_data, "compile_error")

        history = json.loads(history_file.read_text())
        assert len(history) == 2
        assert history[0]["failure_type"] == "first"
        assert history[1]["failure_type"] == "compile_error"


class TestManagerReplanDedup:
    """Manager 大循环去重检测"""

    def test_dedup_detects_identical_steps(self):
        """steps 完全相同 → 认为是重复方案"""
        from opc.main import run_manager_replan
        import inspect
        src = inspect.getsource(run_manager_replan)
        assert "old_steps == new_steps" in src

    def test_max_replans_config(self):
        """MAX_MANAGER_REPLANS = 2"""
        assert MAX_MANAGER_REPLANS == 2

    def test_max_retries_config(self):
        """MAX_RETRIES = 3"""
        assert MAX_RETRIES == 3
