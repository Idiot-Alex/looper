import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch


def load_executor_module():
    fake_config = types.ModuleType("opc.config")
    fake_config.RUNTIME_DIR = Path("/tmp/runtime")
    fake_config.RUNTIME_STDOUT = Path("/tmp/runtime/last_stdout.txt")
    fake_config.RUNTIME_STDERR = Path("/tmp/runtime/last_stderr.txt")
    fake_config.RUNTIME_EXIT_CODE = Path("/tmp/runtime/last_exit_code.txt")
    fake_config.RUNTIME_COMMAND = Path("/tmp/runtime/last_command.txt")
    fake_config.RUNTIME_BACKGROUND_PIDS = Path("/tmp/runtime/background_pids.json")
    fake_config.DEFAULT_COMMAND_TIMEOUT = 30
    fake_config.DEFAULT_STARTUP_TIMEOUT = 10
    fake_config.LOGS_COMMAND_RUNS = Path("/tmp/logs/command_runs")
    fake_config.SESSION_TIMEOUT_SECONDS = 900
    
    # 注入假 sandbox 模块
    fake_sandbox = types.ModuleType("opc.sandbox")
    def _noop(*a, **kw): return True
    fake_sandbox.validate_command = _noop
    fake_sandbox.validate_working_directory = _noop
    fake_sandbox.check_session_timeout = lambda x: False
    fake_sandbox.set_resource_limits = _noop
    sys.modules["opc.sandbox"] = fake_sandbox

    fake_pkg = types.ModuleType("opc")
    fake_pkg.__path__ = []  # mark as package
    sys.modules["opc"] = fake_pkg
    sys.modules["opc.config"] = fake_config

    executor_path = Path(__file__).resolve().parents[1] / "opc" / "executor.py"
    spec = importlib.util.spec_from_file_location("opc.executor", executor_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["opc.executor"] = module
    setattr(fake_pkg, "executor", module)
    spec.loader.exec_module(module)
    return module


executor = load_executor_module()
from unittest.mock import patch

from opc import executor


def test_cleanup_background_skips_invalid_pids():
    with patch.object(executor, "load_background_pids", return_value={"pids": ["x"], "commands": [], "started_at": None}), \
         patch.object(executor, "save_background_pids") as save_mock, \
         patch("builtins.print") as print_mock:
        executor.cleanup_background()

    save_mock.assert_called_once_with({"pids": [], "commands": [], "started_at": None})
    print_mock.assert_called_once()


def test_cleanup_background_escalates_to_sigkill_when_process_alive():
    pid = 12345
    calls = []

    def fake_kill(target_pid, sig):
        calls.append((target_pid, sig))

    with patch.object(executor, "load_background_pids", return_value={"pids": [pid], "commands": [], "started_at": None}), \
         patch.object(executor, "save_background_pids"), \
         patch("opc.executor.os.kill", side_effect=fake_kill), \
         patch("opc.executor.time.sleep", return_value=None), \
         patch("opc.executor.time.time", side_effect=[0, 0, 1, 2, 3, 4]), \
         patch("builtins.print"):
        executor.cleanup_background()

    assert calls[0] == (pid, executor.signal.SIGTERM)
    assert calls[-1] == (pid, executor.signal.SIGKILL)
