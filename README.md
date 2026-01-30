# 微博爬虫

抓取微博内容和评论，支持断点续传、评论回复关系识别、图片下载。

## 安装

```bash
# 安装依赖
pip install -r requirements.txt

# 安装浏览器
playwright install chromium
```

## 使用

```bash
# 抓取单条微博
python main.py https://weibo.com/1497035431/AbCdEfGhI

# 批量抓取用户微博（稳定微博，发布超过1天）
python main.py https://weibo.com/u/1497035431

# 抓取最新微博（包括未稳定的）
python main.py https://weibo.com/u/1497035431 --mode new

# 查看统计信息
python main.py --status

# 查看最近抓取
python main.py --recent
```

首次运行会打开浏览器，需手动登录微博，登录后按 Enter 继续。

## 配置

编辑 `config.py`：

```python
CRAWLER_CONFIG = {
    "delay": 15,              # 请求间隔（秒），实际会随机浮动
    "max_posts_per_run": 50,  # 每次最多抓取微博数
    "max_days": 180,          # 抓取时间范围（天）
    "stable_weibo_days": 1,   # 微博发布几天后视为稳定
    "headless": False,        # 是否无头模式
    "download_images": True,  # 是否下载图片
}
```

## 辅助脚本

```bash
# 查看微博评论
python scripts/show_comments.py <微博ID>
python scripts/show_comments.py <微博ID> -b  # 只看博主评论

# 查看博主所有评论
python scripts/show_blogger_comments.py <博主UID>

# 删除微博评论
python scripts/delete_comments.py <微博ID>
```

## 项目结构

```
weibo-crawler/
├── main.py        # 命令行入口
├── commands.py    # 命令处理
├── crawler.py     # 爬虫核心
├── browser.py     # 浏览器控制
├── api.py         # 微博API
├── parser.py      # 页面解析
├── image.py       # 图片下载
├── database.py    # 数据库操作
├── display.py     # 输出展示
├── config.py      # 配置文件
└── scripts/       # 辅助脚本
```

数据存储在 `../data/` 目录（与项目同级），包含数据库、cookies、缓存、图片、日志。

## 数据库

SQLite 数据库包含三张表：

- **bloggers**: 博主信息（uid, nickname, followers_count）
- **posts**: 微博（mid, content, 互动数据, 图片, 转发信息）
- **comments**: 评论（comment_id, content, 点赞数, 是否博主回复, 回复关系）

```bash
# 查看数据
sqlite3 ../data/weibo.db "SELECT * FROM bloggers"
```

## 常见问题

**登录失效**: 删除 `../data/cookies.json`，重新运行登录

**Ctrl+C 停止**: 按一次优雅停止，按两次强制退出
