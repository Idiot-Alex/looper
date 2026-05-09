"""
OPC 安全文件写入
路径校验 + 备份 + 目录创建
"""
import os
import shutil
from pathlib import Path
from typing import List

from opc.config import PROJECT_ROOT, ALLOWED_WRITE_DIRS


class SafeWriterError(Exception):
    """安全写入异常"""
    pass


def validate_path(project_root: Path, relative_path: str) -> Path:
    """
    校验路径安全性
    
    规则：
    1. 拒绝绝对路径
    2. 拒绝 ../ 路径穿越
    3. 拒绝隐藏目录（.env, .ssh 等）
    
    Args:
        project_root: 项目根目录
        relative_path: 相对路径
    
    Returns:
        解析后的绝对路径
    
    Raises:
        SafeWriterError: 路径不安全
    """
    # 拒绝绝对路径
    if os.path.isabs(relative_path):
        raise SafeWriterError(f"拒绝绝对路径: {relative_path}")
    
    # 禁止 ..
    if ".." in relative_path:
        raise SafeWriterError(f"拒绝路径穿越: {relative_path}")
    
    # 构建目标路径
    target = (project_root / relative_path).resolve()
    
    # 检查是否在允许的目录内
    is_allowed = False
    for allowed_dir in ALLOWED_WRITE_DIRS:
        if str(target).startswith(str(allowed_dir)):
            is_allowed = True
            break
    
    if not is_allowed:
        raise SafeWriterError(f"路径越界: {relative_path}")
    
    # 拒绝隐藏路径（隐藏目录下的文件）
    for part in target.parts:
        if part.startswith(".") and part not in [".git", ".alma", ".github"]:
            raise SafeWriterError(f"拒绝隐藏路径: {relative_path}")
    
    return target


def backup_file(target: Path) -> None:
    """备份已存在的文件"""
    if target.exists():
        backup_path = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, backup_path)


def write_file(project_root: Path, relative_path: str, content: str) -> None:
    """
    安全写入文件
    
    Args:
        project_root: 项目根目录
        relative_path: 相对路径
        content: 文件内容
    
    Raises:
        SafeWriterError: 写入失败
    """
    target = validate_path(project_root, relative_path)
    
    # 备份旧文件
    backup_file(target)
    
    # 创建父目录
    target.parent.mkdir(parents=True, exist_ok=True)
    
    # 写入文件
    try:
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        raise SafeWriterError(f"写入失败 {relative_path}: {e}")


def write_files(project_root: Path, files: List[dict]) -> List[str]:
    """
    批量安全写入文件
    
    Args:
        project_root: 项目根目录
        files: 文件列表 [{"path": "...", "content": "..."}]
    
    Returns:
        写入的文件路径列表
    """
    written = []
    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")
        write_file(project_root, path, content)
        written.append(path)
    return written
