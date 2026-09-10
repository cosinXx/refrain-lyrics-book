# 分享链接解析手册（歌单 + 单曲）

各平台支持状态以本节为准（实测 2026-09），**未实测通过的能力不宣称支持**。
`fetch_playlist.py` 输出统一带完整性标记：
`{"songs":[{name,artist}], "platform": "qq|netease|kugou|qishui|kuwo", "total": 总数, "incomplete": bool, "note": "说明"}`

**incomplete=true 表示脚本只拿到部分歌曲，必须用浏览器补全后再进入歌词流程。**

## 歌单链接

| 平台 | 链接形态 | 脚本状态 | 说明 |
|---|---|---|---|
| QQ音乐 | `y.qq.com/n/ryqq/playlist?id=NNN`、`i2.y.qq.com/...details/playlist.html?...&id=NNN`、`i.y.qq.com/n2/m/share/details/taoge.html?id=NNN` | ✅ 完整支持 | 取 `disstid`/`playlist` 路径中的 ID（排除 `songid=`），调 `c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg`；私密/需登录歌单返回空→浏览器 |
| 网易云 | `music.163.com/m/playlist?id=NNN` | ✅ 完整支持 | **weapi 加密接口**（网页版真实接口，匿名可用）：`/weapi/v6/playlist/detail` 拿全量 trackIds → `/weapi/v3/song/detail` 批量取歌，实测 269 首全量成功；需 `pip install pycryptodome`，缺失时降级 v6（只回部分，标记 incomplete） |
| 酷狗 | `m.kugou.com/songlist/gcid_XXX/?...` | ⚠️ 部分支持 | 分享页内嵌 `songs` 数组只含前 10 首预览（含歌名+歌手），标记 incomplete 提示浏览器补全 |
| 汽水/抖音 | `qishui.douyin.com/s/xxxxx`、`music.douyin.com/qishui/share/playlist?playlist_id=NNN` | ❌ 必须浏览器 | JS 渲染+短链，无法脚本展开 |
| 酷我 | `www.kuwo.cn` | ❌ 必须浏览器 | 无公开稳定接口（需登录 cookie） |

## 单曲链接（用户可能直接丢单曲分享链接）

| 平台 | 链接形态 | 脚本状态 |
|---|---|---|
| QQ音乐 | `y.qq.com/n/ryqq/songDetail/XXXX`（songmid）、`...song.html?songmid=XXXX` | ✅ 支持：按 songmid 调 `c.y.qq.com/v8/fcg-bin/fcg_play_single_song.fcg` 取歌名歌手 |
| 网易云 | `music.163.com/song?id=NNN` | ✅ 支持：调 `/api/song/detail?ids=[id]` |
| 酷狗 | `www.kugou.com/song/#hash=XXX`、`m.kugou.com/share/...` | ❌ JS 页无内嵌数据，浏览器兜底 |
| 汽水/抖音 | `qishui.douyin.com/s/xxx` | ❌ 浏览器兜底 |
| 酷我 | `www.kuwo.cn/song_detail/xxx.html` | ❌ 浏览器兜底 |

单曲链接解析结果也是 `songs:[1首]` 结构，可直接合并进歌曲列表，走同一套歌词流程。

## 浏览器兜底流程（browser-use）
1. `bu.navigate(分享链接)`，等待加载。
2. 循环滚动到底部直到歌曲数不再增加（`bu.scroll` + 观察）。
3. `bu.read_all()` 提取歌曲行（歌名、歌手），或截图逐条读。
4. 结构化写入 `songs.json`（带 `incomplete: false`），与页面总数核对。

## 常见坑
- **歌名带版本后缀**：如「快乐酷宝-(电视剧《快乐酷宝2》主题曲)」，提取后保留纯歌名。
- **同一首歌多版本重复**：按「歌名+歌手」去重，保留用户点名的版本。
- **多语种混排**：用户默认要中文歌，纯外文歌与用户确认。
- **歌单数量核对**：解析数（`len(songs)`）与 `total` 不一致时，以页面为准，浏览器补充。
