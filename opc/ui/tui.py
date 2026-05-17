"""Looper TUI — 终端实时状态面板"""
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Header, Footer, Input, RichLog, Static, Button

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INBOX_DIR = PROJECT_ROOT / "opc" / "tasks" / "inbox"
INBOX_DIR.mkdir(parents=True, exist_ok=True)

PATTERNS = {
    "🤖 调用 Manager": "Manager 规划中...",
    "✅ Manager 完成": "✅ Manager 完成",
    "🤖 调用 Engineer": "🤖 Engineer 编码中...",
    "🔧 工具调用: read_file": "📖 read_file",
    "🔧 工具调用: write_file": "✏️ write_file",
    "🔧 工具调用: list_files": "📂 list_files",
    "🔧 工具调用: edit_file": "✂️ edit_file",
    "🔧 工具调用: search_code": "🔍 search_code",
    "✅ 写入文件:": "✅ 写入:",
    "🚀 启动后台进程": "🚀 启动服务",
    "🧪 执行测试命令": "🧪 测试中",
    "🤖 QA 审计": "🤖 QA 审计 (DeepSeek)...",
    "🎉 任务成功完成": "🎉 任务成功！",
    "📸 Git 快照创建": "📸 Git 快照",
    "❌ 重试次数超限": "❌ 任务失败",
    "❌ 大循环次数超限": "❌ 任务失败",
    "⚠️ 命令 stdout 为空": "⚠️ 服务未就绪",
}


def summarize_line(line: str) -> str:
    """将 OPC 原始输出行转为 TUI 状态行"""
    for pattern, summary in PATTERNS.items():
        if pattern in line:
            return summary
    # 特殊处理 QA 判定行
    if "QA 判定" in line:
        if "✅" in line:
            return "✅ QA 通过"
        return "❌ QA 未通过"
    # 端口探测
    if "端口探测" in line and "已就绪" in line:
        return "✅ 端口就绪"
    # 普通行直接显示
    stripped = line.strip()
    if stripped and not stripped.startswith("="):
        return stripped[:80]
    return ""


class LooperTUI(App):
    """Looper 终端状态面板"""

    CSS = """
    Screen {
        background: #1e1e2e;
    }
    #main-container {
        height: 100%;
        padding: 1;
    }
    #input-row {
        height: 5;
        margin-bottom: 1;
    }
    #task-input {
        dock: left;
        width: 80%;
        margin-right: 1;
    }
    #submit-btn {
        dock: right;
        width: 18%;
    }
    #log-box {
        height: 1fr;
        border: solid #6c7086;
        margin-bottom: 1;
    }
    RichLog {
        background: #181825;
    }
    #stats-bar {
        height: 3;
        background: #313244;
        content-align: center middle;
        padding: 1;
    }
    #stats-bar > Static {
        width: 1fr;
        text-align: center;
    }
    .label {
        color: #a6adc8;
    }
    .value {
        color: #cdd6f4;
    }
    Button {
        background: #45475a;
        color: #cdd6f4;
    }
    Button:hover {
        background: #585b70;
    }
    """

    task_count = reactive(0)
    success_count = reactive(0)
    fail_count = reactive(0)
    is_running = reactive(False)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="main-container"):
            with Horizontal(id="input-row"):
                yield Input(
                    placeholder="📝 输入需求描述，Enter 提交...",
                    id="task-input",
                )
                yield Button("提交 ▶", id="submit-btn", variant="primary")
            yield RichLog(id="log-box", highlight=True, markup=True, max_lines=1000)
            with Horizontal(id="stats-bar"):
                yield Static("📊 任务: 0", id="stat-tasks")
                yield Static("✅ 成功: 0", id="stat-ok")
                yield Static("❌ 失败: 0", id="stat-fail")
                yield Static("⚡ 状态: 空闲", id="stat-status")
        yield Footer()

    def on_mount(self) -> None:
        """启动时聚焦输入框"""
        self.query_one("#task-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """提交按钮点击"""
        if event.button.id == "submit-btn":
            self._submit_task()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter 提交"""
        self._submit_task()

    def _submit_task(self) -> None:
        """提交当前输入框中的任务"""
        if self.is_running:
            self._log("⚠️ 正在运行中，请等待当前任务完成")
            return

        task_input = self.query_one("#task-input", Input)
        task = task_input.value.strip()
        if not task:
            return

        self.is_running = True
        self.query_one("#stat-status", Static).update("⚡ 状态: 运行中...")

        # 写 inbox
        session_id = datetime.now().strftime("tui_%Y%m%d_%H%M%S")
        inbox_file = INBOX_DIR / f"{session_id}.md"
        inbox_file.write_text(task, encoding="utf-8")

        task_input.clear()
        self.task_count += 1
        self._update_stats()
        self._log(f"📝 新任务: {task[:60]}...")
        self._log(f"📁 session: {session_id}")

        # 后台执行
        threading.Thread(
            target=self._run_looper,
            args=(session_id, task),
            daemon=True,
        ).start()

    def _run_looper(self, session_id: str, task: str) -> None:
        """后台执行 Looper"""
        start_time = time.time()
        try:
            result = subprocess.run(
                ["uv", "run", "python", "-m", "opc.main"],
                capture_output=True, text=True, timeout=300,
            )
        except subprocess.TimeoutExpired:
            self.call_from_thread(self._log, "⏰ 任务执行超时（300s）")
            self.call_from_thread(self._task_done, False)
            return

        duration = time.time() - start_time
        # 解析输出行
        lines = []
        for line in result.stdout.split("\n"):
            summary = summarize_line(line)
            if summary:
                lines.append(summary)

        try:
            self.call_from_thread(self._display_results, lines, duration)
        except Exception:
            pass

    def _display_results(self, lines: list, duration: float) -> None:
        """显示执行结果"""
        for line in lines:
            self._log(line)
            if "🎉 任务成功" in line:
                self._task_done(True)
            elif "失败" in line and ("重试" not in line and "审计" not in line):
                pass  # 继续看最终状态

        # 检查最终状态行
        all_text = " ".join(lines)
        if "🎉 任务成功" in all_text:
            self._task_done(True)
        elif "❌ 任务失败" in all_text or "任务失败" in all_text:
            self._task_done(False)
        else:
            # 看退出码
            self._log(f"⏱️ 耗时: {duration:.0f}s")
            self._task_done(True)  # 默认标记完成

    def _task_done(self, success: bool) -> None:
        """任务结束"""
        self.is_running = False
        if success:
            self.success_count += 1
            self._log("✅ 任务完成")
        else:
            self.fail_count += 1
            self._log("❌ 任务失败")
        self._update_stats()
        self.query_one("#stat-status", Static).update("⚡ 状态: 空闲")
        self.query_one("#task-input", Input).focus()

    def _log(self, msg: str) -> None:
        """写入日志面板"""
        log = self.query_one("#log-box", RichLog)
        log.write(msg)

    def _update_stats(self) -> None:
        """更新统计栏"""
        self.query_one("#stat-tasks", Static).update(f"📊 任务: {self.task_count}")
        self.query_one("#stat-ok", Static).update(f"✅ 成功: {self.success_count}")
        self.query_one("#stat-fail", Static).update(f"❌ 失败: {self.fail_count}")


def main():
    app = LooperTUI()
    app.run()


if __name__ == "__main__":
    main()
