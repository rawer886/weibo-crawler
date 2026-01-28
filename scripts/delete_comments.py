"""
删除指定微博的全部评论数据
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_post_with_blogger, get_comments_by_mid, delete_comments_by_mid
from display import display_post_header, display_comments, Colors


def delete_comments_for_post(mid: str):
    """删除指定微博的所有评论"""
    post = get_post_with_blogger(mid)
    comments = get_comments_by_mid(mid)

    if not comments:
        print(f"微博 {mid} 没有评论数据")
        return

    if post:
        display_post_header(post)
    else:
        print("=" * 80)
        print(f"微博ID: {mid}")
        print("微博正文: (未找到)")
        print("=" * 80)
        print()

    print(f"共找到 {len(comments)} 条评论（按热度排序）：")
    print()

    display_comments(comments)

    # 用户确认
    print()
    print(f"{Colors.RED}即将删除微博 {mid} 的全部 {len(comments)} 条评论，微博正文不会被删除{Colors.RESET}")
    response = input(f"{Colors.RED}确认删除吗？(y/n): {Colors.RESET}").strip().lower()

    if response != 'y':
        print("已取消删除")
        return

    # 执行删除
    deleted = delete_comments_by_mid(mid)
    print(f"成功删除 {deleted} 条评论")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/delete_comments.py <微博ID>")
        print("示例: python scripts/delete_comments.py 5254891884513482")
        sys.exit(1)

    delete_comments_for_post(sys.argv[1])
