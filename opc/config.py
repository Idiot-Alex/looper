"""
OPC Stage 1 配置
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 文件
_project_root = Path(__file__).parent.parent.resolve()
load_dotenv(_project_root / ".env")

# 项目根目录
PROJECT_ROOT = _project_root

# OPC 目录
OPC_DIR = PROJECT_ROOT / "opc"
AGENTS_DIR = OPC_DIR / "agents"
TASKS_DIR = OPC_DIR / "tasks"
RUNTIME_DIR = OPC_DIR / "runtime"
LOGS_DIR = OPC_DIR / "logs"
MEMORY_DIR = OPC_DIR / "memory"

# 日志子目录
LOGS_SESSIONS = LOGS_DIR / "sessions"
LOGS_PROMPTS = LOGS_DIR / "prompts"
LOGS_RAW_OUTPUTS = LOGS_DIR / "raw_outputs"
LOGS_COMMAND_RUNS = LOGS_DIR / "command_runs"

# 运行时文件
RUNTIME_STDOUT = RUNTIME_DIR / "last_stdout.txt"
RUNTIME_STDERR = RUNTIME_DIR / "last_stderr.txt"
RUNTIME_EXIT_CODE = RUNTIME_DIR / "last_exit_code.txt"
RUNTIME_COMMAND = RUNTIME_DIR / "last_command.txt"
RUNTIME_BACKGROUND_PIDS = RUNTIME_DIR / "background_pids.json"

# 状态文件
STATUS_FILE = TASKS_DIR / "status.json"
INBOX_FILE = TASKS_DIR / "inbox.md"

# LLM 配置
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = "https://api.minimaxi.com/v1"
MINIMAX_MODEL = "abab6.5s-chat"

# 执行配置
DEFAULT_COMMAND_TIMEOUT = 30  # 秒
DEFAULT_STARTUP_TIMEOUT = 10  # 秒
MAX_RETRIES = 3  # 最大重试次数
MAX_API_RETRIES = 3  # API 调用最大重试次数

# 允许写入的目录（白名单）
ALLOWED_WRITE_DIRS = [PROJECT_ROOT]

# 合法状态
VALID_STAGES = [
    "inbox",
    "manager_done",
    "engineer_done",
    "engineer_retry",
    "qa_done",
    "success",
    "failed",
    "parse_error",
]

# 终态
TERMINAL_STAGES = ["success", "failed", "parse_error"]
