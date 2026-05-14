#!/bin/bash
# OPC Demo 录制脚本
# 用法: ./scripts/record_demo.sh
# 输出: docs/demo.gif (逐字打字机动画)
set -e

DEMO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_LOG="/tmp/opc_demo_output.txt"
GIF_OUT="$DEMO_DIR/docs/demo.gif"
PYTHON="python3"

cd "$DEMO_DIR"

echo "🎬 OPC Demo 录制脚本"
echo "   任务: 实现斐波那契数列计算脚本"
echo "   GIF 输出: $GIF_OUT"

# 1. 写 demo 任务
TASK="实现一个 Python 脚本 fib.py，计算斐波那契数列第 N 项，从命令行参数读取 N"
echo "$TASK" > opc/tasks/inbox/demo.md

# 2. 跑 OPC 并捕获输出
echo "🤖 正在运行 OPC..."
$PYTHON -m opc.main > "$OUTPUT_LOG" 2>&1

# 3. 用 output_to_gif.py 生成 GIF
echo "🎞️  生成 GIF..."
$PYTHON "$DEMO_DIR/scripts/output_to_gif.py" --input "$OUTPUT_LOG" --output "$GIF_OUT"

# 清理
rm -f "$OUTPUT_LOG"

echo "✅ Demo GIF 已生成: $GIF_OUT"
ls -lh "$GIF_OUT"
