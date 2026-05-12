"""
File Tools for OPC
read_file and edit_file implementations (Stage 2.5)
"""
import shutil
from pathlib import Path

from opc.config import PROJECT_ROOT, ALLOWED_WRITE_DIRS
from opc.tools import Tool


# Max file size to read (1MB)
MAX_READ_SIZE = 1024 * 1024

# Max lines to read (prevent context overflow)
MAX_READ_LINES = 3000


def _validate_path(path: str) -> Path:
    """
    Validate and resolve a path for security.
    Rejects absolute paths and path traversal.

    Returns:
        Resolved Path object

    Raises:
        ValueError: Path is invalid
    """
    import os

    if os.path.isabs(path):
        raise ValueError(f"Absolute paths not allowed: {path}")

    if ".." in path:
        raise ValueError(f"Path traversal not allowed: {path}")

    target = (PROJECT_ROOT / path).resolve()

    # Ensure within allowed dirs
    is_allowed = any(
        str(target).startswith(str(d)) for d in ALLOWED_WRITE_DIRS
    )
    if not is_allowed:
        raise ValueError(f"Path outside allowed directories: {path}")

    return target


class ReadFileTool(Tool):
    """Tool to read file contents"""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "读取文件内容。在修改文件前先用此工具查看现有代码结构。"
        )

    @property
    def args_schema(self) -> dict:
        return {
            "path": "文件相对路径，例如 src/index.js",
        }

    def execute(self, path: str) -> str:
        """Execute read_file"""
        try:
            target = _validate_path(path)
        except ValueError as e:
            return f"Error: {e}"

        # Check existence
        if not target.exists():
            return f"Error: File not found: {path}"

        if not target.is_file():
            return f"Error: Not a file: {path}"

        # Check size
        try:
            file_size = target.stat().st_size
        except OSError as e:
            return f"Error: Cannot stat {path}: {e}"

        if file_size > MAX_READ_SIZE:
            return (
                f"Error: File too large ({file_size} bytes). "
                f"Max: {MAX_READ_SIZE} bytes."
            )

        # Read content
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            return f"Error: File is not UTF-8 encoded: {path}"
        except Exception as e:
            return f"Error reading {path}: {e}"

        if len(lines) > MAX_READ_LINES:
            truncated = lines[:MAX_READ_LINES]
            truncated.append(
                f"... [TRUNCATED: {len(lines) - MAX_READ_LINES} more lines]"
            )
            content = "\n".join(truncated)
        else:
            content = "\n".join(lines)

        return (
            f"=== {path} ({len(lines)} lines) ===\n"
            f"{content}\n"
            f"=== END OF {path} ==="
        )


class EditFileTool(Tool):
    """Tool to edit a specific section of a file"""

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "编辑文件中指定内容。用 read_file 先查看文件后再使用。"
            "old_string 必须是文件中完全匹配的文本，只替换第一处出现的位置。"
        )

    @property
    def args_schema(self) -> dict:
        return {
            "path": "文件相对路径",
            "old_string": "要替换的原文（必须完全匹配，包括空格和缩进）",
            "new_string": "替换后的新内容",
        }

    def execute(self, path: str, old_string: str, new_string: str) -> str:
        """Execute edit_file"""
        # Validate path
        try:
            target = _validate_path(path)
        except ValueError as e:
            return f"Error: {e}"

        # Check existence
        if not target.exists():
            return f"Error: File not found: {path}"

        # Read current content
        try:
            content = target.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading {path}: {e}"

        # Check if old_string exists
        if old_string not in content:
            # Provide helpful error with surrounding context
            return (
                f"Error: old_string not found in {path}.\n"
                f"Make sure to use exact text from the file "
                f"(check for spaces/indentation differences).\n"
                f"Expected substring of length {len(old_string)}."
            )

        # Perform replacement (first occurrence only)
        new_content = content.replace(old_string, new_string, 1)

        # Write back
        try:
            # Backup
            backup_path = target.with_suffix(target.suffix + ".bak")
            shutil.copy2(target, backup_path)

            target.write_text(new_content, encoding="utf-8")

            return (
                f"✅ Successfully edited {path}\n"
                f"Backup: {backup_path.name}\n\n"
                f"=== EDITED CONTENT ===\n"
                f"{new_string}\n"
                f"=== END ==="
            )
        except Exception as e:
            return f"Error writing {path}: {e}"
