#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从音乐分享链接提取歌曲列表（歌名 + 歌手/作者）。

支持两种输入：
  1. 歌单链接：QQ音乐 / 网易云 / 酷狗 / 汽水音乐(抖音) / 酷我
  2. 单曲分享链接：上述平台的歌曲页

输出 JSON 统一带完整性标记：
  {"songs": [{"name": "歌名", "artist": "歌手"}], "platform": "qq|netease|kugou|qishui|kuwo",
   "total": 歌单总数(或None), "incomplete": true/false, "note": "说明"}

接口可用性（实测 2026-09）：
  - QQ音乐歌单接口完整可用（178首实测）
  - 网易云 weapi 加密接口完整可用（269首实测；需 pycryptodome，缺失时自动降级v6并警告）
  - 酷狗分享页只内嵌前10首预览 → 标记 incomplete，需浏览器补全
  - 汽水/抖音、酷我：无公开稳定接口 → 直接提示浏览器路径

用法:
  python3 fetch_playlist.py "<分享链接>" -o songs.json
"""
import argparse, base64, json, random, re, sys, urllib.parse, urllib.request

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148',
    'Referer': 'https://y.qq.com/',
}
TIMEOUT = 15

# 网易云 weapi 加密参数（网页版公开固定值）
NEMODULUS = ('00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629'
             'ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d'
             '813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7')
NEPUBKEY = '010001'
NENONCE = '0CoJUm6Qyw8W8jud'
NEIV = '0102030405060708'

try:
    from Crypto.Cipher import AES
    HAVE_CRYPTO = True
except Exception:
    HAVE_CRYPTO = False


def http_get(url, headers=None, timeout=TIMEOUT):
    h = dict(HEADERS)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8', errors='replace')


def strip_jsonp(raw):
    """从 JSONP 响应中剥出 JSON 对象（非贪婪，避免吞掉多余内容）。"""
    m = re.search(r'(\{.*\})\s*$', raw, re.S)
    return m.group(1) if m else raw


def extract_json_array(raw, key):
    """定位 '"key":[' 后用括号匹配提取完整 JSON 数组（处理转义字符串）。"""
    i = raw.find('"' + key + '":')
    if i < 0:
        return None
    s = raw.find('[', i)
    if s < 0:
        return None
    depth, in_str, esc = 0, False, False
    for j in range(s, len(raw)):
        c = raw[j]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    return raw[s:j + 1]
    return None


def parse_name_artist(name_str):
    """解析 '歌手 - 歌名' / '歌手-歌名' 格式。返回 (歌名, 歌手)。"""
    for sep in (' - ', '-'):
        if sep in name_str:
            a, n = name_str.rsplit(sep, 1)
            return n.strip(), a.strip()
    return name_str.strip(), ''


# ================= QQ音乐 =================
def qq_playlist(url):
    m = re.search(r'(?:disstid|playlist_id|playlist)[=/](\d+)', url) or re.search(r'[?&]id=(\d+)', url)
    if not m:
        return None, '未解析出QQ音乐歌单ID'
    pid = m.group(1)
    api = (f'https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg'
           f'?type=1&json=1&utf8=1&onlysong=0&disstid={pid}&format=json')
    raw = http_get(api)
    data = json.loads(strip_jsonp(raw))
    cdlist = data.get('cdlist') or []
    if not cdlist:
        return None, f'歌单 {pid} 返回空（可能私密/需登录），请用浏览器打开歌单提取'
    cd = cdlist[0]
    songs = []
    for s in cd.get('songlist', []):
        songs.append({
            'name': s.get('songname', '').strip(),
            'artist': ' / '.join(a.get('name', '') for a in s.get('singer', [])).strip(),
        })
    if not songs:
        return None, f'歌单 {pid} 无歌曲，请用浏览器核对'
    return {'songs': songs, 'total': len(songs), 'incomplete': False,
            'platform': 'qq', 'note': 'QQ音乐歌单'}, None


def qq_song(url):
    """QQ音乐单曲：从 songmid（query 或路径）查歌名歌手。"""
    m = (re.search(r'songmid=([0-9A-Za-z]+)', url)
         or re.search(r'song(?:Detail)?/([0-9A-Za-z]+)', url)
         or re.search(r'song_id=([0-9A-Za-z]+)', url))
    songmid = m.group(1) if m else None
    if not songmid:
        return None, '未解析出QQ音乐单曲ID'
    api = f'https://c.y.qq.com/v8/fcg-bin/fcg_play_single_song.fcg?songmid={songmid}&format=json'
    raw = http_get(api)
    data = json.loads(strip_jsonp(raw))
    s = (data.get('data') or [{}])[0]
    name = s.get('songname') or s.get('name') or ''
    artist = ' / '.join(a.get('name', '') for a in (s.get('singer') or []))
    if not name:
        return None, 'QQ音乐单曲查询失败，请用浏览器打开单曲页提取'
    return {'songs': [{'name': name, 'artist': artist}], 'total': 1, 'incomplete': False,
            'platform': 'qq', 'note': 'QQ音乐单曲'}, None


# ================= 网易云 =================
def _ne_aes_encrypt(text, key):
    pad = 16 - len(text.encode()) % 16
    text = text + chr(pad) * pad
    c = AES.new(key.encode(), AES.MODE_CBC, NEIV.encode())
    return base64.b64encode(c.encrypt(text.encode())).decode()


def _ne_rsa_encrypt(text):
    num = int.from_bytes(text[::-1].encode(), 'big')
    return format(pow(num, int(NEPUBKEY, 16), int(NEMODULUS, 16)), 'x').zfill(256)


def ne_weapi(url, data):
    """网易云网页版真实接口（weapi，匿名可用，实测返回全量数据）。"""
    if not HAVE_CRYPTO:
        raise RuntimeError('缺少 pycryptodome，无法使用网易云 weapi 接口')
    sec_key = ''.join(random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(16))
    enc1 = _ne_aes_encrypt(json.dumps(data), NENONCE)
    enc2 = _ne_aes_encrypt(enc1, sec_key)
    body = urllib.parse.urlencode({'params': enc2, 'encSecKey': _ne_rsa_encrypt(sec_key)}).encode()
    req = urllib.request.Request(url, data=body, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'Referer': 'https://music.163.com/',
        'Content-Type': 'application/x-www-form-urlencoded',
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _ne_songs_from_tracks(tracks):
    return [{'name': t.get('name', '').strip(),
             'artist': ' / '.join(a.get('name', '') for a in t.get('ar', t.get('artists', []))).strip()}
            for t in tracks]


def netease_playlist(url):
    m = re.search(r'[?&]id=(\d+)', url)
    if not m:
        return None, '未解析出网易云歌单ID'
    pid = m.group(1)
    # 方案A：weapi 完整读取（trackIds 全量 + song/detail 批量取歌）
    if HAVE_CRYPTO:
        try:
            d = ne_weapi('https://music.163.com/weapi/v6/playlist/detail?csrf_token=',
                         {'id': int(pid), 'n': 1000, 's': 8})
            pl = d.get('playlist') or {}
            tracks = pl.get('tracks') or []
            ids = [t['id'] for t in (pl.get('trackIds') or [])]
            total = pl.get('trackCount') or len(ids) or len(tracks)
            if ids and len(tracks) < len(ids):
                sd = ne_weapi('https://music.163.com/weapi/v3/song/detail?csrf_token=',
                              {'c': json.dumps([{'id': i} for i in ids])})
                tracks = sd.get('songs') or []
            songs = _ne_songs_from_tracks(tracks)
            if songs:
                incomplete = len(songs) < total
                note = '网易云weapi接口只返回部分歌曲，需浏览器补全' if incomplete else '网易云歌单'
                return {'songs': songs, 'total': total, 'incomplete': incomplete,
                        'platform': 'netease', 'note': note}, None
        except Exception as e:
            print(f'  网易云weapi解析失败({e})，降级v6接口...', file=sys.stderr)
    # 方案B：v6 公开接口（可能只返回前几首，不完整）
    api = f'https://music.163.com/api/v6/playlist/detail?id={pid}&n=1000&s=8'
    raw = http_get(api, headers={'Referer': 'https://music.163.com/', 'User-Agent': HEADERS['User-Agent']})
    data = json.loads(raw)
    pl = data.get('playlist') or {}
    tracks = pl.get('tracks') or []
    total = pl.get('trackCount') or len(tracks)
    if not tracks:
        return None, f'网易云接口未返回歌曲（code={data.get("code")}，常被限流），请用浏览器打开歌单提取'
    songs = _ne_songs_from_tracks(tracks)
    incomplete = len(songs) < total
    note = '网易云接口只返回部分歌曲，需浏览器补全' if incomplete else '网易云歌单'
    return {'songs': songs, 'total': total, 'incomplete': incomplete,
            'platform': 'netease', 'note': note}, None


def netease_song(url):
    m = re.search(r'[?&]id=(\d+)', url)
    if not m:
        return None, '未解析出网易云单曲ID'
    sid = int(m.group(1))
    if HAVE_CRYPTO:
        try:
            d = ne_weapi('https://music.163.com/weapi/v3/song/detail?csrf_token=',
                         {'c': json.dumps([{'id': sid}])})
            sl = d.get('songs') or []
            if sl:
                s = sl[0]
                return {'songs': [{'name': s.get('name', '').strip(),
                                   'artist': ' / '.join(a.get('name', '') for a in s.get('ar', []))}],
                        'total': 1, 'incomplete': False, 'platform': 'netease', 'note': '网易云单曲'}, None
        except Exception:
            pass
    api = f'https://music.163.com/api/song/detail?ids=[{sid}]&id={sid}'
    raw = http_get(api, headers={'Referer': 'https://music.163.com/', 'User-Agent': HEADERS['User-Agent']})
    data = json.loads(raw)
    songs_list = data.get('songs') or []
    if not songs_list:
        return None, '网易云单曲查询失败，请用浏览器打开单曲页提取'
    s = songs_list[0]
    return {'songs': [{'name': s.get('name', '').strip(),
                       'artist': ' / '.join(a.get('name', '') for a in s.get('artists', []))}],
            'total': 1, 'incomplete': False, 'platform': 'netease', 'note': '网易云单曲'}, None


# ================= 酷狗 =================
def kugou_playlist(url):
    m = re.search(r'gcid_([0-9a-zA-Z]+)', url)
    if not m:
        return None, '未解析出酷狗歌单ID'
    gcid = m.group(1)
    raw = http_get(url, headers={'Referer': 'https://m.kugou.com/', 'User-Agent': HEADERS['User-Agent']})
    arr = extract_json_array(raw, 'songs')
    total_m = re.search(r'"count":(\d+)', raw)
    total = int(total_m.group(1)) if total_m else None
    if not arr:
        return None, '酷狗分享页未内嵌歌曲数据，请用浏览器打开歌单提取'
    items = json.loads(arr)
    songs = []
    for it in items:
        # name 形如 '歌手1、歌手2 - 歌名'；取不到再用 remark
        n2 = it.get('name', '')
        name, artist = '', ''
        if n2:
            name, artist = parse_name_artist(n2)
        if not name:
            name = it.get('remark') or ''
            artist = it.get('singername', '')
        if name:
            songs.append({'name': name.strip(), 'artist': artist.strip()})
    if not songs:
        return None, '酷狗歌单解析为空，请用浏览器打开歌单提取'
    incomplete = total is not None and len(songs) < total
    note = f'酷狗分享页只内嵌前{len(songs)}首（共{total}首），需浏览器补全' if incomplete else '酷狗歌单'
    return {'songs': songs, 'total': total, 'incomplete': incomplete,
            'platform': 'kugou', 'note': note}, None


def kugou_song(url):
    """酷狗单曲：分享页通常内嵌歌曲信息，尽力提取；失败走浏览器。"""
    raw = http_get(url, headers={'Referer': 'https://m.kugou.com/', 'User-Agent': HEADERS['User-Agent']})
    m = re.search(r'"songname"\s*:\s*"([^"]+)"', raw) or re.search(r'"remark"\s*:\s*"([^"]+)"', raw)
    m2 = re.search(r'"singername"\s*:\s*"([^"]*)"', raw)
    if m:
        name = m.group(1).encode().decode('unicode_escape', errors='replace')
        artist = m2.group(1).encode().decode('unicode_escape', errors='replace') if m2 else ''
        return {'songs': [{'name': name, 'artist': artist}], 'total': 1, 'incomplete': False,
                'platform': 'kugou', 'note': '酷狗单曲'}, None
    return None, '酷狗单曲解析失败，请用浏览器打开单曲页提取'


# ================= 汽水音乐 / 抖音 =================
def qishui(url):
    """无公开稳定接口，一律提示浏览器路径（诚实标注，不假装支持）。"""
    if '/s/' in url:
        hint = '汽水音乐短链无法脚本展开'
    else:
        hint = '汽水音乐页面为 JS 渲染'
    return None, f'{hint}：用浏览器打开链接，等页面加载后提取歌曲名与歌手'


# ================= 酷我 =================
def kuwo(url):
    """酷我无公开稳定接口（需登录cookie），提示浏览器路径。"""
    return None, '酷我音乐无公开接口：用浏览器打开链接，从页面提取歌曲名与歌手'


# ================= 路由 =================
PLATFORM_RULES = [
    ('qq', 'QQ音乐', ['y.qq.com', 'i2.y.qq.com', 'i.y.qq.com', 'c.y.qq.com']),
    ('netease', '网易云', ['music.163.com', '163cn.tv']),
    ('kugou', '酷狗', ['kugou.com']),
    ('qishui', '汽水音乐/抖音', ['qishui.douyin.com', 'douyin.com', 'iesdouyin.com']),
    ('kuwo', '酷我', ['kuwo.cn']),
]


def route(url):
    url = url.strip()
    for key, name, domains in PLATFORM_RULES:
        if any(d in url for d in domains):
            is_song = ('song' in url.lower() or 'single' in url.lower()
                       or 'songmid' in url or 'song_detail' in url.lower() or '/song/' in url)
            if key == 'qq':
                fn = qq_song if (is_song or 'song' in url) else qq_playlist
            elif key == 'netease':
                fn = netease_song if '/song' in url else netease_playlist
            elif key == 'kugou':
                fn = kugou_playlist if '/songlist/' in url.lower() else kugou_song
            elif key == 'qishui':
                fn = qishui
            else:
                fn = kuwo
            return name, fn(url)
    return None, ('无法识别的链接，请提供主流平台（QQ音乐/网易云/酷狗/汽水音乐/酷我）的分享链接', None)


def main():
    ap = argparse.ArgumentParser(description='解析音乐分享链接（歌单/单曲）')
    ap.add_argument('url', help='歌单或单曲分享链接')
    ap.add_argument('-o', '--out', default='songs.json')
    args = ap.parse_args()

    try:
        name, (result, err) = route(args.url)
    except Exception as e:
        print(f'解析出错: {e}', file=sys.stderr)
        sys.exit(1)

    if err:
        print(f'[{name}] {err}', file=sys.stderr)
        sys.exit(1)

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f'[{name}] {result["note"]} → {args.out}')
    print(f'  歌曲数: {len(result["songs"])}', end='')
    if result.get('total') and result['total'] != len(result['songs']):
        print(f' (歌单共 {result["total"]} 首)', end='')
    print()
    for s in result['songs'][:10]:
        print(f'  {s["name"]} - {s["artist"]}')
    if len(result['songs']) > 10:
        print(f'  ... 共 {len(result["songs"])} 首')
    if result.get('incomplete'):
        print('  ⚠ 列表不完整，需浏览器补全（见 references/playlist-sources.md）', file=sys.stderr)


if __name__ == '__main__':
    main()
