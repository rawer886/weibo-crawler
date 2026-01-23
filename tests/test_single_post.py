"""
测试单条微博的评论抓取
"""
import sys
import os

# 添加父目录到路径，以便导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawler import WeiboCrawler
from database import save_comment

def test_single_post_comments(uid: str, mid: str):
    """测试单条微博的评论抓取"""
    crawler = WeiboCrawler()

    try:
        crawler.start()

        # 检查登录状态
        if not crawler.check_login_status():
            print("需要登录...")
            if not crawler.login():
                print("登录失败")
                return

        print(f"开始抓取微博 {mid} 的评论...")
        comments = crawler.get_comments(uid, mid, target_count=50)

        print(f"\n获取到 {len(comments)} 条评论")

        # 保存评论
        saved_count = 0
        for comment in comments:
            print(f"\n评论: {comment['nickname']}")
            print(f"  内容: {comment['content']}")
            print(f"  UID: {comment['uid']}")
            print(f"  是否博主: {comment['is_blogger_reply']}")
            print(f"  回复给: {comment['reply_to_nickname']} (UID: {comment['reply_to_uid']})")
            print(f"  回复内容: {comment['reply_to_content']}")

            if save_comment(comment):
                saved_count += 1

        print(f"\n成功保存 {saved_count} 条评论")

    finally:
        crawler.stop()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python tests/test_single_post.py <uid> <mid>")
        print("示例: python tests/test_single_post.py 2014433131 5253489136775271")
        print("\n注意：需要先激活虚拟环境: source venv/bin/activate")
        sys.exit(1)

    uid = sys.argv[1]
    mid = sys.argv[2]
    test_single_post_comments(uid, mid)
