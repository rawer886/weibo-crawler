"""
命令处理模块

职责：
- 单条微博抓取命令
- 用户批量抓取命令
"""
import time

from config import CRAWLER_CONFIG
from database import init_database
from crawler import WeiboCrawler
from display import show_db_status
from logger import get_logger

logger = get_logger(__name__)


def _ensure_login(crawler: WeiboCrawler) -> bool:
    """确保爬虫已登录"""
    if crawler.check_login_status():
        return True
    logger.info("需要登录...")
    return crawler.login()


def _resolve_mid(crawler: WeiboCrawler, mid: str) -> str:
    """解析微博ID，如果是密文则从页面获取数字ID"""
    if mid.isdigit():
        return mid

    logger.info(f"检测到密文 mid: {mid}，从页面解析数字 mid...")
    numeric_mid = crawler.parse_numeric_mid_from_page()
    logger.info(f"\tMID: {numeric_mid}")
    return numeric_mid


def crawl_single_post(url: str, uid: str, mid: str):
    """抓取单条微博"""
    logger.info(f"抓取单条微博: {url}")
    logger.info(f"UID: {uid}, MID: {mid}\n")

    init_database()

    crawler = WeiboCrawler()
    try:
        crawler.start(url)
        logger.info("等待页面数据加载...\n")
        time.sleep(5)

        if not _ensure_login(crawler):
            logger.error("登录失败")
            return

        try:
            numeric_mid = _resolve_mid(crawler, mid)
        except ValueError as e:
            logger.error(f"解析失败: {e}")
            input("按回车键退出...")
            return

        print()
        stable_days = CRAWLER_CONFIG.get("stable_days", 1)
        crawler.crawl_single_post(uid, numeric_mid, source_url=url, skip_navigation=True,
                                  stable_days=stable_days)
        input("\n按回车键退出浏览器...")

    finally:
        crawler.stop()


def crawl_user(uid: str, mode: str = "history"):
    """批量抓取用户微博"""
    stable_days = CRAWLER_CONFIG.get("stable_days", 1)
    mode_desc = {
        "new": "抓取最新微博（包括未稳定的，评论标记待更新）",
        "history": f"抓取稳定微博（发布超过 {stable_days} 天）",
    }

    logger.info(f"批量抓取用户: {uid}")
    logger.info(f"抓取模式: {mode} - {mode_desc.get(mode, mode)}\n")

    init_database()

    crawler = WeiboCrawler()
    try:
        crawler.start()

        if not _ensure_login(crawler):
            logger.error("登录失败，退出")
            return

        crawler.crawl_blogger(uid, mode=mode)

    except Exception as e:
        logger.error(f"抓取出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        crawler.stop()

    print()
    logger.info("抓取完成！")
    show_db_status()
