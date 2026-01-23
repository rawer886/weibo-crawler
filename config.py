"""
微博爬虫配置文件
"""
import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据库配置
DATABASE_PATH = os.path.join(BASE_DIR, "weibo.db")

# 要关注的博主列表 (填入博主的 uid)
# 获取方式: 打开博主主页，URL 中的数字就是 uid
# 例如: https://weibo.com/u/1234567890 中的 1234567890
BLOGGER_UIDS = [
    "1497035431",   # 测试博主1
    "2014433131",   # 测试博主2
]

# 爬虫配置
CRAWLER_CONFIG = {
    # 请求间隔（秒），随机范围
    "min_delay": 3,
    "max_delay": 8,

    # 每个博主最多抓取的微博数量（首次运行时）
    "max_posts_per_blogger": 10,  # 测试阶段先设少一点

    # 增量抓取优化：连续遇到多少条已入库微博后停止翻页
    "stop_after_exists_count": 3,

    # 评论抓取配置
    # 注意：这是"期望获取"的数量，用于控制是否翻页
    # 如果一次请求返回的数据超过这个数量，会全部存储（不浪费已返回的数据）
    "max_comments_per_post": 10,

    # 是否只抓取热门评论
    "hot_comments_only": True,

    # 浏览器配置
    "headless": False,  # False 可以看到浏览器操作，方便调试

    # Cookie 文件路径
    "cookie_file": os.path.join(BASE_DIR, "cookies.json"),

    # 缓存配置（历史微博列表永久缓存，减少重复请求）
    "cache_dir": os.path.join(BASE_DIR, "cache"),

    # 图片下载配置
    "download_images": True,  # 是否下载图片
    "images_dir": os.path.join(BASE_DIR, "images"),  # 图片保存目录
}

# 日志配置
LOG_CONFIG = {
    "level": "DEBUG",  # 调试阶段使用 DEBUG
    "format": "%(asctime)s - %(levelname)s - %(message)s",
    "file": os.path.join(BASE_DIR, "crawler.log"),
}
