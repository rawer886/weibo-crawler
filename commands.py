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
from display import display_comments, print_crawl_stats, show_db_status


def crawl_single_post(url: str, uid: str, mid: str):
    """抓取单条微博"""
    print(f"抓取单条微博: {url}")
    print(f"UID: {uid}, MID: {mid}")
    print("-" * 50)

    crawler = WeiboCrawler()
    try:
        crawler.start(url)
        print("等待页面加载...")
        time.sleep(5)

        if not crawler.check_login_status():
            print("需要登录...")
            if not crawler.login():
                print("登录失败")
                return

        # 如果是密文 mid，从页面解析数字 mid
        numeric_mid = mid
        if not mid.isdigit():
            print(f"检测到密文 mid: {mid}，从页面解析数字 mid...")
            try:
                numeric_mid = crawler.parse_numeric_mid_from_page()
                print(f"解析到数字 MID: {numeric_mid}")
            except ValueError as e:
                print(f"解析失败: {e}")
                input("按回车键退出...")
                return

        result = crawler.crawl_single_post(uid, numeric_mid)

        # 输出统计
        print_crawl_stats(result["stats"])

        # 展示评论
        comments = result["comments"]
        if comments:
            print("\n" + "=" * 50)
            print("评论列表（按热度排序）:")
            print("=" * 50)
            display_comments(comments)

        print("\n" + "=" * 50)
        input("按回车键退出浏览器...")

    finally:
        crawler.stop()


def crawl_user(uid: str, mode: str = "history"):
    """批量抓取用户微博"""
    stable_days = CRAWLER_CONFIG.get("stable_days", 1)
    mode_desc = {
        "new": "抓取最新微博（包括未稳定的，评论标记待更新）",
        "history": f"抓取稳定微博（发布超过 {stable_days} 天）",
    }

    print(f"批量抓取用户: {uid}")
    print(f"抓取模式: {mode} - {mode_desc.get(mode, mode)}")
    print("-" * 50)

    init_database()

    crawler = WeiboCrawler()
    try:
        crawler.start()

        if not crawler.check_login_status():
            print("需要登录...")
            if not crawler.login():
                print("登录失败，退出")
                return

        crawler.crawl_blogger(uid, mode=mode)

    except Exception as e:
        print(f"抓取出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        crawler.stop()

    print("-" * 50)
    print("抓取完成！")
    show_db_status()
