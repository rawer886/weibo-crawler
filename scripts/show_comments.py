"""
展示指定微博的所有评论，按热度排序，支持楼层展示
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_post_with_blogger, get_comments_by_mid
from display import display_post_header, display_comments


def show_all_comments(mid: str, blogger_only: bool = False):
    """展示特定微博的所有评论"""
    post = get_post_with_blogger(mid)

    if not post:
        print(f"未找到微博: {mid}")
        return

    display_post_header(post)

    comments = get_comments_by_mid(mid, blogger_only=blogger_only)

    if not comments:
        msg = "该微博下没有找到博主评论" if blogger_only else "该微博下没有找到评论"
        print(msg)
        return

    label = "博主评论" if blogger_only else "评论"
    print(f"共找到 {len(comments)} 条{label}（按热度排序）：")
    print()

    display_comments(comments)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="展示指定微博的所有评论，按热度排序，支持楼层展示"
    )
    parser.add_argument("mid", help="微博ID")
    parser.add_argument(
        "-b", "--blogger-only",
        action="store_true",
        help="只展示博主自己的评论"
    )

    args = parser.parse_args()
    show_all_comments(args.mid, blogger_only=args.blogger_only)
