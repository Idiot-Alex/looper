#!/bin/bash
# OPC Demo 录制脚本
# 用法: ./scripts/record_demo.sh
# 需要: asciinema (pip3 install asciinema), ffmpeg
set -e

export PATH="$PATH:/Users/hotstrip/Library/Python/3.9/bin"

DEMO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REC_FILE="$DEMO_DIR/opc/logs/demo.cast"
GIF_FILE="$DEMO_DIR/docs/demo.gif"
TIMEOUT=180

cd "$DEMO_DIR"

echo "🎬 开始录制 OPC Demo (超时 ${TIMEOUT}s)..."
echo "   录制文件: $REC_FILE"
echo "   GIF 输出: $GIF_FILE"

# 准备 demo 任务
echo "实现一个 Python 脚本 fib.py，计算斐波那契数列第 N 项，从命令行参数读取 N" > opc/tasks/inbox/demo_recording.md

# 录一个完整的 shell session，里面跑 OPC
# -w: 空闲超时, -t: 录制标题
asciinema rec "$REC_FILE" \
    --title "OPC Demo: AI 代码工厂 90秒演示" \
    --command "cd $DEMO_DIR && uv run python -m opc.main 2>&1" \
    -i "$TIMEOUT"

# 检查录制是否成功
if [ ! -f "$REC_FILE" ] || [ ! -s "$REC_FILE" ]; then
    echo "❌ 录制失败，文件为空"
    exit 1
fi

SIZE=$(wc -c < "$REC_FILE")
echo ""
echo "✅ 录制完成 (${SIZE} bytes)"
echo "   播放: asciinema play $REC_FILE"
echo ""

# 尝试转 GIF
echo "🎞️  转换为 GIF..."

# 检查 ffmpeg 是否有 libass（字幕支持 = sub2video 支持）
if ffmpeg -version 2>&1 | grep -q "libass"; then
    echo "   ffmpeg 有 libass，开始转换（这可能需要几分钟）..."

    ffmpeg -y -i "$REC_FILE" \
        -vf "sub2video=1:24:80,scale=960:-1:flags=lanczos" \
        -r 10 \
        -g 30 \
        -codec:v gif \
        "$GIF_FILE" 2>&1 | grep -E "error|Error|frame=|error" | head -5 || true
fi

# 如果上面的方法失败，用备选：直接从 cast 提取帧转 GIF
if [ ! -f "$GIF_FILE" ] || [ ! -s "$GIF_FILE" ]; then
    echo "   备选方案：生成帧序列..."
    mkdir -p /tmp/opc_frames

    python3 << 'PYTHON'
import json, sys, base64, zlib, os
from pathlib import Path

cast_file = Path("$REC_FILE")
out_dir = Path("/tmp/opc_frames")
out_dir.mkdir(exist_ok=True)

with open(cast_file) as f:
    cast = json.load(f)

fps = 10
frame_duration = 1.0 / fps
cols, rows = 80, 24

# ANSI 颜色解析
def ansi_to_html(text, width=80, height=24):
    """简单渲染：保留换行，空格渲染为方块"""
    lines = text.split('\n')
    html_lines = []
    for line in lines[-height:]:
        # 截断到宽度
        line = line[:width]
        # 转义 HTML
        line = line.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
        # 空格替换为半角方块
        line = line.replace(' ', '&#160;')
        html_lines.append(line)

    # 补满高度
    while len(html_lines) < height:
        html_lines.append('&#160;' * width)

    bg = '#1e1e2e'
    fg = '#cdd6f4'
    html = f'''<!DOCTYPE html>
<html><head>
<style>body{{background:{bg};color:{fg};font:14px monospace;padding:10px;white-space:pre;}}</style>
</head><body>{chr(10).join(html_lines)}</body></html>'''

    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('RGB', (cols * 8, rows * 16), bg)
        draw = ImageDraw.Draw(img)
        for i, line in enumerate(html_lines):
            draw.text((0, i * 16), line, fill=fg)
        return img
    except ImportError:
        return None

# 渲染帧
try:
    from PIL import Image, ImageDraw
    frames = []
    frame_idx = 0
    text_buf = ""

    for _, _, text in cast[1:]:  # skip header
        if text:
            text_buf += text
            # 每积累一定字符或换行，渲染一帧
            if '\n' in text_buf or len(text_buf) > 200:
                img = ansi_to_html(text_buf)
                if img:
                    frames.append(img)
                text_buf = ""
                frame_idx += 1
                if frame_idx > 50:  # 最多 50 帧 GIF
                    break

    if frames:
        frames[0].save(
            "$GIF_FILE",
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0
        )
        print(f"✅ GIF 生成: {len(frames)} 帧")
    else:
        print("⚠️ 未能生成帧")
except ImportError:
    print("⚠️ Pillow 未安装，无法生成 GIF")
    print("   录制文件已保存，运行以下命令手动转换：")
    print("   pip3 install pillow && ./scripts/record_demo.sh")
PYTHON
fi

if [ -f "$GIF_FILE" ] && [ -s "$GIF_FILE" ]; then
    echo "✅ GIF 生成成功!"
    ls -lh "$GIF_FILE"
else
    echo "⚠️ GIF 生成失败"
    echo "   录制文件已就绪: $REC_FILE"
    echo "   稍后手动转换或上传 asciinema.org"
fi
