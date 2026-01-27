#!/usr/bin/env python3
"""
微博爬虫 - 命令行入口

用法:
    python main.py https://weibo.com/1497035431/AbCdEfGhI       # 抓取单条微博
    python main.py https://weibo.com/u/1497035431              # 批量抓取用户微博
    python main.py https://weibo.com/u/1497035431 --mode new   # 抓取最新微博
    python main.py https://weibo.com/u/1497035431 --mode sync  # 同步校验缺失微博
    python main.py --status                                    # 查看统计信息
    python main.py --recent                                    # 查看最近抓取
"""
import argparse
import sys
import re

from commands import crawl_single_post, crawl_user
from display import show_db_status, show_recent_posts



def parse_weibo_url(url: str) -> dict:
    """解析微博 URL，返回类型和参数

    支持的格式:
    - https://weibo.com/u/1497035431          -> {"type": "user", "uid": "3689493785"}
    - https://weibo.com/1497035431/AbCdEfGhI  -> {"type": "post", "uid": "3689493785", "mid": "QogZOCUm5"}
    - https://weibo.com/3689493785/5234567890 -> {"type": "post", "uid": "3689493785", "mid": "5234567890"}
    """
    # 用户主页: /u/数字
    user_match = re.search(r'weibo\.com/u/(\d+)', url)
    if user_match:
        return {"type": "user", "uid": user_match.group(1)}

    # 单条微博: /数字uid/mid
    post_match = re.search(r'weibo\.com/(\d+)/(\w+)', url)
    if post_match:
        return {"type": "post", "uid": post_match.group(1), "mid": post_match.group(2)}

    return {"type": "unknown"}


def main():
    parser = argparse.ArgumentParser(
        description="微博爬虫工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py https://weibo.com/1497035431/AbCdEfGhI       # 抓取单条微博
  python main.py https://weibo.com/u/1497035431              # 批量抓取用户微博
  python main.py https://weibo.com/u/1497035431 --mode new   # 抓取用户最新微博
  python main.py https://weibo.com/u/1497035431 --mode sync  # 同步校验缺失微博
        """
    )
    parser.add_argument("url", nargs="?", help="微博 URL（用户主页或单条微博）")
    parser.add_argument("--mode", choices=["new", "history", "sync"], default="history",
                        help="抓取模式: history(稳定微博), new(最新微博), sync(同步校验缺失)")
    parser.add_argument("--status", action="store_true", help="查看统计信息")
    parser.add_argument("--recent", action="store_true", help="查看最近抓取的微博")

    args = parser.parse_args()

    # 处理查询命令
    if args.status:
        show_db_status()
        return

    if args.recent:
        show_recent_posts()
        return

    # 必须传入 URL
    if not args.url:
        parser.print_help()
        print("\n错误: 请传入微博 URL")
        sys.exit(1)

    # 解析 URL 并路由到对应命令
    parsed = parse_weibo_url(args.url)

    if parsed["type"] == "post":
        crawl_single_post(args.url, parsed["uid"], parsed["mid"])
    elif parsed["type"] == "user":
        crawl_user(parsed["uid"], mode=args.mode)
    else:
        print(f"无法解析 URL: {args.url}")
        print("\n支持的格式:")
        print("  https://weibo.com/u/1497035431          # 用户主页")
        print("  https://weibo.com/1497035431/AbCdEfGhI  # 单条微博")
        sys.exit(1)


if __name__ == "__main__":
    main()
