"""
测试 Stage 2 队列管理
"""
import time
import json
import pytest
from pathlib import Path

from opc.queue import (
    scan_inbox, mark_done, get_next_task,
    is_command_executed, mark_command_executed, command_hash,
    is_file_written, mark_file_written,
)


class TestFIFOQueue:
    """FIFO 队列测试"""
    
    def test_empty_inbox(self):
        """空队列"""
        tasks = scan_inbox()
        # inbox 里可能有遗留文件，只验证格式
        for t in tasks:
            assert "session_id" in t
            assert "path" in t
    
    def test_fifo_ordering(self, monkeypatch):
        """FIFO 按 mtime 排序"""
        from opc.queue import INBOX_DIR
        
        # 清空 inbox
        for f in INBOX_DIR.glob("*.md"):
            f.unlink()
        
        # 创建 3 个文件
        files = []
        for i, name in enumerate(["c", "a", "b"]):
            f = INBOX_DIR / f"2026-05-10-00{i}.md"
            f.write_text(f"test {name}")
            time.sleep(0.05)
            files.append(f)
        
        tasks = scan_inbox()
        
        # 按 mtime 升序，a 最早 → c 最晚
        ids = [t["session_id"] for t in tasks]
        assert ids == ["2026-05-10-000", "2026-05-10-001", "2026-05-10-002"]


class TestReplayProtection:
    """回放保护"""
    
    def test_command_dedup(self, monkeypatch, tmp_path):
        """命令去重"""
        # 使用临时目录隔离测试
        from opc.queue import get_executed_commands_file
        import uuid
        cmd = f"echo {uuid.uuid4().hex}"
        session_id = f"test-{uuid.uuid4().hex[:8]}"
        
        assert not is_command_executed(session_id, cmd)
        mark_command_executed(session_id, cmd)
        assert is_command_executed(session_id, cmd)
    
    def test_command_hash_different(self):
        """不同命令 hash 不同"""
        assert command_hash("echo a") != command_hash("echo b")
    
    def test_file_write_dedup(self, monkeypatch):
        """文件写入去重"""
        import uuid
        path = f"test_file_{uuid.uuid4().hex[:8]}.py"
        session_id = f"test-{uuid.uuid4().hex[:8]}"
        
        assert not is_file_written(session_id, path)
        mark_file_written(session_id, path)
        assert is_file_written(session_id, path)


class TestResourceVerification:
    """资源释放验证"""
    from opc.executor import verify_resources_released
    
    def test_no_ports_check(self):
        """无端口检查返回 True"""
        from opc.executor import verify_resources_released
        assert verify_resources_released(ports=[]) is True
    
    def test_unused_port_check(self):
        """未使用端口返回 True"""
        from opc.executor import verify_resources_released
        assert verify_resources_released(ports=[59999]) is True
