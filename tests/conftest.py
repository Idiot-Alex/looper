"""
OPC 测试基础设施
"""
import sys
import types
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def temp_workspace(tmp_path):
    """临时工作区，隔离测试文件"""
    original = Path.cwd()
    import os
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original)


@pytest.fixture
def mock_config(monkeypatch):
    """
    为测试提供完整的 mock opc.config
    不手动构造字段，而是 patch 真实 config 的路径
    """
    from opc import config as real_config

    tmp = Path(tempfile.mkdtemp())

    # 重定向所有路径到临时目录
    monkeypatch.setattr(real_config, "PROJECT_ROOT", tmp)
    monkeypatch.setattr(real_config, "OPC_DIR", tmp / "opc")
    monkeypatch.setattr(real_config, "TASKS_DIR", tmp / "opc" / "tasks")
    monkeypatch.setattr(real_config, "RUNTIME_DIR", tmp / "opc" / "runtime")
    monkeypatch.setattr(real_config, "LOGS_DIR", tmp / "opc" / "logs")

    # 创建目录
    (tmp / "opc" / "tasks" / "inbox").mkdir(parents=True, exist_ok=True)
    (tmp / "opc" / "tasks" / "done").mkdir(parents=True, exist_ok=True)
    (tmp / "opc" / "runtime").mkdir(parents=True, exist_ok=True)
    (tmp / "opc" / "logs").mkdir(parents=True, exist_ok=True)

    # patch INBOX_DIR, DONE_DIR
    monkeypatch.setattr(real_config, "INBOX_DIR", tmp / "opc" / "tasks" / "inbox")
    monkeypatch.setattr(real_config, "DONE_DIR", tmp / "opc" / "tasks" / "done")

    # CRITICAL: patch 使用点的绑定（Python import 绑定问题）
    # opc.queue 在 import 时绑定了 TASKS_DIR 的引用，需 patch 到使用模块
    import opc.queue
    monkeypatch.setattr(opc.queue, "TASKS_DIR", tmp / "opc" / "tasks")
    monkeypatch.setattr(opc.queue, "INBOX_DIR", tmp / "opc" / "tasks" / "inbox")
    monkeypatch.setattr(opc.queue, "DONE_DIR", tmp / "opc" / "tasks" / "done")

    # patch executor 的 RUNTIME_BACKGROUND_PIDS
    import opc.executor
    monkeypatch.setattr(opc.executor, "RUNTIME_BACKGROUND_PIDS", tmp / "opc" / "runtime" / "background_pids.json")

    yield real_config
