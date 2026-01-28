"""
页面解析模块

职责：
- 详情页微博内容解析
- 评论 DOM 解析
- 时间格式转换
"""
import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class PageParser:
    """页面解析器"""

    def __init__(self, page):
        """
        参数:
            page: Playwright Page 对象
        """
        self.page = page

    def parse_numeric_mid(self) -> str:
        """从当前页面解析数字格式的 mid

        异常:
            ValueError: 无法解析 mid
        """
        dom_data = self.page.evaluate("""
            () => {
                const header = document.querySelector('header[id][userinfo]');
                if (header) {
                    const mid = header.getAttribute('id');
                    if (mid && /^\\d+$/.test(mid)) {
                        return { mid };
                    }
                }
                const weiboItem = document.querySelector('[mid]');
                if (weiboItem) {
                    return { mid: weiboItem.getAttribute('mid') };
                }
                return null;
            }
        """)

        if dom_data and dom_data.get('mid'):
            return dom_data['mid']

        raise ValueError("无法从 DOM 解析数字 mid")

    def parse_post(self, uid: str, mid: str, source_url: str = None) -> Optional[dict]:
        """从详情页解析微博信息"""
        logger.info(f"从详情页解析微博信息: {mid}")

        try:
            # 等待页面加载
            try:
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except:
                logger.debug("等待networkidle超时，继续解析")

            try:
                self.page.wait_for_selector(
                    '[class*="detail_wbtext"], [class*="toolbar"], footer',
                    timeout=5000, state="attached"
                )
            except:
                logger.debug("等待关键元素超时，尝试继续解析")

            # 从 DOM 提取数据
            post_data = self.page.evaluate(self._get_post_parse_script())

            if not post_data:
                logger.warning("无法从页面解析微博数据")
                return None

            post = {
                "mid": str(mid),
                "uid": uid,
                "content": post_data.get("content", ""),
                "created_at": self._parse_weibo_time(post_data.get("created_at", "")),
                "reposts_count": post_data.get("reposts_count", 0),
                "comments_count": post_data.get("comments_count", 0),
                "likes_count": post_data.get("likes_count", 0),
                "is_repost": post_data.get("is_repost", False),
                "repost_content": post_data.get("repost_content", ""),
                "repost_images": post_data.get("repost_images", []),
                "repost_video": post_data.get("repost_video"),
                "images": post_data.get("images", []),
                "video": post_data.get("video"),
                "source_url": source_url or f"https://weibo.com/{uid}/{mid}",
            }

            log_msg = (f"解析成功: 内容长度={len(post['content'])}, 转发={post['reposts_count']}, "
                       f"评论={post['comments_count']}, 点赞={post['likes_count']}, 图片={len(post['images'])}张")
            if post.get("video"):
                log_msg += ", 视频=1个"
            if post["is_repost"]:
                log_msg += f", 原微博图片={len(post['repost_images'])}张"
                if post.get("repost_video"):
                    log_msg += ", 原微博视频=1个"
            logger.info(log_msg)
            return post

        except Exception as e:
            logger.warning(f"解析微博详情失败: {e}")
            return None

    def parse_comments(self, mid: str, blogger_uid: str) -> tuple:
        """解析评论列表

        返回:
            (comments, main_count): 评论列表和主评论容器数
        """
        comments = []
        main_count = 0

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)

            # 新版评论结构
            main_items = self.page.locator('.wbpro-list .item1').all()
            main_count = len(main_items)

            for item in main_items:
                main_con = item.locator('.con1').first
                if main_con.count() > 0:
                    main_comment = self._parse_comment_element(main_con, mid, blogger_uid)
                    if main_comment:
                        comments.append(main_comment)

                        # 子评论
                        sub_items = item.locator('.list2 .item2').all()
                        for sub_item in sub_items:
                            sub_con = sub_item.locator('.con2').first
                            if sub_con.count() > 0:
                                sub_comment = self._parse_comment_element(
                                    sub_con, mid, blogger_uid,
                                    is_sub=True, parent=main_comment
                                )
                                if sub_comment:
                                    comments.append(sub_comment)

        except Exception as e:
            logger.warning(f"评论解析失败: {e}")

        return comments, main_count

    def _parse_comment_element(self, elem, mid: str, blogger_uid: str,
                                is_sub: bool = False, parent: dict = None) -> Optional[dict]:
        """解析单条评论元素"""
        try:
            comment = {
                "mid": mid,
                "comment_id": None,
                "uid": None,
                "nickname": None,
                "content": None,
                "created_at": None,
                "likes_count": 0,
                "is_blogger_reply": False,
                "reply_to_comment_id": None,
                "reply_to_uid": None,
                "reply_to_nickname": None,
                "images": [],
            }

            # 获取真实 comment_id
            try:
                parent_item = elem.locator('xpath=ancestor::div[contains(@class,"item1") or contains(@class,"item2")]').first
                if parent_item.count() > 0:
                    real_id = (
                        parent_item.get_attribute("mid") or
                        parent_item.get_attribute("comment-id") or
                        parent_item.get_attribute("data-mid") or
                        parent_item.get_attribute("data-id")
                    )
                    if real_id:
                        comment["comment_id"] = real_id
            except:
                pass

            # 父评论关系
            if is_sub and parent:
                comment["reply_to_comment_id"] = parent.get("comment_id")
                comment["reply_to_uid"] = parent.get("uid")
                comment["reply_to_nickname"] = parent.get("nickname")

            # 用户信息
            try:
                user_link = elem.locator('.text > a[usercard]').first
                if user_link.count() > 0:
                    comment["uid"] = user_link.get_attribute("usercard")
                    comment["nickname"] = user_link.text_content().strip()
                    if comment["uid"] == blogger_uid:
                        comment["is_blogger_reply"] = True
            except:
                pass

            # 评论内容（包括表情）
            try:
                content_span = elem.locator('.text > span').first
                if content_span.count() > 0:
                    # 先尝试获取纯文本
                    text = content_span.text_content().strip()
                    if text:
                        comment["content"] = text
                    else:
                        # 纯表情评论：提取 img 的 alt 属性
                        emojis = []
                        for img in content_span.locator('img').all():
                            alt = img.get_attribute('alt')
                            if alt:
                                emojis.append(alt)
                        if emojis:
                            comment["content"] = ''.join(emojis)
            except:
                pass

            # 评论图片
            try:
                img_elems = elem.locator('.woo-picture-main .woo-picture-img').all()
                for img in img_elems:
                    src = img.get_attribute("src")
                    if src and ("sinaimg.cn" in src or "weibo.cn" in src):
                        large_src = self._normalize_image_url(src)
                        if large_src not in comment["images"]:
                            comment["images"].append(large_src)
            except:
                pass

            # 时间
            try:
                info_elem = elem.locator('.info').first
                if info_elem.count() > 0:
                    info_text = info_elem.text_content().strip()
                    parts = info_text.split()
                    if parts:
                        raw_time = parts[0]
                        if len(parts) > 1 and ':' in parts[1]:
                            raw_time += " " + parts[1]
                        comment["created_at"] = self._parse_weibo_time(raw_time)
            except:
                pass

            # 点赞数
            try:
                parent_item = elem.locator('xpath=ancestor::div[contains(@class,"item1") or contains(@class,"item2")]').first
                if parent_item.count() > 0:
                    like_elem = parent_item.locator('.woo-like-count').first
                    if like_elem.count() > 0:
                        like_text = like_elem.text_content().strip()
                        if like_text and like_text.isdigit():
                            comment["likes_count"] = int(like_text)
            except:
                pass

            # 生成 ID
            if comment["content"]:
                if not comment["comment_id"]:
                    content_key = comment['content'] + (comment['uid'] or '')
                    content_hash = hashlib.md5(content_key.encode('utf-8')).hexdigest()[:16]
                    comment["comment_id"] = f"{mid}_{content_hash}"
                return comment

            return None

        except Exception as e:
            logger.debug(f"解析评论失败: {e}")
            return None

    def _normalize_image_url(self, url: str) -> str:
        """将缩略图URL转换为大图URL"""
        return url.replace("/orj360/", "/large/") \
                  .replace("/mw690/", "/large/") \
                  .replace("/thumbnail/", "/large/") \
                  .replace("/orj480/", "/large/") \
                  .replace("/thumb150/", "/large/") \
                  .replace("/thumb180/", "/large/")

    def _parse_weibo_time(self, time_str: str) -> str:
        """解析微博时间字符串，统一输出为 YYYY-MM-DD HH:MM 格式"""
        if not time_str:
            return ""

        now = datetime.now()
        dt = None

        try:
            if "刚刚" in time_str:
                dt = now

            if not dt:
                match = re.search(r'(\d+)\s*分钟前', time_str)
                if match:
                    dt = now - timedelta(minutes=int(match.group(1)))

            if not dt:
                match = re.search(r'(\d+)\s*小时前', time_str)
                if match:
                    dt = now - timedelta(hours=int(match.group(1)))

            if not dt:
                match = re.search(r'昨天\s*(\d{1,2}):(\d{2})', time_str)
                if match:
                    yesterday = now - timedelta(days=1)
                    dt = yesterday.replace(
                        hour=int(match.group(1)),
                        minute=int(match.group(2)),
                        second=0
                    )

            if not dt:
                match = re.match(r'^(\d{1,2})-(\d{1,2})$', time_str.strip())
                if match:
                    dt = now.replace(
                        month=int(match.group(1)),
                        day=int(match.group(2)),
                        hour=0, minute=0, second=0
                    )

            # YY-M-D HH:MM 或 YY-MM-DD HH:MM 格式（两位数年份），转换为四位数年份
            if not dt:
                match = re.match(r'^(\d{2})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})$', time_str.strip())
                if match:
                    year, month, day, hour, minute = match.groups()
                    full_year = 2000 + int(year)
                    return f"{full_year}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{minute}"

            # YYYY-MM-DD HH:MM 格式（四位数年份），已是目标格式
            if not dt:
                match = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})$', time_str.strip())
                if match:
                    year, month, day, hour, minute = match.groups()
                    return f"{year}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{minute}"

            if not dt:
                try:
                    dt = datetime.strptime(time_str, "%a %b %d %H:%M:%S %z %Y")
                    dt = dt.replace(tzinfo=None)
                except:
                    pass

            if dt:
                return dt.strftime("%Y-%m-%d %H:%M")

            return time_str
        except:
            return time_str

    def _get_post_parse_script(self) -> str:
        """返回解析微博详情页的 JavaScript 代码"""
        return """
            () => {
                const result = {
                    content: '',
                    created_at: '',
                    reposts_count: 0,
                    comments_count: 0,
                    likes_count: 0,
                    images: [],
                    is_repost: false,
                    repost_content: '',
                    repost_images: [],
                    video: null,
                    repost_video: null
                };

                // 辅助函数：检查元素是否在转发区块内
                function isInRetweet(elem) {
                    return elem.closest('.retweet, [class*="_retweet_m"]') !== null;
                }

                // 辅助函数：检查元素是否在视频区块内
                function isInVideoBox(elem) {
                    return elem.closest('[class*="_videoBox_"], [class*="videoBox"]') !== null;
                }

                // 辅助函数：转换缩略图为大图 URL
                function toLargeUrl(src) {
                    return src.replace(/\\/thumb\\d+\\//, '/large/')
                              .replace(/\\/orj\\d+\\//, '/large/')
                              .replace(/\\/mw\\d+\\//, '/large/');
                }

                // 辅助函数：检查是否为有效图片 URL
                function isValidImageUrl(src) {
                    return src && src.includes('sinaimg.cn') &&
                           !src.includes('avatar') && !src.includes('emotion');
                }

                // 辅助函数：解析视频信息
                function parseVideo(container) {
                    if (!container) return null;

                    const video = {};

                    const videoElem = container.querySelector('video');
                    if (videoElem) {
                        let src = videoElem.src || videoElem.getAttribute('src');
                        if (src) {
                            video.url = src.startsWith('//') ? 'https:' + src : src;
                        }
                    }

                    const posterImg = container.querySelector('.vjs-poster img');
                    if (posterImg) {
                        const coverSrc = posterImg.src || posterImg.getAttribute('src');
                        if (coverSrc) {
                            video.cover = toLargeUrl(coverSrc);
                        }
                    }

                    const durElem = container.querySelector('[class*="_dur_"] span');
                    if (durElem) {
                        video.duration = durElem.textContent.trim();
                    }

                    return (video.url || video.cover) ? video : null;
                }

                // 辅助函数：收集图片 URL
                function collectImages(container, targetArray, seenUrls = null) {
                    container.querySelectorAll('img').forEach(img => {
                        const src = img.src || img.getAttribute('data-src');
                        if (!isValidImageUrl(src)) return;

                        const largeSrc = toLargeUrl(src);
                        if (seenUrls) {
                            const imgId = largeSrc.replace(/https?:\\/\\/[^/]+/, '');
                            if (seenUrls.has(imgId)) return;
                            seenUrls.add(imgId);
                        } else if (targetArray.includes(largeSrc)) {
                            return;
                        }
                        targetArray.push(largeSrc);
                    });
                }

                // 检测转发区块
                const retweetArea = document.querySelector('.retweet, [class*="_retweet_m"]');

                if (retweetArea) {
                    result.is_repost = true;

                    // 原微博内容
                    const reTextElem = retweetArea.querySelector('[class*="_wbtext_"], [class*="wbtext"]');
                    if (reTextElem) {
                        result.repost_content = reTextElem.textContent.trim();
                    }

                    // 原微博图片
                    retweetArea.querySelectorAll('[class*="woo-picture-main"], .picture').forEach(container => {
                        collectImages(container, result.repost_images);
                    });

                    // 原微博视频
                    const repostVideoBox = retweetArea.querySelector('[class*="_videoBox_"], [class*="videoBox"]');
                    result.repost_video = parseVideo(repostVideoBox);
                }

                // 博主正文内容（不在转发区块内）
                const contentSelectors = [
                    '.wbpro-feed-ogText [class*="_wbtext_"]',
                    '[class*="detail_wbtext"]',
                    '.wbpro-feed-content [class*="_wbtext_"]'
                ];
                for (const sel of contentSelectors) {
                    const elem = document.querySelector(sel);
                    if (elem && !isInRetweet(elem)) {
                        result.content = elem.textContent.trim();
                        if (result.content) break;
                    }
                }

                // 发布时间（不在转发区块内）
                const headerTimeElem = document.querySelector('header [class*="_time_"]');
                if (headerTimeElem) {
                    result.created_at = headerTimeElem.textContent.trim();
                } else {
                    for (const elem of document.querySelectorAll('[class*="_time_"]')) {
                        if (!isInRetweet(elem)) {
                            result.created_at = elem.textContent.trim();
                            if (result.created_at) break;
                        }
                    }
                }

                // 互动数据（最后一个不在转发区块内的 footer）
                let targetFooter = null;
                for (const footer of document.querySelectorAll('footer[aria-label]')) {
                    if (!isInRetweet(footer)) {
                        targetFooter = footer;
                    }
                }
                if (!targetFooter) {
                    targetFooter = document.querySelector('[class*="_body_"] > footer[aria-label]');
                }
                if (targetFooter) {
                    const parts = (targetFooter.getAttribute('aria-label') || '').split(',');
                    if (parts.length >= 3) {
                        result.reposts_count = parseInt(parts[0]) || 0;
                        result.comments_count = parseInt(parts[1]) || 0;
                        result.likes_count = parseInt(parts[2]) || 0;
                    }
                }

                // 博主微博的图片（不在转发区块和视频区块内）
                const seenUrls = new Set();
                document.querySelectorAll('.picture, [class*="woo-picture-main"]').forEach(container => {
                    if (isInRetweet(container) || isInVideoBox(container)) return;
                    collectImages(container, result.images, seenUrls);
                });

                // 博主微博的视频（不在转发区块内）
                for (const box of document.querySelectorAll('[class*="_videoBox_"], [class*="videoBox"]')) {
                    if (isInRetweet(box)) continue;
                    result.video = parseVideo(box);
                    if (result.video) break;
                }

                return result;
            }
        """
