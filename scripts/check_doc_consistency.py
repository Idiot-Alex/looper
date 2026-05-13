#!/usr/bin/env python3
"""
文档 vs 代码一致性检查
校验 roadmap 中声明的工具在 registry 中都存在
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def check_tool_consistency():
    """检查 roadmap 中的工具名是否与代码 registry 一致"""
    from opc.tools import get_registry

    registry = get_registry()
    registered = set(registry.list_tools().keys())

    # 从 roadmap 中提取工具名
    doc_path = ROOT / "docs" / "looper_positioning_and_roadmap.md"
    content = doc_path.read_text(encoding="utf-8")

    # 匹配反引号包裹的单词，只检查工具类（不是系统概念）
    mentioned = set()
    for match in re.finditer(r'`([a-z_]+)`', content):
        word = match.group(1)
        # 只检查文件名/工具名这类，不检查系统概念
        tool_candidates = {
            "read_file", "edit_file", "search_code", "list_files",
            "get_file_tree",  # 历史别名，检查是否已修正
        }
        if word in tool_candidates:
            mentioned.add(word)

    # 对比
    missing = mentioned - registered
    extra = registered - mentioned

    print("=== 文档一致性检查 ===")
    print(f"Registry 中: {sorted(registered)}")
    print(f"文档中提到: {sorted(mentioned)}")
    print(f"文档提到但未注册: {sorted(missing) if missing else '无'}")
    print(f"已注册但文档未提: {sorted(extra) if extra else '无'}")

    if missing:
        print(f"\n⚠️  警告：文档提到以下工具但 registry 中不存在: {sorted(missing)}")
        return 1
    if extra:
        print(f"\n💡 提示：以下已注册工具未在文档中声明: {sorted(extra)}")
    print("\n✅ 一致性检查通过")
    return 0


def check_frozen_doc():
    """检查 frozen 文档是否已标注"""
    frozen = ROOT / "docs" / "stage2_next_phase_plan.md"
    content = frozen.read_text(encoding="utf-8")

    has_caveat = "历史冻结" in content or "以 positioning" in content
    print(f"\n=== Frozen 文档标注检查 ===")
    print(f"frozen 文档已标注: {'✅' if has_caveat else '❌ 缺失状态边界提示'}")
    return 0 if has_caveat else 1


if __name__ == "__main__":
    rc1 = check_tool_consistency()
    rc2 = check_frozen_doc()
    sys.exit(rc1 or rc2)
