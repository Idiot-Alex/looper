"""
Search Tools for OPC
search_code implementation (Stage 2.5 P1)
"""
import re
from pathlib import Path
from typing import List, Tuple

from opc.config import PROJECT_ROOT, ALLOWED_WRITE_DIRS
from opc.tools import Tool


MAX_RESULTS = 50  # 最多返回多少匹配结果
MAX_CONTEXT_LINES = 3  # 每条结果显示多少行上下文
MAX_FILE_SIZE = 1024 * 1024  # 跳过大于 1MB 的文件


# 默认排除的文件/目录
EXCLUDE_PATTERNS = {
    "__pycache__", ".git", ".pytest_cache", ".venv",
    "node_modules", ".DS_Store",
    "*.pyc", "*.pyo", "*.so", "*.egg-info", "*.bak",
    "opc/tasks", "opc/logs", "opc/runtime",
    "hello*.py", "server*.py", "test*.sh",
}


def _match_exclude(path: Path) -> bool:
    """检查文件是否应该被排除"""
    parts = path.parts
    name = path.name

    # 排除特定目录
    for part in parts:
        if part in EXCLUDE_PATTERNS or part.startswith("."):
            return True

    # 排除特定文件名
    if name in EXCLUDE_PATTERNS:
        return True

    # 排除特定后缀
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith("*.") and name.endswith(pattern[1:]):
            return True

    return False


def _search_file(
    path: Path,
    pattern: str,
    is_regex: bool,
) -> List[Tuple[int, str]]:
    """
    在单个文件中搜索模式。

    Returns:
        List of (line_number, line_content) matches
    """
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return []

        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except (OSError, UnicodeDecodeError):
        return []

    matches = []
    compiled = re.compile(pattern) if is_regex else re.compile(re.escape(pattern))

    for i, line in enumerate(lines, 1):
        if compiled.search(line):
            matches.append((i, line.rstrip()))
            if len(matches) >= MAX_RESULTS:
                break

    return matches


class SearchCodeTool(Tool):
    """Tool to search for code patterns in the project"""

    @property
    def name(self) -> str:
        return "search_code"

    @property
    def description(self) -> str:
        return (
            "在项目代码中搜索关键词或正则表达式。"
            "返回匹配的文件路径、行号和代码片段。"
            "适合查找函数定义、变量引用、API 端点等。"
        )

    @property
    def args_schema(self) -> dict:
        return {
            "pattern": "搜索关键词或正则表达式",
            "file_filter": "可选，文件后缀过滤（如 .py, .js），多个用逗号分隔",
        }

    def execute(
        self,
        pattern: str,
        file_filter: str = "",
    ) -> str:
        """Execute search_code"""
        if not pattern or len(pattern) < 2:
            return "Error: pattern must be at least 2 characters"

        if len(pattern) > 200:
            return "Error: pattern too long (max 200 chars)"

        # 判断是否是正则
        is_regex = False
        if any(c in pattern for c in r"\[]{}().*+?^$|"):
            is_regex = True
            try:
                re.compile(pattern)
            except re.error as e:
                return f"Error: invalid regex: {e}"

        # 解析文件过滤器
        extensions = None
        if file_filter:
            extensions = {ext.strip() for ext in file_filter.split(",") if ext.strip()}
            extensions = {ext if ext.startswith(".") else f".{ext}" for ext in extensions}

        # 收集匹配文件
        total_matches = 0
        files_scanned = 0
        files_with_matches = 0
        file_results: List[str] = []

        for path in PROJECT_ROOT.rglob("*"):
            if not path.is_file():
                continue
            if _match_exclude(path):
                continue
            if extensions and path.suffix not in extensions:
                continue

            files_scanned += 1
            matches = _search_file(path, pattern, is_regex)
            if not matches:
                continue

            files_with_matches += 1

            # 找到匹配，生成输出
            rel_path = path.relative_to(PROJECT_ROOT)

            if total_matches == 0:
                file_results.append(f"=== Search: '{pattern}' ===\n")

            file_results.append(f"\n📄 {rel_path} ({len(matches)} matches)\n")
            file_results.append("-" * 60 + "\n")

            for lineno, line in matches[:10]:  # 每文件最多 10 条
                # 高亮匹配部分
                highlighted = line
                file_results.append(f"  {lineno}: {highlighted}\n")
                total_matches += 1

            if len(matches) > 10:
                file_results.append(f"  ... and {len(matches) - 10} more matches\n")

        if total_matches == 0:
            return f"No matches found for '{pattern}' in {files_scanned} scanned files"

        # 截断（防止太长）
        result = "".join(file_results)
        if len(result) > 8000:
            result = result[:8000] + f"\n... [truncated, {total_matches} total matches]"

        hit_rate = f"{total_matches}/{files_scanned}" if files_scanned else "0"
        result += f"\n=== Stats: {total_matches} matches in {files_with_matches} files, scanned {files_scanned} files (hit rate {hit_rate}) ==="
        return result


class ListFilesTool(Tool):
    """Tool to list files in a directory"""

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "列出项目目录下的文件结构。"
            "适合了解项目布局或查找特定目录下的文件。"
        )

    @property
    def args_schema(self) -> dict:
        return {
            "path": "目录相对路径，默认为空（项目根目录）",
            "pattern": "可选，文件后缀过滤（如 .py）",
        }

    def execute(self, path: str = "", pattern: str = "") -> str:
        """Execute list_files"""
        if not path:
            search_root = PROJECT_ROOT
            display_path = "."
        else:
            try:
                target = (PROJECT_ROOT / path).resolve()
            except Exception:
                return f"Error: invalid path"

            # 安全检查
            if not str(target).startswith(str(PROJECT_ROOT)):
                return f"Error: path outside project"

            if not target.exists():
                return f"Error: directory not found: {path}"

            if not target.is_dir():
                return f"Error: not a directory: {path}"

            search_root = target
            display_path = path

        # 收集文件
        files: List[str] = []
        try:
            for item in sorted(search_root.iterdir()):
                rel = item.relative_to(search_root)
                if _match_exclude(item):
                    continue

                if item.is_dir():
                    files.append(f"  📁 {rel}/")
                else:
                    if pattern and not rel.suffix == pattern:
                        continue
                    size = item.stat().st_size
                    size_str = f"({size} bytes)" if size < 1024 else f"({size // 1024}KB)"
                    files.append(f"  📄 {rel} {size_str}")
        except PermissionError:
            return f"Error: permission denied"

        if not files:
            return f"No files found in {display_path}"

        result = f"=== Files in {display_path} ===\n\n"
        result += "\n".join(files[:100])  # 最多 100 个
        if len(files) > 100:
            result += f"\n... and {len(files) - 100} more"

        return result
