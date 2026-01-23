"""
微博爬虫配置文件
"""
import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据目录（存放所有运行时产生的文件）
DATA_DIR = os.path.join(BASE_DIR, "data")

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "cache"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "images"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "logs"), exist_ok=True)

# 数据库配置
DATABASE_PATH = os.path.join(DATA_DIR, "weibo.db")

# 要关注的博主列表 (填入博主的 uid)
# 获取方式: 打开博主主页，URL 中的数字就是 uid
# 例如: https://weibo.com/u/1234567890 中的 1234567890
BLOGGER_UIDS = [
    "1497035431",   # 测试博主1
    "2014433131",   # 测试博主2
]

# 爬虫配置
CRAWLER_CONFIG = {
    # 请求间隔（秒），随机范围 - 放慢速度，减少风控
    "min_delay": 8,
    "max_delay": 30,

    # 每次运行最多抓取的微博数量（断续抓取，每次少量）
    "max_posts_per_run": 50,

    # 抓取时间范围（天）- 只抓取最近 N 天的微博
    "max_days": 180,  # 6个月

    # 评论抓取配置
    # 注意：这是"期望获取"的数量，用于控制是否翻页
    # 如果一次请求返回的数据超过这个数量，会全部存储（不浪费已返回的数据）
    "max_comments_per_post": 10,

    # 微博发布多少天后才抓取评论（让评论稳定下来）
    "comment_delay_days": 3,

    # 是否只抓取热门评论
    "hot_comments_only": True,

    # 浏览器配置
    "headless": False,  # False 可以看到浏览器操作，方便调试

    # Cookie 文件路径
    "cookie_file": os.path.join(DATA_DIR, "cookies.json"),

    # 缓存配置（历史微博列表永久缓存，减少重复请求）
    "cache_dir": os.path.join(DATA_DIR, "cache"),

    # 图片下载配置
    "download_images": True,  # 是否下载图片
    "images_dir": os.path.join(DATA_DIR, "images"),  # 图片保存目录
}

# 日志配置
LOG_CONFIG = {
    "level": "INFO",  # 正式运行使用 INFO
    "format": "%(asctime)s - %(levelname)s - %(message)s",
    "file": os.path.join(DATA_DIR, "logs", "crawler.log"),
}
