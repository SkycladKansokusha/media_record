# SPEC — MEDIA LOG

个人"观影 / 阅读 / 听歌"记录网站的规格说明。后续迭代以此为准；修改需求时请先更新本文件。

## 1. 技术约束

| 项 | 规定 |
| --- | --- |
| 前端 | HTML + CSS + 原生 JavaScript ES Modules；无框架、无运行时依赖、无构建步骤 |
| 动画 | 弹簧、缓动、3D 倾斜全部自实现（`js/motion.js`、`js/tilt.js`） |
| 字体 | 系统字体或 Google Fonts（当前：Inter / Rajdhani / JetBrains Mono） |
| 数据 | `data/*.json`，前端 `fetch` 读取（`cache: 'no-cache'`） |
| 封面 | 下载到 `covers/<分类>/` 随仓库提交；前端不请求任何外部 API、不暴露 Key |
| 部署 | GitHub Pages，仓库根目录发布；可选 Actions 工作流 `.github/workflows/pages.yml` |
| 本地预览 | `python -m http.server` |
| 脚本依赖 | `requests`（必需）、`pillow`（可选，缺失时封面原样保存） |
| 设备 | 桌面与手机浏览器，响应式 |

## 2. 信息架构

| 一级分区（hash） | 二级分区 / 分类文件 | 封面比例 |
| --- | --- | --- |
| FILM & SERIES `#film/…` | MOVIES `movie`、TV SERIES `tv`、ANIME `anime` | 2:3 |
| BOOKS `#books/…` | MANGA `manga`、LITERATURE `literature` | 2:3 |
| MUSIC `#music` | ALBUMS `music`（无标签条） | 1:1 |

- 一级导航固定在顶部；二级分区为标签条，带弹簧滑动下划线。
- 每个分类：排序（RATING / DATE ADDED / TITLE，可切换升降序）、标签筛选（多选，取交集）、关键词搜索。
- 统计（每个分类顶部）：条目数、平均分（计数动画）、最近添加。
- URL hash 记录位置，刷新保持；无效 hash 自动纠正；每个一级分区记住上次的二级分区。
- 点击卡片打开详情面板：大封面、标题、原名、ALSO KNOWN AS、创作者（含原名）、年份、评分、完整评价、标签（可点击筛选）、记录日期。

## 3. 界面语言与多语言标题

- 界面全英文，`<html lang="en">`；所有文案集中于 `js/strings.js`（`STRINGS` 对象 + `t()` 占位符函数）。
- 日期：JSON 存 `YYYY-MM-DD`；显示 `Intl.DateTimeFormat('en-GB')` → `20 OCT 2026`（月份截为 3 字母）。
- 评价与标签原样显示；自动按文字推测 `lang`（假名→ja、谚文→ko、汉字→zh）。
- 标题规则：
  - 卡片主标题 `title`，若 `originalTitle` 存在且与 `title` 不同（忽略大小写、首尾空格），下方小一号、低透明度显示原名；两者均最多两行省略。
  - 原名元素带 `lang=originalLanguage`；CSS 按 `lang` 切换 CJK 字体栈（ja / zh / zh-Hant / ko）。
  - `titleMode`（`data/settings.json`）：`both`（默认）/ `english` / `original`。
  - 搜索字段：`title`、`originalTitle`、`altTitles`、`creator`、`creatorOriginal`、`tags`；NFKC + 小写规范化；多个词需全部命中。
  - 标题排序基于 `title`，`Intl.Collator('en', {sensitivity:'base'})`，忽略开头 The / A / An。
  - `title` 缺失 → 用 `originalTitle`；占位封面取标题首字符。

## 4. 数据结构

见 README「手动修改数据」。必填：`id`、`title`、`year`、`date`、`rating`。
`rating` ∈ {1, 1.5, …, 5}。`settings.json`：`titleMode`、`deviceTilt`。

`validate.py` 错误：缺必填、类型错误、评分非法、日期非法、封面不存在或为 URL、id 重复、`altTitles`/`tags` 非字符串数组、语言代码格式非法、settings 非法。
警告：`title` 含 CJK、有原名无语言代码、未知字段、未被引用的封面（递归扫描子文件夹）、封面不在 `covers/<分类>/` 下、id 前缀与分类不符、未来日期。

## 5. 视觉

- 配色：底 `#05070d`，深蓝层次 `#0b1a33 / #0e2449 / #12306a`，强调色 `#4fc3ff`。全部为 `:root` 变量。
- 几何：切角矩形（右上 + 左下，`clip-path`）、1px 线框、网格背景、半色调点阵、斜线条纹、十字准星、刻度尺、角标括号。
- 排版：等宽小号大写标注（`FILE / 001`、`SECTION 02`）、Rajdhani 大标题与数字、超大描边序号作背景。
- 评分：SVG 菱形，半分为左半菱形；进入视口时依次弹出点亮。
- 避免：圆角卡片、渐变泛滥、阴影堆砌。

## 6. 3D 视差倾斜（`js/tilt.js`）

- `perspective(1000px) rotateX/rotateY`，最大 ±13°，指针在卡片内的位置决定角度。
- 层次：投影（反向位移）→ 封面（图像内部反向平移）→ 框架/标注（`translateZ(28px)`）→ 光泽（跟随指针）。
- 三个弹簧（x、y、lift）驱动；离开时切换为低阻尼弹簧回正（可见回弹）。
- 只写 `transform` / `opacity`；矩形在进入时读取一次；所有动画共用一个 rAF。
- 触屏：按压时轻微倾斜 + 下压缩放，滚动时（pointercancel）回正；可选 `deviceorientation`。
- `prefers-reduced-motion`：关闭。

## 7. 动画系统（`js/motion.js` + `css/animations.css`）

- `Spring`：半隐式欧拉，1/240 s 子步长；`to()` 可中途改目标且速度连续；`spring(from, to, opts)` 便捷函数。
- `tween()`、`easings`（easeOutExpo / easeInOutCubic / easeOutBack / easeOutElastic …）、`cssEasings`。
- CSS：`--ease-spring` 用 `linear()` 采样真实弹簧曲线，`@supports` 回退 `cubic-bezier`。
- 场景：首屏错峰擦除入场；切换分区时旧卡片快速退出、新卡片弹簧错峰入场；`IntersectionObserver` 入场；详情面板 FLIP 从卡片位置展开 / 收回；菱形点亮；数字计数；悬停线框展开；标签下划线弹簧滑动。
- 参数集中：`js/config.js`（MOTION、TILT），`css/variables.css`（--dur-*、--ease-*）。

## 8. `add.py`

分类 → 搜索 → 选择 → 逐项确认（回车保留 / `-` 清空）→ 重复检测 → 封面下载（Pillow 转 JPEG ≤1200px；无 Pillow 原样保存）→ 评分（0.5 步长校验）、多行评价、标签、日期 → 预览确认 → 原子写入（`ensure_ascii=False`，按日期倒序）。
支持 `--manual`（封面可为本地路径或 URL）、`-c <分类>`。所有提示为英文；网络错误、401/429、无结果均有友好提示。

## 9. 已知限制 / 后续可做

- Google Books、Open Library 对中文书名的覆盖一般，原名常需手填。
- 匿名调用 Google Books 可能遇到 429 限流（稍后再试即可）。
- 暂无详情面板的独立 URL（只记录分区，不记录打开的条目）。
- 大量条目（上千）时可以考虑分页或虚拟滚动；目前全部渲染、按视口入场。
