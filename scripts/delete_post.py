"""
删除指定微博及其评论数据
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import (
    get_post_with_blogger,
    get_comments_by_mid,
    delete_post_only,
    delete_comments_by_mid,
)
from display import truncate_text, Colors, format_user_name, format_comment_content


def display_comments_preview(comments: list, max_display: int = 10):
    """展示评论预览"""
    if not comments:
        print("暂无评论")
        return

    print(f"\n评论列表 (共 {len(comments)} 条):")
    print("-" * 60)

    display_count = min(len(comments), max_display)
    for i, comment in enumerate(comments[:display_count], 1):
        user = format_user_name(comment)
        content = format_comment_content(comment)
        content = truncate_text(content, 60)
        likes = comment.get('likes_count', 0)
        print(f"  [{i}] {user}: {content} {Colors.GRAY}(赞{likes}){Colors.RESET}")

    if len(comments) > max_display:
        print(f"  ... 还有 {len(comments) - max_display} 条评论")


def delete_post_by_mid(mid: str):
    """删除指定微博及其所有评论"""
    post = get_post_with_blogger(mid)
    comments = get_comments_by_mid(mid)

    if not post:
        print(f"微博 {mid} 不存在")
        return

    # 展示微博信息
    print("=" * 60)
    print(f"微博ID: {mid}")
    blogger_name = post.get('blogger_nickname') or post.get('uid')
    print(f"博主: {blogger_name}")
    print(f"发布时间: {post.get('created_at', '未知')}")
    content = truncate_text(post.get('content', ''), 80)
    print(f"正文: {Colors.CYAN}{content}{Colors.RESET}")
    print(f"互动: 点赞 {post.get('likes_count', 0)} | 转发 {post.get('reposts_count', 0)} | 评论 {post.get('comments_count', 0)}")
    print("=" * 60)

    # 展示评论
    display_comments_preview(comments)

    # 用户确认
    print()
    print(f"{Colors.RED}即将删除该微博及其 {len(comments)} 条评论{Colors.RESET}")
    response = input(f"{Colors.RED}确认删除吗？(y/n): {Colors.RESET}").strip().lower()

    if response != 'y':
        print("已取消删除")
        return

    # 执行删除（先删评论，再删微博）
    deleted_comments = delete_comments_by_mid(mid)
    if delete_post_only(mid):
        print(f"已删除微博 {mid} 及其 {deleted_comments} 条评论")
    else:
        print("删除微博失败")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/delete_post.py <微博ID>")
        print("示例: python scripts/delete_post.py 5254891884513482")
        sys.exit(1)

    delete_post_by_mid(sys.argv[1])
