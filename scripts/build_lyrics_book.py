#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从歌词 JSON 生成可打印歌词本 DOCX。

输入格式（songs.json）:
[
  {"name": "冻结", "artist": "林俊杰", "lyrics": ["行1", "行2", ...]},
  ...
]

用法:
  python3 build_lyrics_book.py songs.json -o 歌词本.docx [--title "cosinX 的歌词乐理本"] [--size a5|b5|a4] [--keep-dups]
"""
import argparse, json, os, re, sys
from docx import Document
from docx.shared import Pt, Mm, RGBColor
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


def clean_tag_lines(lines):
    """删除单独成行的分唱标记（源：/凯：/合：/男：等）。"""
    return [l for l in lines if not TAG_RE.match(l.strip())]


def normalize(l):
    """去除语气词、叹词、标点后比较。"""
    l = re.sub(r'^(唉|哎|喔|哦|嗯|啊|呀|呐|嗷|嘿|嗨|woo|yeah|no|hey|la|na)+', '', l, flags=re.IGNORECASE)
    l = re.sub(r'(唉|哎|喔|哦|嗯|啊|呀|呐|嗷|嘿|嗨|woo|yeah|no|hey|la|na)+$', '', l, flags=re.IGNORECASE)
    l = re.sub(r'[，。！？、,.!?\s]', '', l)
    return l


def aggressive_dedup(lines, min_block=4, max_block=12):
    """块级去重：完全相同（或仅语气词差异）的连续 4-12 行块只保留第一遍。

    副歌重复段通常 4 行以上完全相同，唱一遍即可；每遍词不同的段落会保留。
    """
    lines = [l.strip() for l in lines if l.strip()]
    if not lines:
        return lines
    seen = {}
    out = []
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
                if orig_block == prev_block:  # 完全相同的重复块，跳过
                    i += L
                    hit = True
                    break
                substantive_diff = sum(
                    1 for a, b in zip(orig_block, prev_block)
                    if a != b and normalize(a) != normalize(b)
                )
                if substantive_diff <= L // 3:  # 差异仅为语气词，跳过
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
    return out


# ---------- 字号自适应 ----------
def pick_font(n_lines):
    """按行数选择(字号pt, 行距pt)，确保一首歌完整落在 A5 一栏内（约 490pt 可用高度）。"""
    if n_lines <= 38:
        return 8.5, 11.5
    if n_lines <= 46:
        return 7.5, 10.0
    if n_lines <= 52:
        return 7.0, 9.5
    if n_lines <= 58:
        return 6.5, 8.5
    return 6.0, 7.5  # 超长歌最小字号，若仍放不下需人工精简


# ---------- DOCX 生成 ----------
# A5 一栏可用高度（实际核算值，pt）
COL_AVAIL_PT = 538.6


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


def build(songs, out_path, title='我的歌词乐理本', size='a5', keep_dups=False):
    # 清洗 + 去重；空歌词歌跳过并警告
    total_removed = 0
    skipped = []
    kept = []
    for s in songs:
        orig = [l for l in (s.get('lyrics') or []) if l.strip()]
        orig = clean_tag_lines(orig)
        if not orig:
            skipped.append(s)
            continue
        if not keep_dups:
            new = aggressive_dedup(orig)
            total_removed += len(orig) - len(new)
            s['lyrics'] = new
        else:
            s['lyrics'] = orig
        kept.append(s)
    if skipped:
        print(f'警告: {len(skipped)} 首歌歌词为空，已跳过: '
              + ', '.join(f"{s.get('name')}({s.get('artist','')})" for s in skipped), file=sys.stderr)
    songs = kept

    # 超长歌校验：选字号后估算总高，超过一栏可用高度则警告
    for s in songs:
        n = len([l for l in s.get('lyrics', []) if l.strip()])
        body_size, body_leading = pick_font(n)
        title_size = max(body_size + 1.5, 7)
        est = n * body_leading + body_leading + 14  # 歌词行 + 歌名/歌手行余量
        if est > COL_AVAIL_PT:
            print(f'警告: 《{s.get("name")}》{n}行 估算高{est:.0f}pt>可用{COL_AVAIL_PT}pt，'
                  f'打印会跨栏，需人工精简到 ≤62 行', file=sys.stderr)

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

    # 目录页（两列无边框表格）
    doc.add_page_break()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run('目  录')
    r.font.size = Pt(14); r.font.bold = True; r.font.name = 'Arial'; set_cn(r, '黑体')

    entries = [f"{i+1}. {s['name']}" + (f"  {s['artist']}" if s.get('artist') else '') for i, s in enumerate(songs)]
    rows = (len(entries) + 1) // 2
    table = doc.add_table(rows=rows, cols=2)
    table.autofit = True
    tblPr = table._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement('w:' + edge)
        el.set(qn('w:val'), 'nil')
        borders.append(el)
    tblPr.append(borders)

    def fill_cell(cell, text):
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.line_spacing = 1.0
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
        pf.line_spacing = Pt(max(body_leading, title_size + 2))  # 标题行行距留足，防裁切
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
            ra.font.size = Pt(max(body_size - 1.5, 6.0))  # 下限 6pt，不触红线
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
            rl.font.size = Pt(body_size)
            rl.font.name = 'Songti SC'
            set_cn(rl, '宋体')

    doc.save(out_path)
    print(f'已保存: {out_path}  ({len(songs)} 首, 去重删除 {total_removed} 行)')
    return out_path


def main():
    ap = argparse.ArgumentParser(description='生成可打印歌词本 DOCX')
    ap.add_argument('songs_json', help='歌词 JSON 文件路径')
    ap.add_argument('-o', '--out', default='歌词本.docx', help='输出 DOCX 路径')
    ap.add_argument('--title', default='我的歌词乐理本', help='标题页书名')
    ap.add_argument('--size', default='a5', choices=['a5', 'b5', 'a4'], help='纸张尺寸')
    ap.add_argument('--keep-dups', action='store_true', help='不去重（保留全部重复副歌）')
    args = ap.parse_args()

    songs = json.load(open(args.songs_json, encoding='utf-8'))
    build(songs, args.out, title=args.title, size=args.size, keep_dups=args.keep_dups)


if __name__ == '__main__':
    main()
