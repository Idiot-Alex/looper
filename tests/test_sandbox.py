"""
测试沙箱模块
"""
import pytest
from opc.sandbox import validate_command, validate_working_directory, SandboxError
from opc.sandbox import check_session_timeout, set_resource_limits
from pathlib import Path


class TestCommandValidation:
    """命令安全校验"""
    
    def test_legal_commands(self):
        """合法命令通过"""
        validate_command("python3 server.py")
        validate_command("curl -s http://localhost:8080")
        validate_command("echo hello")
    
    def test_forbidden_commands(self):
        """禁止命令被拦截"""
        with pytest.raises(SandboxError, match="sudo"):
            validate_command("sudo rm -rf /")
        
        with pytest.raises(SandboxError, match="dd"):
            validate_command("dd if=/dev/zero of=test")
    
    def test_partial_match_no_false_positive(self):
        """不因部分子串误拦截"""
        # "dds" 不应该匹配 "dd if="
        validate_command("cat dds_file.txt")


class TestWorkingDirectoryValidation:
    """工作目录校验"""
    
    def test_none_cwd(self):
        """None 表示不需要校验"""
        assert validate_working_directory(None) is True


class TestSessionTimeout:
    """Session 超时检测"""
    
    def test_no_session_start(self, monkeypatch):
        """未设置 OPC_SESSION_START 时返回 False"""
        monkeypatch.delenv("OPC_SESSION_START", raising=False)
        assert check_session_timeout(900) is False


class TestResourceLimits:
    """资源限制"""
    
    def test_set_limits_no_crash(self):
        """设置资源限制不抛异常"""
        set_resource_limits()
