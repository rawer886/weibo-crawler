#!/usr/bin/env python3
"""
微博爬虫入口文件
用法:
    python main.py              # 抓取稳定微博（默认模式，发布超过 stable_days 天的微博）
    python main.py --mode history  # 同上，抓取稳定微博
    python main.py --mode new   # 抓取最新微博（包括未稳定的，评论会标记待更新）
    python main.py --login      # 仅登录并保存 cookies
    python main.py --status     # 查看统计信息
    python main.py --recent     # 查看最近抓取的微博
"""
import argparse
import sys

from config import BLOGGER_UIDS, CRAWLER_CONFIG
from database import init_database, get_stats, get_recent_posts, get_crawl_progress
from crawler import run_crawler, WeiboCrawler


def cmd_run(mode: str = "history"):
    """运行爬虫"""
    if not BLOGGER_UIDS:
        print("错误: 请先在 config.py 中配置要抓取的博主 UID")
        print("获取 UID 方法: 打开博主主页，URL 中的数字就是 UID")
        print("例如: https://weibo.com/u/1234567890 中的 1234567890")
        sys.exit(1)

    stable_days = CRAWLER_CONFIG.get("stable_days", 1)
    mode_desc = {
        "new": f"抓取最新微博（包括未稳定的，评论标记待更新）",
        "history": f"抓取稳定微博（发布超过 {stable_days} 天）",
    }

    print(f"准备抓取 {len(BLOGGER_UIDS)} 个博主")
    print(f"博主 UID 列表: {BLOGGER_UIDS}")
    print(f"抓取模式: {mode} - {mode_desc.get(mode, mode)}")
    print(f"稳定天数: {stable_days} 天")
    print("-" * 50)

    run_crawler(BLOGGER_UIDS, mode=mode)

    print("-" * 50)
    print("抓取完成！")
    cmd_status()


def cmd_login():
    """仅登录并保存 cookies"""
    print("启动浏览器进行登录...")
    crawler = WeiboCrawler()
    try:
        crawler.start()
        crawler.login()
        print("登录完成，cookies 已保存到:", CRAWLER_CONFIG["cookie_file"])
    finally:
        crawler.stop()


def cmd_status():
    """查看统计信息"""
    init_database()
    stats = get_stats()

    print("\n=== 数据库统计 ===")
    print(f"博主数量: {stats['bloggers_count']}")
    print(f"微博数量: {stats['posts_count']}")
    print(f"评论数量: {stats['comments_count']}")

    if stats['posts_by_blogger']:
        print("\n各博主微博数:")
        for uid, count in stats['posts_by_blogger'].items():
            print(f"  {uid}: {count} 条")


def cmd_recent():
    """查看最近抓取的微博"""
    init_database()
    posts = get_recent_posts(10)

    if not posts:
        print("暂无数据")
        return

    print("\n=== 最近抓取的微博 ===\n")
    for post in posts:
        nickname = post.get('nickname') or post['uid']
        content = post['content'] or "(无内容)"
        if len(content) > 100:
            content = content[:100] + "..."

        print(f"【{nickname}】{post['created_at']}")
        print(f"  {content}")
        print(f"  转发:{post['reposts_count']} 评论:{post['comments_count']} 点赞:{post['likes_count']}")
        print()


def cmd_add_blogger(uid: str):
    """添加博主到配置（提示用户手动添加）"""
    print(f"请手动将以下 UID 添加到 config.py 的 BLOGGER_UIDS 列表中:")
    print(f'    "{uid}",')


def cmd_progress():
    """查看抓取进度"""
    init_database()
    print("\n=== 抓取进度 ===\n")

    for uid in BLOGGER_UIDS:
        progress = get_crawl_progress(uid)
        if progress:
            print(f"博主 {uid}:")
            print(f"  最新微博: {progress['newest_mid']} ({progress['newest_created_at']})")
            print(f"  最老微博: {progress['oldest_mid']} ({progress['oldest_created_at']})")
            print(f"  更新时间: {progress['updated_at']}")
        else:
            print(f"博主 {uid}: 尚未抓取")
        print()


def main():
    parser = argparse.ArgumentParser(description="微博爬虫工具")
    parser.add_argument("--mode", type=str, choices=["new", "history"], default="history",
                        help="抓取模式: history(稳定微博，默认), new(最新微博，评论标记待更新)")
    parser.add_argument("--login", action="store_true", help="仅登录并保存 cookies")
    parser.add_argument("--status", action="store_true", help="查看统计信息")
    parser.add_argument("--progress", action="store_true", help="查看抓取进度")
    parser.add_argument("--recent", action="store_true", help="查看最近抓取的微博")
    parser.add_argument("--add", type=str, metavar="UID", help="添加博主 UID")

    args = parser.parse_args()

    if args.login:
        cmd_login()
    elif args.status:
        cmd_status()
    elif args.progress:
        cmd_progress()
    elif args.recent:
        cmd_recent()
    elif args.add:
        cmd_add_blogger(args.add)
    else:
        cmd_run(mode=args.mode)


if __name__ == "__main__":
    main()
