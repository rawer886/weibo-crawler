"""
微博爬虫配置文件
"""
import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据目录（存放所有运行时产生的文件）
# 使用workspace共享data目录
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "cache"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "images"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "logs"), exist_ok=True)

# 数据库配置
DATABASE_PATH = os.path.join(DATA_DIR, "weibo.db")

# 爬虫配置
CRAWLER_CONFIG = {
    # 抓取间隔（秒）- 每条微博之间的等待时间，实际会在此基础上随机浮动
    "delay": 30, # 建议值: 10-30秒，太快容易被风控

    # 每次运行最多抓取的微博数量（断续抓取，每次少量）
    "max_posts_per_run": 100,

    # 抓取时间范围（天）- 只抓取最近 N 天的微博
    "max_days": 365,  # 一年

    # 微博发布多少天后视为"稳定"（默认只抓取稳定微博，评论数据更完整）
    "stable_days": 1,

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
