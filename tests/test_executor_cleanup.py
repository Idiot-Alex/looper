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
