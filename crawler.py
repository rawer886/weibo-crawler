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
    update_crawl_progress, update_post_local_images, update_post_repost_local_images,
    set_comment_pending, get_pending_comment_posts,
    clear_comment_pending, delete_comments_by_mid,
    update_comment_likes, get_next_since_id, update_next_since_id
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

    def crawl_single_post(self, uid: str, mid: str, source_url: str = None, skip_navigation: bool = False) -> dict:
        """抓取单条微博

        参数:
            skip_navigation: 跳过页面导航（当页面已在目标位置时使用）
        """
        result = {
            "post": None,
            "comments": [],
            "stats": {
                "post_saved": False,
                "comments_saved": 0,
                "comments_updated": 0,
                "images_downloaded": 0,
                "repost_images_downloaded": 0,
                "comment_images_downloaded": 0,
                "mark_pending": False
            }
        }

        # 如果没有传入 source_url，使用默认格式
        if source_url is None:
            source_url = f"https://weibo.com/{uid}/{mid}"

        # 1. 访问微博详情页（可跳过）
        if not skip_navigation:
            url = f"https://weibo.com/{uid}/{mid}"
            logger.info(f"访问微博详情页: {url}")
            self.browser.goto(url)
            time.sleep(5)

        # 2. 保存博主信息
        blogger_info = self.api.get_blogger_info(uid)
        if blogger_info:
            save_blogger(blogger_info)

        # 3. 解析微博内容
        post = self.parser.parse_post(uid, mid, source_url=source_url)
        result["post"] = post

        # 判断是否需要标记待更新
        mark_pending = False
        if post and post.get("created_at"):
            try:
                stable_days = CRAWLER_CONFIG.get("stable_days", 1)
                stable_cutoff = datetime.now() - timedelta(days=stable_days)
                post_date = datetime.strptime(post["created_at"], "%Y-%m-%d %H:%M")
                if post_date > stable_cutoff:
                    mark_pending = True
                    logger.info(f"微博发布不足 {stable_days} 天，评论将标记为待更新")
            except:
                pass

        # 3. 保存微博
        if post and post.get("content"):
            is_new = save_post(post)
            result["stats"]["post_saved"] = is_new
            content_preview = post.get("content", "")[:30] + "..." if len(post.get("content", "")) > 30 else post.get("content", "")
            if is_new:
                logger.info(f"微博已保存: {mid} - {content_preview}")
                update_crawl_progress(uid, mid, post.get("created_at", ""), is_newer=mark_pending)
            else:
                logger.info(f"微博已存在: {mid} - {content_preview}")

            # 4. 下载微博图片
            if post.get("images"):
                local_paths = self.image_downloader.download_post_images(post)
                result["stats"]["images_downloaded"] = len(local_paths)
                if local_paths:
                    update_post_local_images(mid, local_paths)

            # 5. 下载原微博图片（如果是转发）
            if post.get("repost_images"):
                repost_local_paths = self.image_downloader.download_repost_images(post)
                result["stats"]["repost_images_downloaded"] = len(repost_local_paths)
                if repost_local_paths:
                    update_post_repost_local_images(mid, repost_local_paths)
        else:
            logger.warning(f"微博内容为空，跳过保存: {mid}")

        print()

        # 6. 抓取评论（评论数为 0 时跳过）
        comments_count = post.get("comments_count", 0) if post else 0
        if comments_count > 0:
            # 滚动并点击「按热度」
            if self._scroll_and_click_hot_button():
                time.sleep(2)

            time.sleep(5)

            # 抓取评论（两轮）
            print()
            all_comments = {}
            comments, main_count = self.parser.parse_comments(mid, uid)
            for c in comments:
                if c.get("comment_id"):
                    all_comments[c["comment_id"]] = c
            logger.info(f"第 1 轮抓取: 获取 {len(comments)} 条评论, 其中 {main_count} 个主评论")

            # 滚动后再抓一轮
            if comments:
                viewport_height = self.browser.page.evaluate("() => window.innerHeight")
                scroll_distance = int(viewport_height * random.uniform(0.8, 1.0))
                self.browser.scroll_page(scroll_distance)
                time.sleep(random.uniform(2, 3))

                comments, main_count = self.parser.parse_comments(mid, uid)
                new_count = 0
                new_main_count = 0
                for c in comments:
                    cid = c.get("comment_id")
                    if cid and cid not in all_comments:
                        all_comments[cid] = c
                        new_count += 1
                        if not c.get("reply_to_comment_id"):
                            new_main_count += 1
                logger.info(f"第 2 轮抓取: 新增 {new_count} 条评论，包含 {new_main_count} 条主评论")

            # 保存评论
            comments = list(all_comments.values())
            result["comments"] = comments

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

            # 输出评论保存统计
            saved_count = result['stats']['comments_saved']
            updated_count = result['stats']['comments_updated']
            images_count = result['stats']['comment_images_downloaded']

            # 构建日志消息
            parts = []
            if saved_count > 0:
                parts.append(f"新增 {saved_count} 条")
            if updated_count > 0:
                parts.append(f"更新 {updated_count} 条点赞")
            if images_count > 0:
                parts.append(f"下载 {images_count} 张图片")

            if parts:
                logger.info(f"评论: {', '.join(parts)}")
        else:
            logger.info("评论数为 0，跳过评论抓取")

        # 7. 标记待更新（只看时间，不看评论数量）
        if mark_pending:
            set_comment_pending(mid, True)
            result["stats"]["mark_pending"] = True

        print()
        logger.info(f"微博 {mid} 抓取结束")
        return result

    def _parse_post_date(self, post: dict) -> datetime:
        """解析微博发布时间（YYYY-MM-DD HH:MM 格式），返回 None 如果解析失败"""
        created_at = post.get("created_at")
        if not created_at:
            return None
        try:
            return datetime.strptime(created_at, "%Y-%m-%d %H:%M")
        except Exception:
            return None

    def crawl_blogger(self, uid: str, mode: str = "history"):
        """抓取博主微博

        参数:
            uid: 博主ID
            mode:
                - "history": 抓取稳定微博（超过 stable_days 的历史微博）
                - "new": 抓取最新微博（stable_days 内，不使用缓存）
                - "sync": 同步校验缺失微博（使用 24h 缓存）
        """
        stable_days = CRAWLER_CONFIG.get("stable_days", 1)
        stable_cutoff = datetime.now() - timedelta(days=stable_days)

        # 获取博主信息
        logger.info(f"开始抓取博主: {uid}, 模式: {mode}")
        blogger_info = self.api.get_blogger_info(uid)
        if not blogger_info:
            logger.error(f"无法获取博主信息: {uid}")
            return
        save_blogger(blogger_info)

        # 获取已抓取的最老微博（仅供参考）
        oldest_mid = get_blogger_oldest_mid(uid)
        if oldest_mid:
            logger.info(f"已有记录 - 最老 mid: {oldest_mid}")

        posts_to_process = []

        if mode == "sync":
            # 同步模式：24h 缓存，校验并补抓缺失微博
            cache_max_age = 24 * 3600
            logger.info(f"=== 同步模式：校验缺失微博 ===")

            posts, _, _ = self.api.get_post_list(
                uid, since_id=None, check_date=True, cache_max_age=cache_max_age
            )

            for post in posts:
                if not is_post_exists(post["mid"]):
                    logger.info(f"发现缺失微博: {post['mid']}")
                    posts_to_process.append(post)

            if posts_to_process:
                logger.info(f"共发现 {len(posts_to_process)} 条缺失微博需要补抓")
            else:
                logger.info("没有缺失微博，数据完整")

        elif mode == "new":
            # 新微博模式：不使用缓存，抓取 stable_days 内的新微博
            logger.info(f"=== 抓取最新微博（{stable_days} 天内） ===")

            posts, _, _ = self.api.get_post_list(uid, since_id=None, cache_max_age=0)

            for post in posts:
                post_date = self._parse_post_date(post)
                if post_date and post_date < stable_cutoff:
                    logger.info(f"微博 {post['mid']} 已超过 {stable_days} 天，停止")
                    break

                if is_post_exists(post["mid"]):
                    logger.debug(f"微博 {post['mid']} 已存在，跳过")
                    continue

                posts_to_process.append(post)

            if posts_to_process:
                logger.info(f"发现 {len(posts_to_process)} 条新微博")
            else:
                logger.info("没有新微博")

        elif mode == "history":
            # 历史模式：先处理待更新评论，再抓取稳定微博
            self._update_pending_comments(uid, stable_days)

            # 获取断点续抓的 since_id（API 分页游标）
            next_since_id = get_next_since_id(uid)
            if next_since_id:
                logger.info(f"从断点继续 (since_id: {next_since_id})\n")
            else:
                logger.info("首次抓取，从头开始\n")

            posts, new_since_id, reached_cutoff = self.api.get_post_list(
                uid, since_id=next_since_id, check_date=True
            )

            for post in posts:
                if is_post_exists(post["mid"]):
                    continue

                post_date = self._parse_post_date(post)
                if post_date and post_date > stable_cutoff:
                    logger.debug(f"微博 {post['mid']} 发布不足 {stable_days} 天，跳过")
                    continue

                posts_to_process.append(post)

            if posts_to_process:
                logger.info(f"获取到 {len(posts_to_process)} 条稳定微博\n")
                logger.info("-" * 50)

            # 保存下一页的 since_id 用于断点续抓
            if new_since_id:
                update_next_since_id(uid, new_since_id)

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

    def _update_pending_comments(self, uid: str, stable_days: int):
        """更新待更新评论的微博"""
        pending_posts = get_pending_comment_posts(uid, stable_days)
        if not pending_posts:
            return

        logger.info(f"=== 发现 {len(pending_posts)} 条微博需要更新评论 ===")
        for post in pending_posts:
            mid = post["mid"]
            logger.info(f"更新微博 {mid} 的评论...")

            old_count = delete_comments_by_mid(mid)
            logger.info(f"清除旧评论 {old_count} 条")

            result = self.crawl_single_post(uid, mid)
            logger.info(f"保存了 {result['stats']['comments_saved']} 条新评论")

            clear_comment_pending(mid)
            self._random_delay()

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
