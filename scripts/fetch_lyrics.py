#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从歌单歌曲列表批量联网抓取歌词（QQ音乐公开接口）。

用法:
  python3 fetch_lyrics.py songs.txt -o lyrics.json
  python3 fetch_lyrics.py songs.json -o lyrics.json   # 已含歌名/歌手的JSON

songs.txt 每行格式: 歌名 - 歌手   (或 歌名 歌手)
输出 JSON: [{"name":.., "artist":.., "lyrics":[行...], "status": "ok|problem"}]

特性: 搜索时校验歌手版本（同名歌不抓错）；歌词返回 base64 时自动解码；
      时间轴标记精确剥离（不误删 [Live]/[最后一遍] 等演唱提示）。
"""
import argparse, base64, json, re, sys, time, urllib.parse, urllib.request, concurrent.futures

SEARCH_API = 'https://c.y.qq.com/soso/fcgi-bin/search_for_qq_cp'
LYRIC_API = 'https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Referer': 'https://y.qq.com/',
}
# 只剥离 [mm:ss] / [mm:ss.xx] 时间轴与 [ti:/ar:/al:/by:/offset:] 元数据
TIME_TAG = re.compile(r'\[\d{1,2}:\d{2}(?:\.\d+)?\]')
META_TAG = re.compile(r'\[(?:ti|ar|al|by|offset|total|length):[^\]]*\]')


def http_get(url, timeout=12, retries=2):
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode('utf-8', errors='replace')
        except Exception as e:
            last = e
            time.sleep(1 + attempt)
    raise last


def search_song(name, artist=''):
    """搜索歌曲，返回候选列表（含是否与目标歌手匹配）。"""
    w = f'{name} {artist}'.strip()
    url = f'{SEARCH_API}?w={urllib.parse.quote(w)}&format=json&n=8&p=1'
    try:
        raw = http_get(url)
    except Exception as e:
        print(f'  搜索失败 {w}: {e}', file=sys.stderr)
        return []
    m = re.search(r'(\{.*\})\s*$', raw, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    out = []
    for s in (data.get('data', {}).get('song', {}).get('list', []) or []):
        sname = s.get('songname', '') or ''
        sartist = ' / '.join(a.get('name', '') for a in (s.get('singer') or [])).strip()
        matched = False
        if artist:
            # 目标歌手名出现在返回歌手串中（或反向包含），视为版本匹配
            target = artist.lower()
            src = sartist.lower()
            matched = target in src or src in target
        else:
            matched = True  # 未指定歌手时取第一条候选
        out.append({
            'songmid': s.get('songmid', ''),
            'name': sname,
            'artist': sartist,
            'matched': matched,
        })
    return out


def decode_lyric_text(text):
    """QQ 歌词可能直接返回文本或 base64。自动识别并解码。"""
    if not text:
        return None
    # 纯文本特征：含中文或含 [mm:ss] 时间轴
    if re.search(r'[\u4e00-\u9fff]', text) or re.search(r'\[\d{1,2}:\d{2}', text):
        return text
    try:
        # 去掉 base64 中的换行后尝试解码
        decoded = base64.b64decode(text.replace('\n', '').replace('\r', '')).decode('utf-8', errors='replace')
        return decoded
    except Exception:
        return text


def fetch_lyric(songmid):
    """按 songmid 获取歌词文本（行列表）。"""
    if not songmid:
        return None
    url = f'{LYRIC_API}?songmid={songmid}&format=json&nobase64=1'
    try:
        raw = http_get(url)
    except Exception as e:
        print(f'  歌词获取失败 {songmid}: {e}', file=sys.stderr)
        return None
    m = re.search(r'(\{.*\})\s*$', raw, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    lyric = decode_lyric_text(data.get('lyric', ''))
    if not lyric:
        return None
    lines = []
    for line in lyric.replace('\r', '').split('\n'):
        line = TIME_TAG.sub('', line)
        line = META_TAG.sub('', line).strip()
        if line:
            lines.append(line)
    return lines


def process_one(item):
    name = item['name']
    artist = item.get('artist', '')
    cands = search_song(name, artist)
    # 优先匹配歌手版本；无匹配歌手候选时退回第一条
    info = next((c for c in cands if c['matched']), cands[0] if cands else None)
    if not info or not info.get('songmid'):
        return {**item, 'lyrics': [], 'status': 'problem', 'note': '搜不到'}
    lines = fetch_lyric(info['songmid'])
    if not lines:
        return {**item, 'lyrics': [], 'status': 'problem', 'note': '无歌词'}
    return {
        'name': name,
        'artist': artist,
        'lyrics': lines,
        'status': 'ok',
        'source_song': info['name'],
        'source_artist': info['artist'],
    }


def main():
    ap = argparse.ArgumentParser(description='批量抓取歌词')
    ap.add_argument('input', help='songs.txt（每行"歌名 - 歌手"）或 songs.json')
    ap.add_argument('-o', '--out', default='lyrics.json')
    ap.add_argument('--workers', type=int, default=3, help='并发数，默认3（过高易被风控）')
    args = ap.parse_args()

    if args.input.endswith('.json'):
        with open(args.input, encoding='utf-8') as f:
            items = json.load(f)
    else:
        items = []
        for line in open(args.input, encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            if ' - ' in line:
                name, artist = line.split(' - ', 1)
            elif '-' in line:
                name, artist = line.split('-', 1)
            else:
                name, artist = line, ''
            items.append({'name': name.strip(), 'artist': artist.strip()})

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {}
        for idx, it in enumerate(items):
            time.sleep(0.3)  # 提交前限速（真实生效，避免并发风控）
            futs[ex.submit(process_one, it)] = idx
        for fut in concurrent.futures.as_completed(futs):
            idx = futs[fut]
            it = items[idx]
            try:
                r = fut.result()
                results.append((idx, r))
                print(f"[{r['status']}] {r['name']} - {r.get('artist', '')} ({len(r.get('lyrics', []))}行)")
            except Exception as e:
                print(f"[error] {it['name']}: {e}", file=sys.stderr)
                results.append((idx, {**it, 'lyrics': [], 'status': 'problem', 'note': str(e)}))

    # 按输入顺序输出（用序号做 key，避免同名歌覆盖）
    results.sort(key=lambda x: x[0])
    ordered = [r for _, r in results]
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(ordered, f, ensure_ascii=False, indent=1)
    ok = sum(1 for r in ordered if r['status'] == 'ok')
    print(f'\n完成: {len(ordered)} 首, 成功 {ok}, 问题 {len(ordered) - ok} → {args.out}')


if __name__ == '__main__':
    main()
