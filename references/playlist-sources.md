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
| 酷狗 | `m.kugou.com/songlist/gcid_XXX/?...` | ⚠️ 仅前10首 | 分享页内嵌 `songs` 数组只含前 10 首预览（含歌名+歌手），PC 页强制扫码登录、公开 API 已失效；全量需登录态或浏览器手动提取，标记 incomplete |
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

## 浏览器兜底流程（必须用 agent 内置沙箱浏览器 + PC 桌面模式）

**重要：使用 AI agent 自带的浏览器自动化工具（browser-use / seed_browser_use / mac_computer_use_tool plane="bu"），在 agent 沙箱内操作页面。禁止调用用户本地系统浏览器，禁止让用户手动打开网页。**

**必须用 PC 桌面模式访问**（设置桌面 User-Agent，如 Chrome on macOS/Windows），**禁止用手机移动模式**——移动模式下酷狗/汽水等歌单只显示部分歌曲或要求登录，PC 网页版通常能直接看到完整列表。

标准步骤：
1. 内置浏览器 `navigate(分享链接)`，设置桌面 UA，等待页面加载完成。
2. 循环 `scroll` 滚动到列表底部，每次滚动后观察歌曲数是否增加，直到数量不再变化（酷狗/汽水都是懒加载分页，必须滚到底）。
3. 用结构化读取（`read_all` / `get_page_text` / DOM 选择器）逐条提取**歌名 + 歌手**，不要用截图 OCR（容易漏行错字）。
4. 与页面顶部显示的歌单总数核对，一致后写入 `songs.json`（`incomplete: false`）。
5. 如果内置浏览器遇到登录墙/验证码且无法绕过，再向用户说明情况，请用户提供歌单截图或手动歌曲列表。

各平台页面特点：
- **酷狗**：PC 页 `www.kugou.com/playlist/id/xxx.html` 强制扫码登录（歌单主体为空）；移动页 `m.kugou.com` 只内嵌前 10 首预览；全量提取需登录态 cookie 或浏览器手动逐条复制。
- **汽水音乐**：短链 `qishui.douyin.com/s/xxx` 会跳转到 `music.douyin.com/qishui/share/playlist`，JS 渲染，PC 模式下需等加载后滚动。
- **酷我**：PC 页 `www.kuwo.cn/playlist_detail/xxx.html`，优先 PC 页。

## 常见坑
- **歌名带版本后缀**：如「快乐酷宝-(电视剧《快乐酷宝2》主题曲)」，提取后保留纯歌名。
- **同一首歌多版本重复**：按「歌名+歌手」去重，保留用户点名的版本。
- **多语种混排**：用户默认要中文歌，纯外文歌与用户确认。
- **歌单数量核对**：解析数（`len(songs)`）与 `total` 不一致时，以页面为准，浏览器补充。
