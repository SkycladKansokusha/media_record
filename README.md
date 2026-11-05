# MEDIA LOG — 个人观影 / 阅读 / 听歌记录

纯静态网站（HTML + CSS + 原生 JS 模块），数据存放在 `data/*.json`，封面按分类存放在 `covers/<分类>/`。
不需要构建步骤，也没有运行时依赖；可以直接部署到 GitHub Pages。

```
my-media-log/
├── index.html              页面骨架（没有文案，文案由 js/strings.js 填入）
├── css/
│   ├── variables.css       ★ 设计变量：颜色、字体、间距、切角、动画曲线
│   ├── base.css            重置、字体栈（含 CJK 按 lang 切换）、背景装饰
│   ├── components.css      顶栏、标题区、工具栏、卡片、菱形评分、详情面板
│   └── animations.css      CSS 动画（入场擦除、星级点亮、减少动态模式）
├── js/
│   ├── strings.js          ★ 全站英文界面文案（唯一的文案来源）
│   ├── config.js           ★ 分区结构 + 弹簧参数 / 错峰 / 倾斜参数
│   ├── store.js            读取 JSON、清洗、搜索、排序、统计（不碰 DOM）
│   ├── router.js           URL hash（#film/anime）
│   ├── render.js           把数据变成 DOM（卡片、占位封面、菱形评分）
│   ├── detail.js           详情面板（<dialog> + FLIP 展开动画）
│   ├── motion.js           弹簧求解器、缓动函数库、补间
│   ├── tilt.js             3D 视差倾斜（可复用模块）
│   └── main.js             入口：把以上模块连起来
├── data/                   movie / tv / anime / manga / literature / music .json + settings.json
├── covers/                 封面图片（随仓库提交），按分类分子文件夹：movie/ tv/ anime/ manga/ literature/ music/
├── scripts/
│   ├── add.py              交互式录入 + 封面抓取
│   ├── validate.py         数据校验
│   └── common.py           两个脚本共用的工具函数
├── .github/workflows/pages.yml   可选的 GitHub Actions 部署
├── requirements.txt
└── SPEC.md                 需求规格（供后续迭代参考）
```

相对你给的建议结构，我多加了 4 个文件，理由：
`js/config.js`（所有动画手感参数集中一处，符合"集中配置"的要求）、
`js/detail.js`（详情面板 + FLIP 逻辑较长，单独成文件更好读）、
`scripts/common.py`（add.py 与 validate.py 共享分类列表、评分校验、JSON 写入）、
`.nojekyll`（让 GitHub Pages 原样发布文件，不走 Jekyll）。

---

## 1. 安装与本地预览

需要 Python 3.9+。

```bash
cd my-media-log
```

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

（Windows：`.venv\Scripts\activate`）

```bash
pip install -r requirements.txt
```

`pillow` 是可选的：没装时 `add.py` 会把封面原样保存（不转格式、不缩放）。网站本身不需要任何 Python 包。

本地预览（必须通过本地服务器打开，直接双击 `index.html` 会因为浏览器禁止 `fetch` 本地文件而读不到数据）：

```bash
python3 -m http.server
```

然后打开 <http://localhost:8000>。

---

## 2. 添加条目：`add.py`

```bash
python3 scripts/add.py
```

流程：选分类 → 输入关键词搜索 → 从结果里选一条 → 逐项确认/修改标题等字段 → 下载封面 → 输入评分、评价、标签、日期 → 确认保存。

- 每个字段显示默认值：**回车 = 保留**，输入新内容 = 修改，输入 `-` = 清空。
- 评价可以多行，最后单独输入一行 `.` 结束。
- 评分 1–5，允许半星（如 `3.5`），其他值会被拒绝。
- 标签会从数据源自动填充前 3 个，可修改；取不到时会提示手动输入。
- 写入的 JSON 使用 `ensure_ascii=False`，中日韩文字以原文保存，并按日期从新到旧排序。
- 发现重复条目（同一数据源 id，或同名同年）会提示。

其他用法：

```bash
python3 scripts/add.py --manual
```

```bash
python3 scripts/add.py -c anime
```

`--manual`：跳过搜索，全部自己填；封面可以填本地路径或图片 URL。`-c`：直接指定分类。

### 数据源

| 分类 | 数据源 | 需要 Key |
| --- | --- | --- |
| movie / tv | TMDB（英文标题 `language=en-US`，原名 `original_title`，另外尝试取中文译名放进 altTitles） | 是 |
| anime / manga | AniList GraphQL（`title.english`，缺失时用 romaji；`title.native` 为原名） | 否 |
| literature | Open Library，结果太少时补充 Google Books | 否 |
| music | iTunes Search（中/日/韩关键词会自动搜对应地区商店） | 否 |

TMDB Key（免费申请：<https://www.themoviedb.org/settings/api>，v3 API Key 或 v4 Read Access Token 都可以）**只通过环境变量提供，绝不写进代码或仓库**：

```bash
export TMDB_API_KEY=你的key
```

（Windows PowerShell：`$env:TMDB_API_KEY="你的key"`）

想长期保存可以放进 `.env` 文件并在终端里 `source .env`；`.env` 已在 `.gitignore` 中。

---

## 3. 手动修改数据（标题、原名、译名…）

直接编辑 `data/<分类>.json`，保存后刷新页面即可，不需要改任何代码。

```json
{
  "id": "movie-0001",
  "title": "Spirited Away",
  "originalTitle": "千と千尋の神隠し",
  "originalLanguage": "ja",
  "altTitles": ["千与千寻"],
  "creator": "Hayao Miyazaki",
  "creatorOriginal": "宮崎駿",
  "year": 2001,
  "date": "2026-10-20",
  "rating": 4.5,
  "review": "评价文字，\n支持换行",
  "tags": ["animation", "fantasy"],
  "cover": "covers/movie/movie-0001.jpg",
  "source": { "provider": "tmdb", "id": "129" }
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | ✓ | 唯一，建议 `分类-0001` 格式 |
| `title` | ✓ | **英文**译名，作为主标题。缺失时网页会退回用 `originalTitle` |
| `originalTitle` | | 原名，作为副标题（与 title 相同时不重复显示） |
| `originalLanguage` | | 原名语言代码：`ja`、`zh`、`zh-Hant`、`ko`、`fr`… 决定汉字用哪国字形 |
| `altTitles` | | 其他译名数组，只在详情面板 `ALSO KNOWN AS` 中显示，也能被搜索到 |
| `creator` / `creatorOriginal` | | 创作者英文名 / 原名 |
| `year` | ✓ | 作品年份（整数） |
| `date` | ✓ | 记录日期 `YYYY-MM-DD`，页面显示为 `20 OCT 2026` |
| `rating` | ✓ | 1–5，0.5 的倍数 |
| `review` / `tags` | | 你写的内容，原样显示，中英文都可以 |
| `cover` | | 本地路径 `covers/<分类>/xxx.jpg`；留空显示占位封面 |

### 手动换封面

把图片放进 `covers/<分类>/`（例如 `covers/anime/anime-0014.jpg`），再把条目的 `cover` 改成这个路径。`add.py` 下载的封面会自动保存到对应分类的子文件夹。放错文件夹时 `validate.py` 会给出警告。

### 标题显示模式 `data/settings.json`

```json
{ "titleMode": "both", "deviceTilt": false }
```

- `"both"`（默认）：英文主标题 + 原名副标题
- `"english"`：只显示英文名
- `"original"`：原名在上，英文名在下
- `deviceTilt`：`true` 时手机上可以用陀螺仪倾斜卡片（iOS 会在第一次点击时请求权限）

### 校验数据

```bash
python3 scripts/validate.py
```

检查：必填字段、类型、评分是否 0.5 倍数且在 1–5、日期格式、封面文件是否存在、id 重复、`altTitles`/`tags` 是否字符串数组、语言代码格式、`settings.json`。
`title` 含中日韩字符（提醒补英文译名）、封面不在 `covers/<分类>/` 下、`covers/` 里有未被引用的图片时给出**警告**，不算错误。有错误时退出码为 1（GitHub Actions 部署会因此中止）。

---

## 4. 部署到 GitHub Pages

```bash
git init
```

```bash
git add .
```

```bash
git commit -m "Initial commit"
```

在 GitHub 新建一个仓库（例如 `my-media-log`），然后：

```bash
git remote add origin https://github.com/<你的用户名>/my-media-log.git
```

```bash
git branch -M main
```

```bash
git push -u origin main
```

二选一：

- **最简单**：仓库 Settings → Pages → Source 选 *Deploy from a branch* → `main` / `/ (root)`。
- **用 Actions（会先跑 validate.py）**：Settings → Pages → Source 选 *GitHub Actions*，之后每次 push 到 `main` 自动部署（`.github/workflows/pages.yml`）。

几分钟后访问 `https://<你的用户名>.github.io/my-media-log/`。所有路径都是相对路径，放在子目录下也能工作。

> 改了 JSON 后 push 即可。页面以 `cache: 'no-cache'` 读取 JSON，刷新就能看到最新数据。

---

## 5. 调整风格与手感

| 想改什么 | 改哪里 |
| --- | --- |
| 颜色、字体、间距、切角大小、卡片最小宽度 | `css/variables.css` |
| CSS 动画曲线和时长（`--ease-spring`、`--dur-*`） | `css/variables.css` |
| 弹簧刚度/阻尼、错峰间隔、入场距离、计数时长 | `js/config.js` → `MOTION` |
| 倾斜最大角度、透视、光泽强度、缩放 | `js/config.js` → `TILT` |
| 任何界面英文文案 | `js/strings.js` |
| 增加/调整分区和子分区 | `js/config.js` → `SECTIONS` / `CATEGORIES`（同时在 `strings.js` 加名称、在 `scripts/common.py` 的 `CATEGORIES` 加分类、建对应 JSON） |

弹簧参数经验值：`stiffness` 越大越快；`damping` 越小越"弹"（10 左右明显回弹，`≈ 2·√stiffness` 时不回弹）。

`index.html` 里的 `<title>`、`<meta description>` 和 `<noscript>` 是 JS 运行前的后备文字，改 `strings.js` 时顺手同步即可。

### 无障碍与性能

- 系统开启"减少动态效果"时：倾斜、弹簧、滑动全部关闭，只保留短淡入。
- 倾斜只写 `transform` / `opacity`，所有弹簧共用一个 `requestAnimationFrame` 循环。
- 卡片是 `<article>` + 覆盖全卡的 `<button>`，键盘可用 Tab 聚焦、回车打开；详情面板是原生 `<dialog>`，Esc 关闭、焦点自动回到卡片。按 `/` 可以快速聚焦搜索框。

---

## 版权说明

视觉风格参考了"科技档案感"的设计语言，但**没有使用任何官方图片、Logo、字体文件或网站代码**。Logo 是自己画的 SVG，字体来自 Google Fonts（Inter、Rajdhani、JetBrains Mono），中日韩字体使用系统字体。你通过 `add.py` 下载的封面版权归原作者所有，仅供个人记录使用。
