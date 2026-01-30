"""
微博爬虫配置文件

修改此文件来调整爬虫行为，修改后重新运行即可生效。
"""
import os

# =============================================================================
# 数据目录
# =============================================================================
# 数据存储在项目同级的 data 目录下，包含数据库、缓存、图片、日志等
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "cache"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "images"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "logs"), exist_ok=True)

# 数据文件路径（一般不需要修改）
DATABASE_PATH = os.path.join(DATA_DIR, "weibo.db")
COOKIE_FILE = os.path.join(DATA_DIR, "cookies.json")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

# =============================================================================
# 爬虫配置（可根据需要调整）
# =============================================================================
CRAWLER_CONFIG = {
    # 每条微博之间的等待时间（秒），实际会在此基础上随机浮动 ±25%
    # 建议值: 10-30 秒，太快容易触发风控
    "delay": 10,

    # 单次运行最大抓取数；达到数量后自动停止，下次运行会继续
    "max_posts_per_run": 1000,

    # 抓取时间范围（天）；只抓取最近 N 天内发布的微博
    "max_days": 365,

    # 微博稳定天数
    # 发布超过此天数的微博视为"稳定"，评论数据更完整
    # history 模式只抓取稳定微博，new 模式会标记未稳定的待后续更新
    "stable_weibo_days": 1,

    # 浏览器窗口大小（占屏幕比例 0-1）
    "browser_width_ratio": 0.8,
    "browser_height_ratio": 1.0,

    # 无头模式
    # True: 后台运行，不显示浏览器窗口
    # False: 显示浏览器，方便调试和首次登录
    "headless": True,

    # 是否下载图片
    "download_images": True,

    # 日志级别: DEBUG, INFO, WARNING, ERROR
    # DEBUG 会输出更详细的信息，用于排查问题
    "log_level": "INFO",
}
