#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用真实专辑封面拼贴生成 A5 歌词本封面（错落堆叠、铺满、标题留白）。

用法:
  python3 make_cover.py covers_dir/ -o 封面.png --title "cosinX 的歌词乐理本" [--subtitle "MY LYRICS · 208 SONGS"]

covers_dir 下放正方形专辑封面图（jpg/png，建议 ≥500px）。
输出: A5 比例 1240×1754px（148×210mm @216dpi），PNG。
"""
import argparse, glob, math, os, random, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

A5_W, A5_H = 1240, 1754          # 148×210mm @216dpi
TITLE_H = 300                    # 顶部标题留白区
GAP = 14                         # 拼贴间隙（小，制造堆叠感）
ROT_RANGE = (-8, 8)              # 随机旋转角度

# Pillow 10+ 兼容（旧版回退）
try:
    RESAMPLE = Image.Resampling.LANCZOS
    ROTATE = Image.Resampling.BICUBIC
except AttributeError:
    RESAMPLE = Image.LANCZOS
    ROTATE = Image.BICUBIC


def load_font(size, bold=False):
    """跨平台字体探测：macOS / Windows / Linux 依次尝试，找不到回退默认字体。"""
    if sys.platform == 'darwin':
        candidates = (
            [('/System/Library/Fonts/STHeiti Medium.ttc', 0)] if bold else
            [('/System/Library/Fonts/STHeiti Light.ttc', 0), ('/System/Library/Fonts/STHeiti Medium.ttc', 0)]
        )
        candidates += [
            ('/System/Library/Fonts/PingFang.ttc', 1 if bold else 0),
            ('/Library/Fonts/Arial Unicode.ttf', 0),
            ('/System/Library/Fonts/Supplemental/Arial Unicode.ttf', 0),
        ]
    elif sys.platform in ('win32', 'cygwin'):
        candidates = [
            (r'C:\Windows\Fonts\msyh.ttc', 1 if bold else 0),       # 微软雅黑
            (r'C:\Windows\Fonts\msyhbd.ttc', 0),                      # 微软雅黑粗体
            (r'C:\Windows\Fonts\simhei.ttf', 0),                      # 黑体
            (r'C:\Windows\Fonts\simsun.ttc', 0),                      # 宋体
        ]
    else:  # Linux / other
        candidates = [
            ('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', 0) if bold else
            ('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 0),
            ('/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc', 0),
            ('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', 0),
            ('/usr/share/fonts/truetype/wqy/wqy-microhei.ttc', 0),
        ]
    for path, index in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size, index=index)
            except Exception:
                continue
    # 最后回退：扫描常见字体目录找任意 CJK 字体
    for scan_dir in ('/usr/share/fonts', '/usr/local/share/fonts', os.path.expanduser('~/.fonts')):
        if os.path.isdir(scan_dir):
            for root, _, files in os.walk(scan_dir):
                for f in files:
                    if f.lower().endswith(('.ttf', '.ttc', '.otf')) and any(
                        k in f.lower() for k in ('cjk', 'noto', 'wqy', 'hei', 'song', 'ming', 'yahei', 'pingfang', 'stheiti')):
                        try:
                            return ImageFont.truetype(os.path.join(root, f), size)
                        except Exception:
                            continue
    return ImageFont.load_default()


def collage(covers, out_path, title, subtitle=''):
    random.seed(42)
    canvas = Image.new('RGB', (A5_W, A5_H), (18, 18, 22))
    draw = ImageDraw.Draw(canvas)

    # 标题区渐变
    for y in range(TITLE_H):
        k = y / TITLE_H
        color = (int(18 + 30 * k), int(18 + 24 * k), int(22 + 30 * k))
        draw.line([(0, y), (A5_W, y)], fill=color)

    # 标题（粗体）
    if title:
        font = load_font(92, bold=True)
        bbox = draw.textbbox((0, 0), title, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((A5_W - tw) / 2, 70), title, font=font, fill=(255, 255, 255))
        if subtitle:
            font2 = load_font(34)
            bbox2 = draw.textbbox((0, 0), subtitle, font=font2)
            tw2 = bbox2[2] - bbox2[0]
            draw.text(((A5_W - tw2) / 2, 190), subtitle, font=font2, fill=(180, 180, 185))

    # 错落布局：奇数行右移半个格宽、随机上下错位，制造堆叠而非整齐网格
    area_h = A5_H - TITLE_H - 60
    cols = 4
    cell_w = (A5_W - (cols + 1) * GAP) / cols
    cell_h = cell_w * 1.02
    rows = math.ceil(area_h / cell_h)
    images = [Image.open(c).convert('RGB') for c in covers]
    random.shuffle(images)

    idx = 0
    for r in range(rows):
        for c in range(cols):
            if idx >= len(images):
                break
            img = images[idx]
            idx += 1
            img = img.resize((int(cell_w * 0.9), int(cell_w * 0.9)), RESAMPLE)
            # 奇数行整体右移半格（交错），再加随机偏移
            x = GAP + c * (cell_w + GAP) + (cell_w * 0.5 if r % 2 else 0) + random.uniform(-14, 14)
            y = TITLE_H + 30 + r * cell_h + random.uniform(-10, 10)
            rot = random.uniform(*ROT_RANGE)
            img = img.rotate(rot, expand=True, resample=ROTATE)
            # 柔和投影阴影（高斯模糊）
            shadow = Image.new('RGBA', (img.width + 16, img.height + 16), (0, 0, 0, 0))
            sd = ImageDraw.Draw(shadow)
            sd.rectangle([8, 12, 8 + img.width, 12 + img.height], fill=(0, 0, 0, 150))
            shadow = shadow.filter(ImageFilter.GaussianBlur(7))
            canvas.paste(shadow, (int(x - 8), int(y - 6)), shadow)
            canvas.paste(img, (int(x), int(y)))
        if idx >= len(images):
            break

    canvas.save(out_path, 'PNG')
    print(f'封面已保存: {out_path}  ({idx} 张专辑, {cols}列 {rows}行错落拼贴)')


def _aspect(path):
    try:
        with Image.open(path) as im:
            w, h = im.size
            return w / h if h else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description='专辑封面拼贴生成A5歌词本封面')
    ap.add_argument('covers_dir', help='专辑封面图片目录')
    ap.add_argument('-o', '--out', default='封面.png')
    ap.add_argument('--title', default='我的歌词乐理本')
    ap.add_argument('--subtitle', default='')
    args = ap.parse_args()

    exts = ('*.jpg', '*.jpeg', '*.png', '*.webp')
    covers = []
    for e in exts:
        covers.extend(glob.glob(os.path.join(args.covers_dir, e)))
    # 预计算宽高比，过滤打不开/损坏的图，避免 sort 时崩溃
    rated = []
    for p in covers:
        ar = _aspect(p)
        if ar is None:
            print(f'  跳过损坏/无法打开的图: {os.path.basename(p)}', file=sys.stderr)
            continue
        rated.append((abs(ar - 1.0), p))
    rated.sort(key=lambda x: x[0])   # 优先正方形
    covers = [p for _, p in rated][:24]
    if not covers:
        print('没有可用的专辑封面图片', file=sys.stderr)
        sys.exit(1)
    collage(covers, args.out, args.title, args.subtitle)


if __name__ == '__main__':
    main()
