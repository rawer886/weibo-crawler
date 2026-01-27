"""
微博爬虫核心模块

职责：
- 协调各模块完成爬虫任务
- 单条微博抓取流程
- 博主批量抓取流程
"""
import logging
import os
import random
import signal
import time
from datetime import datetime, timedelta

from config import CRAWLER_CONFIG, LOG_CONFIG
from database import (
    init_database, save_blogger, save_post, save_comment,
    is_post_exists, get_blogger_oldest_mid, get_blogger_newest_mid,
    update_crawl_progress, update_post_local_images,
    set_comment_pending, get_pending_comment_posts,
    clear_comment_pending, clear_comments_for_post,
    update_comment_likes
)
from browser import BrowserManager
from api import WeiboAPI
from parser import PageParser
from image import ImageDownloader


# 信号处理
_stopping = False


def _signal_handler(signum, frame):
    global _stopping
    if _stopping:
        print("\n强制退出...")
        os._exit(1)
    _stopping = True
    print("\n\n收到停止信号，正在关闭... (再按一次强制退出)")
    os._exit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# 配置日志
logging.basicConfig(
    level=getattr(logging, LOG_CONFIG["level"]),
    format=LOG_CONFIG["format"],
    handlers=[
        logging.FileHandler(LOG_CONFIG["file"], encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class WeiboCrawler:
    """微博爬虫"""

    def __init__(self):
        init_database()

        self.browser = BrowserManager()
        self.api = WeiboAPI()
        self.parser = None  # 需要 page 初始化
        self.image_downloader = ImageDownloader()

    def start(self, url: str = None):
        """启动浏览器"""
        self.browser.start(url)
        self.parser = PageParser(self.browser.page)
        self.image_downloader.set_page(self.browser.page)

    def stop(self):
        """停止浏览器"""
        self.browser.stop()

    def login(self) -> bool:
        """登录"""
        result = self.browser.login()
        if result:
            self.api.set_cookies(self.browser.cookies_for_request)
        return result

    def check_login_status(self) -> bool:
        """检查登录状态"""
        result = self.browser.check_login_status()
        if result:
            self.api.set_cookies(self.browser.cookies_for_request)
        return result

    def parse_numeric_mid_from_page(self) -> str:
        """从当前页面解析数字 mid"""
        return self.parser.parse_numeric_mid()

    def crawl_single_post(self, uid: str, mid: str) -> dict:
        """抓取单条微博"""
        result = {
            "post": None,
            "comments": [],
            "stats": {
                "post_saved": False,
                "comments_saved": 0,
                "comments_updated": 0,
                "images_downloaded": 0,
                "comment_images_downloaded": 0,
                "mark_pending": False
            }
        }

        # 1. 访问详情页
        url = f"https://weibo.com/{uid}/{mid}"
        if mid not in self.browser.page.url:
            logger.info(f"访问微博详情页: {url}")
            self.browser.goto(url)
            time.sleep(5)

        # 2. 解析微博内容
        post = self.parser.parse_post(uid, mid)
        result["post"] = post

        # 判断是否需要标记待更新
        mark_pending = False
        if post and post.get("created_at"):
            try:
                stable_days = CRAWLER_CONFIG.get("stable_days", 1)
                stable_cutoff = datetime.now() - timedelta(days=stable_days)
                post_date = datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
                if post_date.replace(tzinfo=None) > stable_cutoff:
                    mark_pending = True
                    logger.info(f"微博发布不足 {stable_days} 天，评论将标记为待更新")
            except:
                pass

        # 3. 保存微博
        if post and post.get("content"):
            is_new = save_post(post)
            result["stats"]["post_saved"] = is_new
            if is_new:
                logger.info(f"微博已保存: {mid}")
                update_crawl_progress(uid, mid, post.get("created_at", ""), is_newer=mark_pending)

            # 4. 下载微博图片
            if post.get("images"):
                local_paths = self.image_downloader.download_post_images(post)
                result["stats"]["images_downloaded"] = len(local_paths)
                if local_paths:
                    update_post_local_images(mid, local_paths)
        else:
            logger.warning(f"微博内容为空，跳过保存: {mid}")

        # 5. 滚动并点击「按热度」
        if self._scroll_and_click_hot_button():
            time.sleep(2)

        time.sleep(5)

        # 6. 抓取评论（两轮）
        all_comments = {}
        comments = self.parser.parse_comments(mid, uid)
        for c in comments:
            if c.get("comment_id"):
                all_comments[c["comment_id"]] = c
        logger.info(f"第 1 轮抓取: 获取 {len(comments)} 条评论")

        # 7. 滚动后再抓一轮
        if comments:
            logger.info("模拟用户滚动页面...")
            viewport_height = self.browser.page.evaluate("() => window.innerHeight")
            scroll_distance = int(viewport_height * random.uniform(0.8, 1.0))
            self.browser.scroll_page(scroll_distance)
            time.sleep(random.uniform(2, 3))

            comments = self.parser.parse_comments(mid, uid)
            new_count = 0
            for c in comments:
                cid = c.get("comment_id")
                if cid and cid not in all_comments:
                    all_comments[cid] = c
                    new_count += 1
            logger.info(f"第 2 轮抓取: 获取 {len(comments)} 条，新增 {new_count} 条")

        # 8. 保存评论
        comments = list(all_comments.values())
        result["comments"] = comments
        logger.info(f"评论抓取完成，共 {len(comments)} 条")

        for comment in comments:
            # 下载评论图片
            if comment.get("images"):
                local_paths = self.image_downloader.download_comment_images(comment, uid)
                if local_paths:
                    comment["local_images"] = local_paths
                    result["stats"]["comment_images_downloaded"] += len(local_paths)

            # 保存评论
            if save_comment(comment):
                result["stats"]["comments_saved"] += 1
            else:
                if update_comment_likes(comment["comment_id"], comment.get("likes_count", 0)):
                    result["stats"]["comments_updated"] += 1

        logger.info(f"新增 {result['stats']['comments_saved']} 条评论，"
                   f"更新 {result['stats']['comments_updated']} 条点赞数")

        # 9. 标记待更新
        if mark_pending and result["stats"]["comments_saved"] > 0:
            set_comment_pending(mid, True)
            result["stats"]["mark_pending"] = True

        return result

    def crawl_blogger(self, uid: str, mode: str = "history"):
        """抓取博主微博

        参数:
            uid: 博主ID
            mode: "history" 抓取稳定微博，"new" 抓取最新微博
        """
        logger.info(f"开始抓取博主: {uid}, 模式: {mode}")

        stable_days = CRAWLER_CONFIG.get("stable_days", 1)

        # 获取博主信息
        blogger_info = self.api.get_blogger_info(uid)
        if not blogger_info:
            logger.error(f"无法获取博主信息: {uid}")
            return
        save_blogger(blogger_info)

        # 获取抓取边界
        newest_mid = get_blogger_newest_mid(uid)
        oldest_mid = get_blogger_oldest_mid(uid)
        logger.info(f"已有记录 - 最新: {newest_mid}, 最老: {oldest_mid}")

        posts_to_process = []

        if mode == "new":
            # 抓取新微博
            logger.info("=== 抓取最新微博 ===")
            posts, _, _ = self.api.get_post_list(uid, since_id=None)

            for post in posts:
                if is_post_exists(post["mid"]):
                    logger.info(f"遇到已入库微博 {post['mid']}，停止")
                    break
                posts_to_process.append(post)

            if posts_to_process:
                logger.info(f"发现 {len(posts_to_process)} 条新微博")
            else:
                logger.info("没有新微博")

        elif mode == "history":
            # 先处理待更新评论
            pending_posts = get_pending_comment_posts(uid, stable_days)
            if pending_posts:
                logger.info(f"=== 发现 {len(pending_posts)} 条微博需要更新评论 ===")
                for post in pending_posts:
                    mid = post["mid"]
                    logger.info(f"更新微博 {mid} 的评论...")

                    old_count = clear_comments_for_post(mid)
                    logger.info(f"清除旧评论 {old_count} 条")

                    result = self.crawl_single_post(uid, mid)
                    logger.info(f"保存了 {result['stats']['comments_saved']} 条新评论")

                    clear_comment_pending(mid)
                    self._random_delay()

            # 抓取稳定微博
            logger.info(f"=== 抓取稳定微博（发布超过 {stable_days} 天） ===")
            posts, _, reached_cutoff = self.api.get_post_list(uid, since_id=oldest_mid, check_date=True)

            stable_cutoff = datetime.now() - timedelta(days=stable_days)

            for post in posts:
                if is_post_exists(post["mid"]):
                    continue

                if post.get("created_at"):
                    try:
                        post_date = datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
                        if post_date.replace(tzinfo=None) > stable_cutoff:
                            logger.debug(f"微博 {post['mid']} 发布不足 {stable_days} 天，跳过")
                            continue
                    except:
                        pass

                posts_to_process.append(post)

            if posts_to_process:
                logger.info(f"获取到 {len(posts_to_process)} 条稳定微博")

            if reached_cutoff:
                logger.info(f"博主 {uid} 的历史微博已全部抓取完成")

        if not posts_to_process:
            logger.info(f"博主 {uid} 没有需要处理的新微博")
            return

        # 处理每条微博
        for i, post in enumerate(posts_to_process):
            mid = post["mid"]
            logger.info(f"处理第 {i+1}/{len(posts_to_process)} 条微博: {mid}")
            self.crawl_single_post(uid, mid)
            self._random_delay()

        logger.info(f"博主 {uid} 抓取完成")

    def _scroll_and_click_hot_button(self) -> bool:
        """滚动并点击「按热度」按钮"""
        try:
            hot_btn = self.browser.page.locator('text="按热度"').first

            if hot_btn.count() == 0:
                logger.info("未找到「按热度」按钮")
                return False

            logger.info("滚动到「按热度」按钮...")
            self.browser.smooth_scroll_to_element(hot_btn)

            try:
                hot_btn.wait_for(state="visible", timeout=3000)
                hot_btn.click()
                logger.info("已点击「按热度」按钮")
                self.browser.page.wait_for_load_state("networkidle", timeout=5000)
                return True
            except:
                logger.warning("按钮无法点击")
                return False

        except Exception as e:
            logger.warning(f"操作失败: {e}")
            return False

    def _random_delay(self, base_delay: float = None):
        """随机延迟"""
        base = base_delay or CRAWLER_CONFIG["delay"]
        delay = random.uniform(base * 0.5, base * 1.5)
        logger.debug(f"等待 {delay:.1f} 秒...")
        time.sleep(delay)
