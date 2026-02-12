# 微博爬虫

抓取微博内容和评论，支持断点续传、评论回复关系识别、图片下载。

## 安装

```bash
pip install -r requirements.txt
playwright install chromium
```

## 快速开始

```bash
# 抓取单条微博
python main.py https://weibo.com/1234567890/AbCdEfGhI

# 批量抓取用户微博（稳定微博，发布超过1天）
python main.py https://weibo.com/u/1234567890

# 抓取最新微博（包括未稳定的）
python main.py https://weibo.com/u/1234567890 --mode new

# 从 N 天前开始抓取（配合 new 模式）
python main.py https://weibo.com/u/1234567890 --mode new --start-days 3
```

首次运行会打开浏览器，需手动登录微博，登录后按 Enter 继续。

## 项目结构

```
crawler/
├── main.py              # 命令行入口
├── run.sh               # 快捷运行脚本
├── requirements.txt     # 依赖列表
├── src/                 # 核心模块
│   ├── crawler.py       # 爬虫调度器
│   ├── browser.py       # Playwright 浏览器管理
│   ├── api.py           # 微博移动端 API
│   ├── parser.py        # DOM 解析
│   ├── database.py      # SQLite 数据库操作
│   ├── image.py         # 图片下载
│   ├── display.py       # 控制台输出
│   ├── logger.py        # 日志模块
│   ├── config.py        # 配置文件
│   └── utils.py         # 工具函数
└── scripts/             # 辅助脚本
    ├── show_stats.py    # 数据统计
    ├── show_post.py     # 查看微博详情
    ├── show_blogger_replies.py  # 博主回复
    ├── delete_post.py   # 删除微博
    ├── delete_comments.py  # 删除评论
    └── clean_images.py  # 清理图片
```

## 配置

编辑 `src/config.py` 调整爬虫行为：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `delay` | 15 | 请求间隔（秒），实际随机浮动 ±25% |
| `max_posts_per_run` | 100 | 单次运行最大抓取数 |
| `max_days` | 365 | 抓取时间范围（天） |
| `stable_weibo_days` | 1 | 微博发布几天后视为稳定 |
| `headless` | False | 无头模式（后台运行） |
| `download_images` | True | 是否下载图片 |
| `log_level` | INFO | 日志级别 |

## 辅助脚本

```bash
# 查看数据库统计
python scripts/show_stats.py

# 查看微博及评论
python scripts/show_post.py <mid>
python scripts/show_post.py <mid> -b    # 只看博主评论

# 查看博主所有回复
python scripts/show_blogger_replies.py <uid>

# 删除数据
python scripts/delete_comments.py <mid>  # 删除评论
python scripts/delete_post.py <mid>      # 删除微博

# 清理无效图片（按 MD5）
python scripts/clean_images.py --dry-run
```

## 数据存储

数据存储在 `../data/` 目录（与项目同级）：

```
data/
├── weibo.db        # SQLite 数据库
├── cookies.json    # 登录凭证
├── cache/          # API 响应缓存
├── images/         # 下载的图片
└── logs/           # 日志文件
```

## 抓取模式

### History 模式（默认）

从历史往更老方向抓取，适合首次抓取博主全部微博。

### New 模式

从最新往历史方向抓取，适合增量更新已有数据。

```
时间线（从新到旧）：
[最新] A → B → C → D → E → F → G → H → I → J [最老]
                    ↑                   ↑
             history_start        history_end
             (new 模式边界)     (history 模式边界)
```

## 数据库表

- **bloggers** - 博主信息（uid, nickname, followers_count）
- **posts** - 微博（mid, content, 互动数据, 图片, 转发信息）
- **comments** - 评论（comment_id, content, 点赞数, 是否博主回复, 回复关系）
- **crawl_progress** - 抓取进度边界

```bash
# 直接查询数据库
sqlite3 ../data/weibo.db "SELECT * FROM bloggers"
```

## 常见问题

**登录失效**：删除 `../data/cookies.json`，重新运行登录
