#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从歌词 JSON 生成可打印歌词本 DOCX。

输入格式（songs.json）:
[
  {"name": "冻结", "artist": "林俊杰", "lyrics": ["行1", "行2", ...]},
  ...
]

用法:
  python3 build_lyrics_book.py songs.json -o 歌词本.docx [--title "cosinX 的歌词乐理本"] [--size a5|b5|a4]
  可选: --keep-dups（不去重） --keep-full（不自动精简超长歌） --no-chorus-mark（不标副歌重复）
"""
import argparse, json, os, re, sys
from docx import Document
from docx.shared import Pt, Mm, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

PAGE_SIZES = {
    'a5': (148, 210),
    'b5': (176, 250),
    'a4': (210, 297),
}

# ---------- 歌词清洗 ----------
TAG_RE = re.compile(r'^(源|凯|玺|源凯|凯玺|源玺|凯玺源|源凯玺|源玺凯|合|合唱|男|女|男女|全体|全员|rap|Rap|RAP|bridge|Bridge|BRIDGE|Chorus|CHORUS|副歌|主歌|前奏|间奏|尾奏|独白|对白|念白|说|唱|和音|和声|伴唱|王源|王俊凯|易烊千玺|TFBOYS|TFboys|tfboy)\s*[：:]\s*$')

# 纯语气词/叹词行（整行只有这些），超长歌精简时可删
FILLER_RE = re.compile(r'^(唉|哎|喔|哦|嗯|啊|呀|呐|嗷|嘿|嗨|woo|yeah|ya|no|hey|la|na|oh|ah|ha|~|…|\.)+$', re.IGNORECASE)


def clean_tag_lines(lines):
    """删除单独成行的分唱标记（源：/凯：/合：/男：等）。"""
    return [l for l in lines if not TAG_RE.match(l.strip())]


def normalize(l):
    """去除语气词、叹词、标点后比较。"""
    l = re.sub(r'^(唉|哎|喔|哦|嗯|啊|呀|呐|嗷|嘿|嗨|woo|yeah|no|hey|la|na)+', '', l, flags=re.IGNORECASE)
    l = re.sub(r'(唉|哎|喔|哦|嗯|啊|呀|呐|嗷|嘿|嗨|woo|yeah|no|hey|la|na)+$', '', l, flags=re.IGNORECASE)
    l = re.sub(r'[，。！？、,.!?\s]', '', l)
    return l


def normalize_name(name):
    """歌名归一化：去空格、标点、版本后缀，小写。"""
    n = re.sub(r'[-—–（(].*?[)）]\s*$', '', name)  # 去尾部(电视剧主题曲)等
    n = re.sub(r'[\s，。！？、,.!?:：·]', '', n)
    return n.lower().strip()


def normalize_artist(artist):
    """歌手归一化：取第一个歌手，去空格、统一分隔符，小写。"""
    if not artist:
        return ''
    # 按常见分隔符切，取第一个
    first = re.split(r'[/、,，&和\s]+', artist.strip())[0]
    first = re.sub(r'[\s]', '', first)
    return first.lower().strip()


def dedup_songs(songs):
    """按归一化歌名+第一个歌手去重，保留第一个出现的版本。"""
    seen = set()
    out = []
    dup_count = 0
    for s in songs:
        key = (normalize_name(s.get('name', '')), normalize_artist(s.get('artist', '')))
        if key in seen:
            dup_count += 1
            continue
        seen.add(key)
        out.append(s)
    return out, dup_count


def aggressive_dedup(lines, min_block=4, max_block=12, chorus_mark=True):
    """块级去重：完全相同（或仅语气词差异）的连续 4-12 行块只保留第一遍。

    返回 (lines, removed_count)。chorus_mark=True 时在被删重复块位置插入(副歌×N)标记。
    """
    lines = [l.strip() for l in lines if l.strip()]
    if not lines:
        return lines, 0
    seen = {}
    out = []
    removed = 0
    i, n = 0, len(lines)
    while i < n:
        hit = False
        for L in range(min(max_block, n - i), min_block - 1, -1):
            block = tuple(normalize(lines[j]) for j in range(i, i + L))
            if not any(b for b in block):
                continue
            key = block
            if key in seen:
                orig_block = tuple(lines[j] for j in range(i, i + L))
                prev_block = seen[key]
                if orig_block == prev_block:
                    removed += L
                    if chorus_mark:
                        out.append(f'（副歌 ×2）')
                    i += L
                    hit = True
                    break
                substantive_diff = sum(
                    1 for a, b in zip(orig_block, prev_block)
                    if a != b and normalize(a) != normalize(b)
                )
                if substantive_diff <= L // 3:
                    removed += L
                    if chorus_mark:
                        out.append(f'（副歌 ×2）')
                    i += L
                    hit = True
                    break
        if hit:
            continue
        for L in range(min_block, min(max_block + 1, n - i + 1)):
            block = tuple(normalize(lines[j]) for j in range(i, i + L))
            if any(b for b in block):
                seen[block] = tuple(lines[j] for j in range(i, i + L))
        out.append(lines[i])
        i += 1
    return out, removed


def auto_truncate(lines, max_lines=62):
    """超长歌自动精简：删纯语气词行 → 去尾部重复 → 截断到核心段落加……。

    返回 (lines, was_truncated)。
    """
    if len(lines) <= max_lines:
        return lines, False
    # 1. 删纯语气词行
    filtered = [l for l in lines if not FILLER_RE.match(l.strip())]
    if len(filtered) <= max_lines:
        return filtered, True
    # 2. 截断到 max_lines，保留前 max_lines-1 行 + "……"
    truncated = filtered[:max_lines - 1] + ['……']
    return truncated, True


# ---------- 字号自适应 ----------
def pick_font(n_lines):
    """按行数选择(字号pt, 行距pt)，确保一首歌完整落在 A5 一栏内（约 538pt 可用高度）。"""
    if n_lines <= 38:
        return 8.5, 11.5
    if n_lines <= 46:
        return 7.5, 10.0
    if n_lines <= 52:
        return 7.0, 9.5
    if n_lines <= 58:
        return 6.5, 8.5
    return 6.0, 7.5


# ---------- DOCX 生成 ----------
COL_AVAIL_PT = 538.6
MAX_LINES = 62  # 超过此行数自动精简


def set_cn(run, east):
    rpr = run._element.get_or_add_rPr()
    rf = rpr.get_or_add_rFonts()
    rf.set(qn('w:eastAsia'), east)
    rf.set(qn('w:ascii'), east)
    rf.set(qn('w:hAnsi'), east)


def setup_page(sec, size_key, two_col=False, margin_mm=10):
    w, h = PAGE_SIZES[size_key]
    sec.page_width, sec.page_height = Mm(w), Mm(h)
    sec.left_margin = sec.right_margin = Mm(margin_mm)
    sec.top_margin, sec.bottom_margin = Mm(margin_mm), Mm(margin_mm)
    if two_col:
        c = sec._sectPr.xpath('./w:cols')[0]
        c.set(qn('w:num'), '2')
        c.set(qn('w:space'), '300')


def column_break_run(p):
    r = p.add_run()
    br = OxmlElement('w:br')
    br.set(qn('w:type'), 'column')
    r._r.append(br)


def set_cell_width(cell, width_mm):
    """固定单元格宽度。"""
    cell.width = Mm(width_mm)
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcW = tcPr.find(qn('w:tcW'))
    if tcW is None:
        tcW = OxmlElement('w:tcW')
        tcPr.append(tcW)
    tcW.set(qn('w:w'), str(int(width_mm * 56.7)))  # mm to twips
    tcW.set(qn('w:type'), 'dxa')


def build(songs, out_path, title='我的歌词乐理本', size='a5',
          keep_dups=False, keep_full=False, chorus_mark=True):
    # 1. 歌手归一化去重
    songs, dup_count = dedup_songs(songs)
    if dup_count:
        print(f'去重: 移除 {dup_count} 首重复歌曲（按归一化歌名+首歌手）', file=sys.stderr)

    # 2. 清洗 + 去重；空歌词歌跳过
    total_removed = 0
    skipped = []
    kept = []
    truncated_songs = []
    for s in songs:
        orig = [l for l in (s.get('lyrics') or []) if l.strip()]
        orig = clean_tag_lines(orig)
        if not orig:
            skipped.append(s)
            continue
        if not keep_dups:
            new, removed = aggressive_dedup(orig, chorus_mark=chorus_mark)
            total_removed += removed
        else:
            new = orig
        # 3. 超长歌自动精简
        if not keep_full:
            new, was_trunc = auto_truncate(new, MAX_LINES)
            if was_trunc:
                truncated_songs.append(f"{s.get('name')}({s.get('artist','')})")
        s['lyrics'] = new
        kept.append(s)
    if skipped:
        print(f'警告: {len(skipped)} 首歌歌词为空，已跳过: '
              + ', '.join(f"{s.get('name')}({s.get('artist','')})" for s in skipped), file=sys.stderr)
    if truncated_songs:
        print(f'自动精简: {len(truncated_songs)} 首超长歌已精简到≤{MAX_LINES}行: '
              + ', '.join(truncated_songs[:10]) + ('...' if len(truncated_songs) > 10 else ''), file=sys.stderr)
    songs = kept

    # 4. 超长歌校验（keep_full 模式下才警告，否则已自动精简）
    if keep_full:
        for s in songs:
            n = len([l for l in s.get('lyrics', []) if l.strip()])
            body_size, body_leading = pick_font(n)
            est = n * body_leading + body_leading + 14
            if est > COL_AVAIL_PT:
                print(f'警告: 《{s.get("name")}》{n}行 估算高{est:.0f}pt>可用{COL_AVAIL_PT}pt，'
                      f'打印会跨栏，需人工精简', file=sys.stderr)

    doc = Document()

    # 标题页
    sec0 = doc.sections[0]
    setup_page(sec0, size)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(60)
    r = p.add_run(title)
    r.font.size = Pt(22); r.font.bold = True; r.font.name = 'Arial'
    set_cn(r, '黑体')

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    r = p.add_run(f'共 {len(songs)} 首  ·  MY LYRICS')
    r.font.size = Pt(11); r.font.name = 'Arial'; set_cn(r, '宋体')
    r.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

    # 目录页（两列无边框表格，序号固定宽度对齐）
    doc.add_page_break()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run('目  录')
    r.font.size = Pt(14); r.font.bold = True; r.font.name = 'Arial'; set_cn(r, '黑体')

    # 序号格式化：固定宽度，3位数右对齐 + 点 + 空格
    def fmt_entry(i, s):
        num = f"{i+1:>3}."
        name = s['name']
        artist = s.get('artist', '')
        if artist:
            return f"{num} {name}  {artist}"
        return f"{num} {name}"

    entries = [fmt_entry(i, s) for i, s in enumerate(songs)]
    rows = (len(entries) + 1) // 2
    table = doc.add_table(rows=rows, cols=2)
    table.autofit = False

    # 固定列宽（A5可用宽度128mm，每列约62mm，留间距）
    col_w = 62 if size == 'a5' else (78 if size == 'b5' else 92)
    for row in table.rows:
        for cell in row.cells:
            set_cell_width(cell, col_w)

    # 无边框
    tblPr = table._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement('w:' + edge)
        el.set(qn('w:val'), 'nil')
        borders.append(el)
    tblPr.append(borders)

    def fill_cell(cell, text):
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.line_spacing = Pt(9)
        r = p.add_run(text)
        r.font.size = Pt(7); r.font.name = 'Arial'; set_cn(r, '黑体')

    for i in range(rows):
        if i < len(entries):
            fill_cell(table.cell(i, 0), entries[i])
        if i + rows < len(entries):
            fill_cell(table.cell(i, 1), entries[i + rows])

    # 正文：两栏，每首歌前面插分栏符 + keep_together，保证一栏一首、绝不串栏跨页
    body = doc.add_section(WD_SECTION.NEW_PAGE)
    setup_page(body, size, two_col=True)

    for idx, s in enumerate(songs):
        name = s['name']
        artist = s.get('artist', '')
        lyrics = [l for l in (s.get('lyrics') or []) if l.strip()]
        body_size, body_leading = pick_font(len(lyrics))
        title_size = max(body_size + 1.5, 7)

        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.keep_together = True
        pf.keep_with_next = True
        pf.space_before = Pt(4 if idx > 0 else 0)
        pf.space_after = Pt(1)
        pf.line_spacing = Pt(max(body_leading, title_size + 2))
        if idx > 0:
            column_break_run(p)
        r = p.add_run(f"{idx+1}. {name}")
        r.font.size = Pt(title_size)
        r.font.bold = True
        r.font.name = 'Heiti TC'
        set_cn(r, '黑体')

        if artist:
            pa = doc.add_paragraph()
            pfa = pa.paragraph_format
            pfa.keep_together = True
            pfa.keep_with_next = True
            pfa.space_before = Pt(0)
            pfa.space_after = Pt(2)
            pfa.line_spacing = Pt(body_leading)
            ra = pa.add_run(artist)
            ra.font.size = Pt(max(body_size - 1.5, 6.0))
            ra.font.color.rgb = RGBColor(0x8a, 0x8a, 0x8a)
            ra.font.name = 'Heiti TC'
            set_cn(ra, '黑体')

        for i, line in enumerate(lyrics):
            pl = doc.add_paragraph()
            plf = pl.paragraph_format
            plf.keep_together = True
            if i < len(lyrics) - 1:
                plf.keep_with_next = True
            plf.space_before = Pt(0)
            plf.space_after = Pt(0)
            plf.line_spacing = Pt(body_leading)
            rl = pl.add_run(line)
            # 副歌标记行用灰色小字号
            if line.startswith('（副歌'):
                rl.font.size = Pt(max(body_size - 1.5, 6.0))
                rl.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
                rl.font.italic = True
            else:
                rl.font.size = Pt(body_size)
            rl.font.name = 'Songti SC'
            set_cn(rl, '宋体')

    doc.save(out_path)
    summary = f'已保存: {out_path}  ({len(songs)} 首'
    if not keep_dups:
        summary += f', 去重删除 {total_removed} 行'
    if truncated_songs:
        summary += f', 自动精简 {len(truncated_songs)} 首'
    summary += ')'
    print(summary)
    return out_path


def main():
    ap = argparse.ArgumentParser(description='生成可打印歌词本 DOCX')
    ap.add_argument('songs_json', help='歌词 JSON 文件路径')
    ap.add_argument('-o', '--out', default='歌词本.docx', help='输出 DOCX 路径')
    ap.add_argument('--title', default='我的歌词乐理本', help='标题页书名')
    ap.add_argument('--size', default='a5', choices=['a5', 'b5', 'a4'], help='纸张尺寸')
    ap.add_argument('--keep-dups', action='store_true', help='不去重（保留全部重复副歌）')
    ap.add_argument('--keep-full', action='store_true', help='不自动精简超长歌（可能跨栏）')
    ap.add_argument('--no-chorus-mark', action='store_true', help='不插入副歌重复标记')
    args = ap.parse_args()

    songs = json.load(open(args.songs_json, encoding='utf-8'))
    build(songs, args.out, title=args.title, size=args.size,
          keep_dups=args.keep_dups, keep_full=args.keep_full,
          chorus_mark=not args.no_chorus_mark)


if __name__ == '__main__':
    main()
