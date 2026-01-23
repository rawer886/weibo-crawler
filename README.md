# 微博爬虫

一个用于抓取微博内容和评论的爬虫工具，支持断点续传、评论回复关系识别等功能。

## 项目结构

```
weibo-crawler/
├── config.py              # 配置文件（博主列表、抓取参数等）
├── crawler.py             # 爬虫核心逻辑
├── database.py            # 数据库操作
├── main.py               # 主程序入口
├── requirements.txt      # Python依赖
├── run.sh               # 快速启动脚本
├── scripts/             # 查询和分析脚本
│   ├── query_blogger_comments.py  # 查询博主评论
│   └── README.md
├── tests/               # 测试脚本
│   ├── test_single_post.py       # 单条微博测试
│   └── README.md
└── data/                # 数据目录（运行时产生的所有文件）
    ├── weibo.db         # SQLite数据库
    ├── cookies.json     # 登录cookies（自动生成）
    ├── cache/           # API响应缓存
    ├── images/          # 下载的图片（按博主和日期组织）
    ├── logs/            # 运行日志
    └── README.md        # 数据目录说明
```

## 功能特性

### 核心功能
- 🔐 自动登录和cookie管理
- 👥 支持多个博主同时抓取
- 🔄 断点续传（支持向前抓新微博和向后抓历史）
- ⏰ 时间范围限制（默认180天）
- 💬 **评论回复关系识别**（主评论和子评论的父子关系）
- 📸 图片下载（支持浏览器缓存优先）
- 💾 API响应永久缓存（减少重复请求）
- ⚡ 优雅停止（Ctrl+C）

### 智能策略
- 评论抓取延迟：微博发布N天后才抓评论，让评论稳定下来
- 随机延迟：8-30秒随机间隔，避免被封
- 缓存优化：历史数据永久缓存，新数据实时抓取

## 数据库结构

### bloggers 表
- uid, nickname, description, followers_count

### posts 表
- mid, uid, content, created_at
- reposts_count, comments_count, likes_count
- is_repost, repost_uid, repost_nickname, repost_content
- images (JSON), local_images (JSON), video_url, source_url

### comments 表
- comment_id, mid, uid, nickname, content, created_at, likes_count
- is_blogger_reply (是否是博主回复)
- reply_to_comment_id, reply_to_uid, reply_to_nickname, reply_to_content

## 安装

1. 克隆项目
```bash
git clone <repository-url>
cd weibo-crawler
```

2. 创建虚拟环境并安装依赖
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. 安装 Playwright 浏览器
```bash
playwright install chromium
```

## 配置

编辑 `config.py`：

```python
# 要关注的博主列表
BLOGGER_UIDS = [
    "1497035431",   # 博主1
    "2014433131",   # 博主2
]

# 爬虫配置
CRAWLER_CONFIG = {
    "min_delay": 8,              # 请求间隔（秒）
    "max_delay": 30,
    "max_posts_per_run": 50,     # 每次运行最多抓取微博数
    "max_days": 180,             # 抓取时间范围（天）
    "max_comments_per_post": 10, # 每条微博期望抓取评论数
    "comment_delay_days": 3,     # 微博发布几天后才抓评论
    "headless": False,           # 是否无头模式
    "download_images": True,     # 是否下载图片
}
```

## 快速开始

### 首次运行

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行主程序
python main.py
```

首次运行会打开浏览器窗口，需要手动登录微博。登录成功后按 Enter 继续，cookie 会自动保存。

### 抓取模式

在 `main.py` 中可以选择不同的抓取模式：

```python
# 只抓取新微博
run_crawler(BLOGGER_UIDS, mode="new")

# 继续抓取历史微博
run_crawler(BLOGGER_UIDS, mode="history")

# 先抓新的，再抓历史（默认）
run_crawler(BLOGGER_UIDS, mode="all")
```

### 停止爬虫

按 `Ctrl+C` 可以优雅停止（会等待当前任务完成并关闭浏览器）。再按一次可强制退出。

## 评论回复关系

爬虫能正确识别评论的回复关系：

- **主评论**：直接评论微博
- **子评论**：回复主评论或其他子评论

数据库字段：
- `reply_to_comment_id`: 被回复评论的ID
- `reply_to_uid`: 被回复者的UID
- `reply_to_nickname`: 被回复者的昵称
- `reply_to_content`: 被回复的内容

## 扩展工具

项目包含以下工具目录：

- **scripts/**: 数据查询和分析脚本（详见 [scripts/README.md](scripts/README.md)）
- **tests/**: 功能测试脚本（详见 [tests/README.md](tests/README.md)）

## 常见问题

### 登录失效
删除 `data/cookies.json`，重新运行程序手动登录。

### 浏览器打不开
检查是否安装了 Playwright 浏览器：
```bash
playwright install chromium
```

### 抓取速度慢
这是正常的！为了避免被封，默认 8-30 秒间隔。可以在 `config.py` 中适当调整：
```python
CRAWLER_CONFIG = {
    "min_delay": 5,   # 最小延迟（秒）
    "max_delay": 15,  # 最大延迟（秒）
}
```

### 查看数据
使用 SQLite 命令行：
```bash
sqlite3 data/weibo.db

# 查看博主列表
SELECT * FROM bloggers;

# 查看最新微博
SELECT mid, content, created_at FROM posts ORDER BY created_at DESC LIMIT 10;

# 查看博主评论
SELECT * FROM comments WHERE is_blogger_reply = 1;
```

## 注意事项

1. **登录**：首次运行需要手动登录，之后会自动使用保存的 cookies
2. **速度限制**：默认 8-30 秒随机间隔，避免被封
3. **评论延迟**：默认微博发布 3 天后才抓评论，让评论稳定
4. **时间范围**：默认只抓取最近 180 天的微博
5. **缓存**：历史微博列表会永久缓存，减少重复请求

## 技术栈

- Python 3.7+
- Playwright (浏览器自动化)
- SQLite (数据存储)
- Requests (HTTP 请求)

## 许可证

MIT
