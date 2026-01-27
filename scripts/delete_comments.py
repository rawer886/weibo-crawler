"""
删除指定微博的全部评论数据
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_post_with_blogger, get_comments_by_mid, clear_comments_for_post
from display import display_post_header, display_comments


def delete_comments_by_mid(mid: str):
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
    print(f"即将删除微博 {mid} 的全部 {len(comments)} 条评论")
    response = input("确认删除吗？(y/n): ").strip().lower()

    if response != 'y':
        print("已取消删除")
        return

    # 执行删除
    deleted = clear_comments_for_post(mid)
    print(f"成功删除 {deleted} 条评论")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/delete_comments.py <微博ID>")
        print("示例: python scripts/delete_comments.py 5254891884513482")
        sys.exit(1)

    delete_comments_by_mid(sys.argv[1])
