# Refrain · 歌词本制作

> 把你收藏的歌单，做成一本可以打印、可以随手翻着唱的歌词本。

**Refrain** 是一个 AI Agent Skill：你丢一个音乐歌单链接（QQ音乐 / 网易云 / 酷狗 / 汽水音乐），它自动解析全部歌曲、联网逐首抓取并核对歌词、清洗去重，最终生成一本 **A5 大小、左右两栏、一栏一首、绝不跨页** 的可打印歌词本 DOCX，还能顺手做一张专辑封面拼贴。

---

## 它能做什么

- **多平台歌单解析**：QQ音乐、网易云（weapi 全量读取，实测 269 首）脚本直接支持；酷狗、汽水音乐、酷我通过浏览器兜底完整读取
- **三种输入形态**：歌单链接、单曲链接、歌单截图，都能提取歌名 + 歌手
- **联网歌词抓取**：QQ音乐公开接口逐首搜索取词，带歌手版本匹配（避免同名歌抓错版本），失败标记为 problem 由 agent 联网搜索补全
- **歌词清洗**：重复副歌只留一遍、删除分唱标记、剥离时间轴、错字漏句核对
- **A5 两栏排版**：一页左右各一首歌，分栏符 + keep_together 保证**任何歌都不跨页不串栏**；字号随歌词行数自适应（最低 6pt）；歌名带序号且与目录严格对应
- **专辑封面拼贴**：从曲目里挑代表性专辑封面，错落堆叠拼成 A5 封面图（非 AI 生成、非整齐网格）

## 产出长什么样

```
标题页 → 目录页（两列）→ 正文（A5 两栏，一栏一首，带序号）
```

实测成品：208 首歌、A5 双面打印、每首歌完整落在一栏内。

## 新手推荐：让 AI 帮你一键安装（最省事）

**最简单的用法：直接把这个仓库地址丢给 AI，让 AI 去读取这个技能即可使用。** 对 AI 说："读取 https://github.com/cosinXx/refrain-lyrics-book 这个技能并安装"，剩下的它会自己搞定。

如果 AI 不支持自动安装，手动方式也很简单：把这个仓库的 `refrain/` 整个文件夹复制到你的 AI Agent 的 user skills 目录下即可，无需编译、无需配置。

典型路径（豆包 / Doubao Work）：
```
~/Library/Application Support/DoubaoWork/Default/.doubaowork/agent_mode/workspace/.user_skills/refrain/
```

复制完成后，对 AI 说："帮我把这个歌单做成歌词本：<歌单链接>"，剩下的它会自己跑完。

## 手动安装（依赖）

```bash
pip install python-docx pillow pycryptodome
```

- `python-docx`：生成 DOCX
- `Pillow`：封面拼贴
- `pycryptodome`：网易云 weapi 加密接口（缺失时自动降级并警告）

## 快速使用

```bash
# 1. 解析歌单
python3 scripts/fetch_playlist.py "https://music.163.com/m/playlist?id=XXXXX" -o songs.json

# 2. 抓歌词
python3 scripts/fetch_lyrics.py songs.json -o lyrics.json --workers 3

# 3. 生成歌词本
python3 scripts/build_lyrics_book.py lyrics.json -o 歌词本.docx --title "我的歌词本"

# 4.（可选）做封面
python3 scripts/make_cover.py --title "我的歌词本" -o cover.png
```

## 目录结构

```
refrain/
├── SKILL.md              # AI Agent 读取的技能说明（核心）
├── scripts/
│   ├── fetch_playlist.py # 歌单/单曲解析（QQ/网易云全量 + 酷狗/汽水浏览器兜底）
│   ├── fetch_lyrics.py   # 联网歌词抓取（QQ音乐接口 + 歌手匹配）
│   ├── build_lyrics_book.py # A5 两栏 DOCX 生成（去重/字号自适应/不跨页/序号）
│   └── make_cover.py     # 专辑封面错落拼贴
└── references/
    ├── playlist-sources.md  # 各平台歌单解析手册
    ├── input-forms.md       # 三种输入形态处理
    ├── lyrics-quality.md    # 歌词核对质量标准
    └── format-spec.md       # A5 格式规范
```

## 设计原则

- **歌词必须联网来源**，禁止凭记忆生成
- **歌名序号 = 目录序号 = 正文序号**，三者一致
- **任何一首歌都不得跨页或串栏**，放不下就降字号或精简
- **重复副歌默认只留一遍**（歌词本是用来唱的，不是用来研究的）
- **平台能力如实声明**，拿不全就标记 incomplete 并走浏览器补全，不静默丢歌

## 更新日志

### v1.1.0（2026-09-11）

**新增**
- 超长歌自动精简：超过 62 行的歌自动删纯语气词行、截断到核心段落加「……」，保证不跨栏（`--keep-full` 关闭）
- 副歌重复标记：被删的重复副歌位置插入灰色斜体「（副歌 ×2）」，唱歌时知道要唱两遍（`--no-chorus-mark` 关闭）
- 第⑧步 AI 专家自检：用户确认后派多专家联网查歌词错字、查排版、查完整性
- 目录序号固定宽度右对齐，列宽固定，不再参差不齐

**修复**
- 歌手归一化去重：按「归一化歌名 + 第一个歌手」合并重复歌曲，修复「By2, 林俊杰」与「By2」被当成两首的问题
- 酷狗平台声明诚实化：PC 页强制扫码登录，脚本只能取分享页前 10 首，不再假装全量
- README 修正：歌词抓取失败不再谎称「自动降级网络搜索」，改为「标记 problem 由 agent 搜索补全」
- make_cover.py 跨平台字体探测：Windows（微软雅黑/黑体）、Linux（Noto CJK/文泉驿）、macOS（STHeiti/PingFang）自动适配，不再变豆腐块

**平台支持状态**
- QQ音乐、网易云音乐：脚本直接完全识别所有歌曲
- 汽水音乐、酷我音乐：必须用 agent 内置浏览器识别
- 酷狗音乐：暂时只能识别分享链接前 10 首，全量需登录态

### v1.0.0（2026-09-10）

- 初始发布：多平台歌单解析 + 联网歌词抓取 + A5 两栏可打印 DOCX 生成 + 专辑封面拼贴
- 网易云 weapi 加密接口全量读取（实测 269 首）
- 浏览器兜底强制 agent 内置沙箱浏览器 + PC 桌面模式 UA

## License

MIT
