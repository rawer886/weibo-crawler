# 微博爬虫

抓取微博内容和评论，支持断点续传、评论回复关系识别、图片下载。

## 安装

```bash
pip install -r requirements.txt
playwright install chromium
```

## 使用

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

## 配置

编辑 `config.py` 调整爬虫行为：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `delay` | 15 | 请求间隔（秒），实际会随机浮动 ±25% |
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
```

## 数据存储

数据存储在 `../data/` 目录（与项目同级），包含数据库、登录凭证、缓存、图片、日志。

## 数据库

SQLite 数据库包含以下表：

- **bloggers** - 博主信息（uid, nickname, followers_count）
- **posts** - 微博（mid, content, 互动数据, 图片, 转发信息）
- **comments** - 评论（comment_id, content, 点赞数, 是否博主回复, 回复关系）
- **crawl_progress** - 抓取进度

```bash
# 直接查询数据库
sqlite3 ../data/weibo.db "SELECT * FROM bloggers"
```

## 常见问题

**登录失效**：删除 `../data/cookies.json`，重新运行登录
