"""
测试 Git 快照模块
"""
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

from opc.git_snapshot import create_snapshot, get_last_commit_hash


class TestGitSnapshot:
    """Git 快照测试"""
    
    def test_not_in_git_repo(self, monkeypatch):
        """非 git 仓库时返回 False"""
        def fake_run(cmd, **kwargs):
            # 模拟 git rev-parse 返回 false
            result = MagicMock()
            result.stdout = "false\n"
            result.stderr = ""
            return result
        
        monkeypatch.setattr(subprocess, "run", fake_run)
        result = create_snapshot("test", "test summary")
        assert result is False
    
    def test_successful_snapshot(self, monkeypatch):
        """成功创建快照"""
        class SubprocessResult:
            def __init__(self, stdout="", stderr="", returncode=0):
                self.stdout = stdout
                self.stderr = stderr
                self.returncode = returncode
        
        def fake_run(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            
            if "--is-inside-work-tree" in cmd_str:
                return SubprocessResult("true\n")
            
            # git diff --cached --quiet: exit 1 = has changes (not an error)
            if "--quiet" in cmd_str:
                return SubprocessResult(returncode=1)
            
            # git add -A: success
            if "add" in cmd_str:
                return SubprocessResult()
            
            # git commit: success
            if "commit" in cmd_str:
                return SubprocessResult()
            
            # git rev-parse --short HEAD
            if "--short" in cmd_str:
                return SubprocessResult("abc1234\n")
            
            return SubprocessResult()
        
        monkeypatch.setattr(subprocess, "run", fake_run)
        
        result = create_snapshot("test", "test summary")
        assert result is True


class TestGetCommitHash:
    """获取 commit hash"""
    
    def test_no_commits(self, monkeypatch):
        """无 commit 时返回 None"""
        def fake_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd)
        
        monkeypatch.setattr(subprocess, "run", fake_run)
        assert get_last_commit_hash() is None
