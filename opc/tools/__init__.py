"""
OPC Tool System
Tool ABC + ToolRegistry for Engineer tool-calling (Stage 2.5)
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional

from opc.config import PROJECT_ROOT


class Tool(ABC):
    """Tool abstract base class"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name (used in JSON protocol)"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for LLM context"""
        pass

    @property
    def args_schema(self) -> Dict[str, str]:
        """Argument schema: {arg_name: description}"""
        return {}

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """
        Execute the tool.

        Args:
            **kwargs: Tool arguments from JSON {"name": "read_file", "args": {"path": "..."}}

        Returns:
            Result string to append to messages
        """
        pass


class ToolRegistry:
    """Registry for available tools"""

    _instance: Optional["ToolRegistry"] = None

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_default_tools()
        return cls._instance

    def _register_default_tools(self) -> None:
        """Register built-in tools"""
        from opc.tools.file_tools import ReadFileTool, EditFileTool

        self.register(ReadFileTool())
        self.register(EditFileTool())

    def register(self, tool: Tool) -> None:
        """Register a tool"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name"""
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, Tool]:
        """List all registered tools"""
        return self._tools.copy()

    def execute(self, name: str, args: Dict[str, Any]) -> str:
        """
        Execute a tool by name.

        Args:
            name: Tool name
            args: Tool arguments

        Returns:
            Result string

        Raises:
            KeyError: Tool not found
        """
        tool = self.get(name)
        if tool is None:
            available = list(self._tools.keys())
            return f'Error: Tool "{name}" not found. Available tools: {available}'

        try:
            return tool.execute(**args)
        except TypeError as e:
            return f'Error: Invalid arguments for {name}: {e}'


def get_registry() -> ToolRegistry:
    """Get the tool registry singleton"""
    return ToolRegistry.get_instance()


def build_tools_description() -> str:
    """
    Build tool descriptions for LLM prompt.

    Returns:
        Markdown-formatted tool descriptions
    """
    registry = get_registry()
    lines = []

    lines.append("## Available Tools\n")
    lines.append(
        "你可以调用工具读取现有文件，再决定如何修改。\n"
        "**调用格式**: ```json\n{\"tool_call\": {\"name\": \"tool_name\", \"args\": {...}}}\n```\n"
    )
    lines.append("**使用建议**: 修改文件前先调用 read_file 查看现有内容。\n\n")

    for tool in registry.list_tools().values():
        args_parts = [f"{k} - {v}" for k, v in tool.args_schema.items()]
        args_str = "; ".join(args_parts) if args_parts else "(无参数)"

        lines.append(f"### {tool.name}\n")
        lines.append(f"{tool.description}\n")
        lines.append(f"**参数**: {args_str}\n\n")
        lines.append("```json\n")
        lines.append(f'{{"tool_call": {{"name": "{tool.name}", "args": ')
        if tool.args_schema:
            example_args = {k: f"<{k}>" for k in tool.args_schema}
        else:
            example_args = {}
        lines.append(f"{example_args}}}\n")
        lines.append("}\n```\n\n")

    return "".join(lines)
