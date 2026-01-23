# 快速开始

## 1. 首次使用

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行主程序
python main.py
```

首次运行会打开浏览器窗口，需要手动登录微博。登录成功后按 Enter 继续。

## 2. 日常使用

### 抓取微博

```bash
# 使用快捷脚本
./run.sh

# 或手动运行
source venv/bin/activate
python main.py
```

### 查询博主评论

```bash
# 查询指定微博下博主的评论
python scripts/query_blogger_comments.py 5253489136775271
```

### 测试单条微博

```bash
# 测试抓取单条微博的评论
python tests/test_single_post.py 2014433131 5253489136775271
```

## 3. 配置博主列表

编辑 `config.py`：

```python
BLOGGER_UIDS = [
    "1497035431",   # 你要关注的博主UID
]
```

**如何获取博主UID？**
打开博主主页，URL中的数字就是UID：
- `https://weibo.com/u/1234567890` → UID: `1234567890`

## 4. 常见任务

### 只抓取新微博
```python
# 在 main.py 中修改
run_crawler(BLOGGER_UIDS, mode="new")
```

### 继续抓取历史
```python
run_crawler(BLOGGER_UIDS, mode="history")
```

### 抓取新微博+历史（默认）
```python
run_crawler(BLOGGER_UIDS, mode="all")
```

### 调整抓取速度
编辑 `config.py`：
```python
CRAWLER_CONFIG = {
    "min_delay": 5,   # 最小延迟（秒）
    "max_delay": 15,  # 最大延迟（秒）
}
```

### 调整抓取数量
```python
CRAWLER_CONFIG = {
    "max_posts_per_run": 100,  # 每次运行最多抓取100条
}
```

## 5. 查看数据

### 使用 SQLite 命令行
```bash
sqlite3 weibo.db

# 查看博主列表
SELECT * FROM bloggers;

# 查看最新微博
SELECT mid, content, created_at FROM posts ORDER BY created_at DESC LIMIT 10;

# 查看博主评论
SELECT * FROM comments WHERE is_blogger_reply = 1;

# 退出
.quit
```

### 使用查询脚本
```bash
# 查询指定微博下博主的评论
python scripts/query_blogger_comments.py <微博ID>
```

## 6. 停止爬虫

按 `Ctrl+C` 可以优雅停止（会等待当前任务完成并关闭浏览器）。

如果需要强制退出，再按一次 `Ctrl+C`。

## 7. 故障排除

### 登录失效
删除 `cookies.json`，重新运行程序手动登录。

### 浏览器打不开
检查是否安装了 Playwright 浏览器：
```bash
playwright install chromium
```

### 抓取速度慢
这是正常的！为了避免被封，默认8-30秒间隔。可以在 `config.py` 中适当调整。

### 图片下载失败
检查 `config.py` 中的 `download_images` 设置，确认图片目录权限。
