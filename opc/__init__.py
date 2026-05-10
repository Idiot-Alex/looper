"""
OPC - AI 代码工厂
"""
from opc.config import *
from opc.state import *
from opc.llm import *
from opc.parser import *
from opc.writer import *
from opc.executor import *
from opc.logger import *
from opc.prompts import *
from opc.queue import *
from opc.sandbox import *
from opc.git_snapshot import *
from opc.metrics import get_metrics_summary, export_metrics
from opc.dashboard import generate_dashboard, open_dashboard

__version__ = "2.0.0"
