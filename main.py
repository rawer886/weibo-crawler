#!/usr/bin/env python3
"""
微博爬虫 - 命令行入口

用法:
    python main.py https://weibo.com/1497035431/AbCdEfGhI       # 抓取单条微博
    python main.py https://weibo.com/1497035431                # 批量抓取用户微博
    python main.py https://weibo.com/u/1497035431              # 批量抓取用户微博
    python main.py https://weibo.com/u/1497035431 --mode new   # 抓取最新微博
"""
import argparse
import sys
import re

from commands import crawl_single_post, crawl_user


def parse_weibo_url(url: str) -> dict:
    """解析微博 URL，返回类型和参数

    支持的格式:
    - https://weibo.com/u/1497035431          -> {"type": "user", "uid": "1497035431"}
    - https://weibo.com/1497035431            -> {"type": "user", "uid": "1497035431"}
    - https://weibo.com/1497035431/AbCdEfGhI  -> {"type": "post", "uid": "1497035431", "mid": "AbCdEfGhI"}
    """
    # 用户主页: /u/数字
    user_match = re.search(r'weibo\.com/u/(\d+)', url)
    if user_match:
        return {"type": "user", "uid": user_match.group(1)}

    # 单条微博: /数字uid/mid
    post_match = re.search(r'weibo\.com/(\d+)/(\w+)', url)
    if post_match:
        return {"type": "post", "uid": post_match.group(1), "mid": post_match.group(2)}

    # 用户主页: /数字 (不带 /u/ 前缀)
    user_short_match = re.search(r'weibo\.com/(\d+)/?$', url)
    if user_short_match:
        return {"type": "user", "uid": user_short_match.group(1)}

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
        """
    )
    parser.add_argument("url", help="微博 URL（用户主页或单条微博）")
    parser.add_argument("--mode", choices=["new", "history"], default="history",
                        help="抓取模式: history(稳定微博), new(最新微博)")

    args = parser.parse_args()

    # 解析 URL 并路由到对应命令
    parsed = parse_weibo_url(args.url)

    if parsed["type"] == "post":
        crawl_single_post(args.url, parsed["uid"], parsed["mid"])
    elif parsed["type"] == "user":
        crawl_user(parsed["uid"], mode=args.mode)
    else:
        print(f"无法解析 URL: {args.url}")
        print("\n支持的格式:")
        print("  https://weibo.com/1497035431            # 用户主页")
        print("  https://weibo.com/u/1497035431          # 用户主页")
        print("  https://weibo.com/1497035431/AbCdEfGhI  # 单条微博")
        sys.exit(1)


if __name__ == "__main__":
    main()
