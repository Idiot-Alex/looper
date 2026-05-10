"""
OPC 可视化面板
展示 session 状态、阶段耗时、失败热区
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

from opc.config import LOGS_JSONL, PROJECT_ROOT


def load_events() -> List[Dict]:
    """加载 JSONL 事件"""
    events = []
    if not LOGS_JSONL.exists():
        return events
    
    with open(LOGS_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            try:
                events.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    return events


def group_by_session(events: List[Dict]) -> Dict[str, List[Dict]]:
    """按 session 分组事件"""
    sessions = {}
    for event in events:
        session_id = event.get("session_id", "unknown")
        if session_id not in sessions:
            sessions[session_id] = []
        sessions[session_id].append(event)
    return sessions


def compute_session_stats(session_id: str, events: List[Dict]) -> Dict[str, Any]:
    """计算单个 session 的统计"""
    stats = {
        "session_id": session_id,
        "total_events": len(events),
        "llm_calls": 0,
        "file_writes": 0,
        "command_runs": 0,
        "passed": False,
        "failed": False,
        "parse_error": False,
        "stages": [],
        "failure_type": None,
        "failure_reason": None,
    }
    
    # 按时间排序
    events.sort(key=lambda x: x.get("timestamp", ""))
    
    stage_times = {}
    stage_start = None
    
    for event in events:
        event_type = event.get("event_type")
        
        if event_type == "llm_call":
            stats["llm_calls"] += 1
            stage = event.get("stage")
            if stage:
                stats["stages"].append(stage)
                stage_times[stage] = event.get("timestamp")
        
        elif event_type == "file_write":
            stats["file_writes"] += 1
        
        elif event_type == "command_run":
            stats["command_runs"] += 1
        
        elif event_type == "qa_decision":
            stats["passed"] = event.get("passed", False)
            stats["failed"] = not event.get("passed", False)
            stats["failure_type"] = event.get("failure_type")
            stats["failure_reason"] = event.get("reason")
        
        elif event_type == "session_timeout":
            stats["failed"] = True
            stats["failure_type"] = "timeout"
    
    return stats


def generate_html_report() -> str:
    """生成 HTML 报告"""
    events = load_events()
    sessions = group_by_session(events)
    
    session_stats = []
    for session_id, session_events in sessions.items():
        stats = compute_session_stats(session_id, session_events)
        session_stats.append(stats)
    
    # 排序：最新的在前
    session_stats.sort(key=lambda x: x["session_id"], reverse=True)
    
    # 计算总体统计
    total = len(session_stats)
    success = sum(1 for s in session_stats if s["passed"])
    failed = sum(1 for s in session_stats if s["failed"])
    
    # 失败类型统计
    failure_types = {}
    for s in session_stats:
        if s["failure_type"]:
            failure_types[s["failure_type"]] = failure_types.get(s["failure_type"], 0) + 1
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OPC Dashboard</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f7; padding: 20px; }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    h1 {{ color: #1d1d1f; margin-bottom: 20px; }}
    
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 30px; }}
    .stat-card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .stat-label {{ font-size: 14px; color: #86868b; margin-bottom: 8px; }}
    .stat-value {{ font-size: 32px; font-weight: 600; color: #1d1d1f; }}
    .stat-value.success {{ color: #34c759; }}
    .stat-value.failed {{ color: #ff3b30; }}
    
    .sessions {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .sessions h2 {{ margin-bottom: 16px; color: #1d1d1f; }}
    
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 12px; border-bottom: 1px solid #e5e5e5; }}
    th {{ color: #86868b; font-weight: 500; font-size: 14px; }}
    td {{ font-size: 14px; color: #1d1d1f; }}
    
    .status {{ display: inline-block; padding: 4px 12px; border-radius: 100px; font-size: 12px; font-weight: 500; }}
    .status.success {{ background: #d4edda; color: #155724; }}
    .status.failed {{ background: #f8d7da; color: #721c24; }}
    
    .empty {{ text-align: center; color: #86868b; padding: 40px; }}
</style>
</head>
<body>
<div class="container">
    <h1>📊 OPC Dashboard</h1>
    
    <div class="stats">
        <div class="stat-card">
            <div class="stat-label">总任务数</div>
            <div class="stat-value">{total}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">成功</div>
            <div class="stat-value success">{success}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">失败</div>
            <div class="stat-value failed">{failed}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">成功率</div>
            <div class="stat-value">{success/total*100:.1f}%</div>
        </div>
    </div>
    
    <div class="sessions">
        <h2>最近 Sessions</h2>
"""
    
    if not session_stats:
        html += '<div class="empty">暂无数据</div>'
    else:
        html += """
        <table>
            <thead>
                <tr>
                    <th>Session ID</th>
                    <th>状态</th>
                    <th>LLM 调用</th>
                    <th>文件写入</th>
                    <th>失败原因</th>
                </tr>
            </thead>
            <tbody>
"""
        for s in session_stats[:20]:  # 只显示最近 20 个
            status_class = "success" if s["passed"] else "failed"
            status_text = "✅ 成功" if s["passed"] else "❌ 失败"
            failure_text = s["failure_type"] or "N/A"
            if s["failure_reason"]:
                failure_text = s["failure_reason"][:50]
            
            html += f"""
                <tr>
                    <td>{s['session_id']}</td>
                    <td><span class="status {status_class}">{status_text}</span></td>
                    <td>{s['llm_calls']}</td>
                    <td>{s['file_writes']}</td>
                    <td>{failure_text}</td>
                </tr>
"""
        html += """
            </tbody>
        </table>
"""
    
    html += """
    </div>
</div>
</body>
</html>
"""
    return html


def generate_dashboard(path: Optional[Path] = None) -> Path:
    """生成面板 HTML 文件"""
    if path is None:
        path = PROJECT_ROOT / "opc" / "logs" / "dashboard.html"
    
    html = generate_html_report()
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    
    return path


def open_dashboard():
    """在浏览器中打开面板"""
    import subprocess
    path = generate_dashboard()
    subprocess.run(["open", str(path)], check=True)
