"""
展示指定博主的最近评论，支持分页浏览
"""
import sqlite3
import sys
import os

# 添加父目录到路径，以便导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_PATH


# ANSI 颜色代码
class Colors:
    CYAN = '\033[96m'      # 青色 - 次高亮（被回复内容）
    YELLOW = '\033[93m'    # 黄色 - 高亮（评论内容）
    DIM = '\033[2m'        # 暗色 - 用于次要信息
    RESET = '\033[0m'      # 重置颜色


def truncate_text(text: str, max_length: int = 100) -> str:
    """截断文本，如果超过最大长度则添加省略号"""
    if not text:
        return ""
    # 移除换行符，保持单行显示
    text = text.replace('\n', ' ').replace('\r', '')
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


def print_comment(comment, index: int, total: int):
    """
    打印单条评论

    参数:
        comment: 评论数据
        index: 当前索引（从1开始）
        total: 总数
    """
    # 分割线
    print("-" * 80)

    # 微博正文（截断显示）
    post_content = truncate_text(comment['post_content'], 100)

    # 微博发布时间
    post_time = comment['post_created_at'] if comment['post_created_at'] else "未知"

    # 评论时间
    comment_time = comment['created_at'] if comment['created_at'] else "未知"

    # 点赞数
    likes_info = f"👍 {comment['likes_count']}"

    # 第一行：序号 + 微博ID
    print(f"[{index}/{total}] 微博ID: {comment['mid']}")

    # 第二行：微博正文 + 微博时间
    print(f"  📝 {post_content} {Colors.DIM}[{post_time}]{Colors.RESET}")

    # 第三行：评论内容（高亮）+ 点赞数 + 评论时间
    print(f"  💬 {Colors.YELLOW}{comment['content']}{Colors.RESET}  {likes_info} {Colors.DIM}[{comment_time}]{Colors.RESET}")

    # 如果是回复其他评论，显示被回复的内容（次高亮）
    if comment['reply_to_comment_id']:
        reply_to_nickname = comment['reply_to_nickname']
        if reply_to_nickname:
            reply_to_info = f"@{reply_to_nickname}"
        else:
            reply_to_info = f"@{comment['reply_to_comment_id']}"

        if comment['reply_to_content']:
            reply_content = truncate_text(comment['reply_to_content'], 80)
            print(f"  {Colors.CYAN}↳ 回复 {reply_to_info}: {reply_content}{Colors.RESET}")
        else:
            print(f"  {Colors.CYAN}↳ 回复 {reply_to_info}{Colors.RESET}")


def show_blogger_comments(uid: str):
    """
    展示指定博主的最近评论，支持分页浏览

    参数:
        uid: 博主UID
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 查询博主信息
    cursor.execute("SELECT * FROM bloggers WHERE uid = ?", (uid,))
    blogger = cursor.fetchone()

    if not blogger:
        print(f"❌ 未找到博主: {uid}")
        conn.close()
        return

    # 查询博主的所有评论，按时间降序排列
    cursor.execute("""
        SELECT c.*, p.content as post_content, p.created_at as post_created_at
        FROM comments c
        LEFT JOIN posts p ON c.mid = p.mid
        WHERE c.is_blogger_reply = 1 AND p.uid = ?
        ORDER BY c.created_at DESC
    """, (uid,))

    all_comments = cursor.fetchall()

    # 输出博主信息
    print("=" * 80)
    print(f"博主: {Colors.YELLOW}{blogger['nickname'] or uid}{Colors.RESET}")
    print(f"UID: {uid}")
    print(f"粉丝数: {blogger['followers_count'] or '未知'}")
    print("=" * 80)
    print()

    if not all_comments:
        print("❌ 该博主没有评论记录")
        conn.close()
        return

    total = len(all_comments)
    print(f"✅ 共找到 {total} 条评论，按时间倒序展示（最新在前）")
    print(f"💡 首次展示 5 条，之后按回车键继续展示（每次1条）")
    print()

    # 分页展示：首次5条，之后每次1条
    first_batch_size = 5
    displayed = 0

    # 首次展示5条
    first_batch = all_comments[:first_batch_size]
    for i, comment in enumerate(first_batch, 1):
        print_comment(comment, i, total)

    displayed = len(first_batch)

    # 之后每次展示1条
    while displayed < total:
        remaining = total - displayed
        try:
            input(f"--- 还有 {remaining} 条评论，按回车键继续，Ctrl+C 退出 ---")
        except KeyboardInterrupt:
            print("\n\n👋 已退出浏览")
            break

        comment = all_comments[displayed]
        displayed += 1
        print_comment(comment, displayed, total)

    if displayed >= total:
        print()
        print("✅ 已展示全部评论")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python show_blogger_comments.py <博主UID>")
        print("示例: python show_blogger_comments.py 1234567890")
        print()
        print("功能:")
        print("  - 输入博主UID，展示该博主的所有评论")
        print("  - 按时间倒序排列（最新评论在前）")
        print("  - 同时显示评论所属的微博正文（截断展示）")
        print("  - 首次展示5条，之后按回车键每次展示1条")
        sys.exit(1)

    uid = sys.argv[1]
    show_blogger_comments(uid)
