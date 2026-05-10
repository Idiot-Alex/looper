"""
OPC 成本与时延统计模块
"""
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from opc.config import LOGS_JSONL, PROJECT_ROOT


class MetricsCollector:
    """成本与时延指标收集器"""
    
    def __init__(self):
        self.events = []
        self.stats = {
            "total_tasks": 0,
            "success_tasks": 0,
            "failed_tasks": 0,
            "parse_error_tasks": 0,
            "total_llm_calls": 0,
            "total_tokens_used": 0,
            "total_duration_ms": 0,
            "avg_task_duration_ms": 0,
            "failure_reasons": {},
            "failure_types": {},
        }
    
    def load_from_jsonl(self):
        """从 JSONL 文件加载历史数据"""
        if not LOGS_JSONL.exists():
            return
        
        with open(LOGS_JSONL, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    self.events.append(event)
                except json.JSONDecodeError:
                    continue
    
    def compute_stats(self) -> Dict[str, Any]:
        """计算统计指标"""
        # 按 session 分组
        sessions = {}
        for event in self.events:
            session_id = event.get("session_id", "unknown")
            if session_id not in sessions:
                sessions[session_id] = []
            sessions[session_id].append(event)
        
        # 统计每个 session
        for session_id, events in sessions.items():
            self.stats["total_tasks"] += 1
            
            # 检查 session 结果
            qa_events = [e for e in events if e.get("event_type") == "qa_decision"]
            for qa in qa_events:
                if qa.get("passed"):
                    self.stats["success_tasks"] += 1
                else:
                    self.stats["failed_tasks"] += 1
                    reason = qa.get("reason", "unknown")[:50]
                    failure_type = qa.get("failure_type", "unknown")
                    self.stats["failure_reasons"][reason] = self.stats["failure_reasons"].get(reason, 0) + 1
                    self.stats["failure_types"][failure_type] = self.stats["failure_types"].get(failure_type, 0) + 1
            
            parse_events = [e for e in events if e.get("event_type") == "parse_error"]
            if parse_events:
                self.stats["parse_error_tasks"] += 1
            
            # LLM 调用统计
            llm_events = [e for e in events if e.get("event_type") == "llm_call"]
            self.stats["total_llm_calls"] += len(llm_events)
            
            for llm in llm_events:
                tokens = llm.get("tokens_used")
                if tokens:
                    self.stats["total_tokens_used"] += tokens
                
                duration = llm.get("duration_ms")
                if duration:
                    self.stats["total_duration_ms"] += duration
        
        # 计算平均值
        if self.stats["total_tasks"] > 0:
            self.stats["avg_task_duration_ms"] = (
                self.stats["total_duration_ms"] / self.stats["total_tasks"]
            )
        
        return self.stats
    
    def get_summary(self) -> str:
        """获取摘要报告"""
        self.load_from_jsonl()
        stats = self.compute_stats()
        
        lines = [
            "=" * 50,
            "📊 OPC 运行统计",
            "=" * 50,
            f"总任务数: {stats['total_tasks']}",
            f"  成功: {stats['success_tasks']}",
            f"  失败: {stats['failed_tasks']}",
            f"  协议错误: {stats['parse_error_tasks']}",
            f"LLM 调用次数: {stats['total_llm_calls']}",
            f"总 Token 消耗: {stats['total_tokens_used']}",
            f"总耗时: {stats['total_duration_ms'] / 1000:.1f}s",
            f"平均任务耗时: {stats['avg_task_duration_ms'] / 1000:.1f}s",
        ]
        
        if stats["failure_types"]:
            lines.append("\n失败类型分布:")
            for ftype, count in sorted(stats["failure_types"].items(), key=lambda x: -x[1]):
                lines.append(f"  {ftype}: {count}")
        
        lines.append("=" * 50)
        return "\n".join(lines)
    
    def export_json(self, path: Optional[Path] = None) -> Path:
        """导出为 JSON 文件"""
        if path is None:
            path = PROJECT_ROOT / "opc" / "logs" / "metrics.json"
        
        self.load_from_jsonl()
        data = {
            "generated_at": datetime.now().isoformat(),
            "stats": self.compute_stats(),
        }
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return path


def get_metrics_summary() -> str:
    """获取统计摘要（便捷函数）"""
    collector = MetricsCollector()
    return collector.get_summary()


def export_metrics(path: Optional[Path] = None) -> Path:
    """导出指标（便捷函数）"""
    collector = MetricsCollector()
    return collector.export_json(path)
