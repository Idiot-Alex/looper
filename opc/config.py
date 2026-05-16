"""
OPC 配置
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 文件
_project_root = Path(__file__).parent.parent.resolve()
load_dotenv(_project_root / ".env")

# 关闭系统代理（Python urllib/httpx 会读取 macOS 系统代理设置）
# 如果代理进程没在跑，会导致所有 HTTP 请求 Connection refused
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

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

# 状态文件（Stage 1 兼容）
STATUS_FILE = TASKS_DIR / "status.json"
INBOX_FILE = TASKS_DIR / "inbox.md"

# 队列相关路径（Stage 2）
INBOX_DIR = TASKS_DIR / "inbox"
DONE_DIR = TASKS_DIR / "done"
SESSION_DIR = TASKS_DIR / "{session_id}"  # 每个 session 的独立目录

# LLM 配置
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = "https://api.minimaxi.com/v1"
MINIMAX_MODEL = "MiniMax-M2.5"

# 执行配置
DEFAULT_COMMAND_TIMEOUT = 30  # 秒
DEFAULT_STARTUP_TIMEOUT = 10  # 秒
MAX_RETRIES = 3  # 最大重试次数
MAX_API_RETRIES = 3  # API 调用最大重试次数
MAX_MANAGER_REPLANS = 2  # Manager 大循环最大重规划次数

# 允许写入的目录（白名单）
ALLOWED_WRITE_DIRS = [PROJECT_ROOT]

# 包管理器映射
PACKAGE_MANAGER_MAP = {
    "python":     "uv pip install {pkg}",  # uv 项目用 uv pip
    "javascript": "npm install {pkg}",
    "typescript": "npm install {pkg}",
    "go":         "go get {pkg}",
    "rust":       "cargo add {pkg}",
}

# 合法状态
VALID_STAGES = [
    "inbox",
    "manager_done",
    "engineer_done",
    "engineer_retry",
    "qa_done",
    "human_review",
    "success",
    "failed",
    "parse_error",
]

# 终态（human_review 不是终态，审批后才转 success/failed）
TERMINAL_STAGES = ["success", "failed", "parse_error"]

# Session 全局超时（15分钟）
SESSION_TIMEOUT_SECONDS = 900

# 队列严格模式：资源释放失败时是否中断队列
# True = 严格模式，任一任务资源未释放则停止队列
# False = 宽松模式，仅告警但不中断（默认）
STRICT_QUEUE_MODE = False

# 命令黑名单（禁止执行）
FORBIDDEN_COMMANDS = [
    "sudo", "rm -rf /", "mkfs", "dd if=", 
]

# 允许的工作目录
ALLOWED_WORK_DIRS = [PROJECT_ROOT]

# 结构化日志路径
LOGS_JSONL = LOGS_DIR / "events.jsonl"
