#!/usr/bin/env python3
"""将 OPC 的 ANSI 彩色输出转换为动画 GIF"""
import re
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

INPUT = Path("/tmp/opc_output.txt")
OUTPUT = Path("/Users/hotstrip/Developer/looper/docs/demo.gif")

import argparse
parser = argparse.ArgumentParser(description="OPC 输出 → 动画 GIF")
parser.add_argument("--input", type=str, help="输入文本文件")
parser.add_argument("--output", type=str, help="输出 GIF 文件")
args = parser.parse_args()
if args.input:
    INPUT = Path(args.input)
if args.output:
    OUTPUT = Path(args.output)

# ANSI 颜色 → RGB
ANSI_COLORS = {
    30: (0, 0, 0),       # 黑
    31: (205, 54, 54),   # 红
    32: (46, 160, 46),   # 绿
    33: (238, 200, 74),  # 黄
    34: (88, 166, 255),  # 蓝
    35: (189, 74, 164),  # 紫
    36: (20, 189, 188),  # 青
    37: (240, 240, 240), # 白
    90: (120, 120, 120), # 亮黑
    91: (255, 95, 87),   # 亮红
    92: (84, 220, 80),   # 亮绿
    93: (245, 238, 100), # 亮黄
    94: (86, 185, 255),  # 亮蓝
    95: (200, 100, 200), # 亮紫
    96: (28, 225, 228),  # 亮青
    97: (255, 255, 255), # 亮白
}

BG = (30, 30, 46)         # 深色背景
FG = (205, 208, 220)     # 主文字色
ACCENT = (137, 221, 255) # 强调色（蓝）
GREEN = (46, 220, 100)    # 成功绿
YELLOW = (255, 211, 81)   # 警告黄
RED = (255, 97, 117)      # 错误红

COLS = 80
ROWS = 25
CHAR_W = 9
CHAR_H = 18
PAD_X = 16
PAD_Y = 16
MARGIN = 8
IMG_W = PAD_X * 2 + COLS * CHAR_W + MARGIN * 2
IMG_H = PAD_Y * 2 + ROWS * CHAR_H + MARGIN * 2 + 40  # 40 for title bar

# 加载等宽字体
def load_font():
    paths = [
        "/System/Library/Fonts/Monaco.ttf",
        "/System/Library/Fonts/SF Mono.ttf",
        "/Library/Fonts/Courier New.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, 14)
        except:
            pass
    return ImageFont.load_default()

FONT = load_font()

def parse_ansi(text):
    """解析 ANSI 转义序列，返回 (text, fg_color, bg_color) 片段列表"""
    fg = FG
    bg = None
    result = []

    # ANSI SGR (Select Graphic Rendition) 模式
    # 格式: \x1b[...m
    ansi_re = re.compile(r'\x1b\[([0-9;]*)m')

    pos = 0
    while pos < len(text):
        m = ansi_re.search(text, pos)
        if not m:
            # 剩余全部
            chunk = text[pos:]
            if chunk:
                result.append((chunk, fg, bg))
            break

        # 添加 ANSI 前的纯文本
        if m.start() > pos:
            result.append((text[pos:m.start()], fg, bg))

        # 处理 ANSI 码
        codes = m.group(1)
        if codes == '0' or codes == '':
            fg = FG
            bg = None
        else:
            for code in codes.split(';'):
                code = int(code) if code else 0
                if code == 0:
                    fg = FG
                    bg = None
                elif code == 1:
                    fg = brighten(fg)
                elif 30 <= code <= 37:
                    fg = ANSI_COLORS.get(code, FG)
                elif 90 <= code <= 97:
                    fg = ANSI_COLORS.get(code, FG)

        pos = m.end()

    return result

def brighten(color):
    """变亮颜色"""
    r, g, b = color
    return (min(255, r+40), min(255, g+40), min(255, b+40))

def render_frame(text_lines, title="", title_color=ACCENT):
    """渲染一帧终端画面"""
    img = Image.new('RGB', (IMG_W, IMG_H), BG)
    draw = ImageDraw.Draw(img)

    # 标题栏
    draw.rectangle([0, 0, IMG_W-1, 28], fill=(50, 50, 70))
    if title:
        draw.text((PAD_X, 7), title, font=FONT, fill=title_color)
    draw.text((IMG_W - PAD_X - 100, 7), "OPC Demo", font=FONT, fill=(100, 100, 120))

    # 终端窗口
    win_y = 30
    draw.rectangle([MARGIN, win_y, IMG_W - MARGIN - 1, IMG_H - MARGIN - 1],
                   fill=(30, 30, 46), outline=(60, 60, 80), width=1)

    # 渲染文字行
    for row, line in enumerate(text_lines[-ROWS:]):
        # 补足宽度
        line = line[:COLS].ljust(COLS)
        y = win_y + MARGIN + 2 + row * CHAR_H

        # 解析 ANSI 并渲染
        segments = parse_ansi(line)
        x = win_y + MARGIN + 2
        for text, fg_color, _ in segments:
            if text:
                draw.text((x, y), text, font=FONT, fill=fg_color)
                x += FONT.getlength(text)

    return img

def simulate_typewriter(full_text, fps=15, chars_per_frame=3):
    """模拟逐字输出动画"""
    frames = []
    total = len(full_text)

    # 进度条百分比
    for i in range(0, total, chars_per_frame):
        progress = min(1.0, i / total)
        prefix = full_text[:i]

        # 提取行
        lines = prefix.split('\n')
        # 每行最多 COLS 字符
        trimmed = [ln[:COLS] for ln in lines]

        img = render_frame(trimmed, f"OPC Demo — {int(progress*100)}%")
        frames.append(img)

        if len(frames) > 200:  # 最多 200 帧
            break

    return frames

def main():
    if not INPUT.exists():
        print(f"❌ 输入文件不存在: {INPUT}")
        return

    with open(INPUT) as f:
        text = f.read()

    print(f"📄 读取输出 ({len(text)} chars, {len(text.split(chr(10)))} lines)")

    # 生成打字机动画
    print("🎞️  生成动画帧...")
    frames = simulate_typewriter(text, fps=15, chars_per_frame=2)
    print(f"   {len(frames)} 帧")

    if not frames:
        print("❌ 没有生成帧")
        return

    # 保存 GIF
    print(f"💾 保存 GIF → {OUTPUT}")
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=80,  # 每帧 80ms ≈ 12fps
        loop=0,
        optimize=False,
    )

    size_kb = OUTPUT.stat().st_size // 1024
    print(f"✅ GIF 生成完成: {size_kb}KB, {len(frames)} 帧")

if __name__ == "__main__":
    main()
