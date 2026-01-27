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

    def parse_post(self, uid: str, mid: str) -> Optional[dict]:
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
                "repost_uid": post_data.get("repost_uid", ""),
                "repost_nickname": post_data.get("repost_nickname", ""),
                "images": post_data.get("images", []),
                "source_url": f"https://weibo.com/{uid}/{mid}",
            }

            repost_info = ""
            if post["is_repost"]:
                repost_info = f", 转发自={post['repost_nickname'] or '未知'}({post['repost_uid'] or '?'})"
            logger.info(f"解析成功: 内容长度={len(post['content'])}, 转发={post['reposts_count']}, "
                       f"评论={post['comments_count']}, 点赞={post['likes_count']}, 图片={len(post['images'])}张{repost_info}")
            return post

        except Exception as e:
            logger.warning(f"解析微博详情失败: {e}")
            return None

    def parse_comments(self, mid: str, blogger_uid: str) -> list:
        """解析评论列表"""
        comments = []

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)

            # 新版评论结构
            main_items = self.page.locator('.wbpro-list .item1').all()
            logger.info(f"找到 {len(main_items)} 条主评论容器")

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

        logger.info(f"获取到 {len(comments)} 条评论")
        return comments

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

            # 评论内容
            try:
                content_span = elem.locator('.text > span').first
                if content_span.count() > 0:
                    comment["content"] = content_span.text_content().strip()
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
                        comment["created_at"] = parts[0]
                        if len(parts) > 1 and ':' in parts[1]:
                            comment["created_at"] += " " + parts[1]
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
        """解析微博时间字符串"""
        if not time_str:
            return ""

        now = datetime.now()

        try:
            if "刚刚" in time_str:
                return now.isoformat()

            match = re.search(r'(\d+)\s*分钟前', time_str)
            if match:
                return (now - timedelta(minutes=int(match.group(1)))).isoformat()

            match = re.search(r'(\d+)\s*小时前', time_str)
            if match:
                return (now - timedelta(hours=int(match.group(1)))).isoformat()

            match = re.search(r'昨天\s*(\d{1,2}):(\d{2})', time_str)
            if match:
                yesterday = now - timedelta(days=1)
                return yesterday.replace(
                    hour=int(match.group(1)),
                    minute=int(match.group(2)),
                    second=0
                ).isoformat()

            match = re.match(r'^(\d{1,2})-(\d{1,2})$', time_str.strip())
            if match:
                return now.replace(
                    month=int(match.group(1)),
                    day=int(match.group(2)),
                    hour=0, minute=0, second=0
                ).isoformat()

            try:
                dt = datetime.strptime(time_str, "%a %b %d %H:%M:%S %z %Y")
                return dt.isoformat()
            except:
                pass

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
                    repost_uid: '',
                    repost_nickname: ''
                };

                // 检测转发
                const repostSelectors = ['[class*="repost"]', '[class*="Feed_repost"]', '[class*="ogText"]', '.wbpro-feed-ogText'];
                let repostArea = null;
                for (const sel of repostSelectors) {
                    repostArea = document.querySelector(sel);
                    if (repostArea) break;
                }

                if (repostArea) {
                    result.is_repost = true;

                    // 原微博内容
                    const ogSelectors = ['[class*="_wbtext_"]', '[class*="ogText"] [class*="wbtext"]'];
                    for (const sel of ogSelectors) {
                        const elem = repostArea.querySelector(sel);
                        if (elem) {
                            result.repost_content = elem.textContent.trim();
                            if (result.repost_content) break;
                        }
                    }

                    // 原微博作者
                    const authorLink = repostArea.querySelector('a[href*="/u/"], a[usercard]');
                    if (authorLink) {
                        result.repost_nickname = authorLink.textContent.trim().replace(/^@/, '');
                        const href = authorLink.getAttribute('href') || '';
                        const uidMatch = href.match(/\\/u\\/(\\d+)/);
                        if (uidMatch) result.repost_uid = uidMatch[1];
                        const usercard = authorLink.getAttribute('usercard');
                        if (usercard && /^\\d+$/.test(usercard)) result.repost_uid = usercard;
                    }

                    // 原微博图片
                    const ogPicSels = ['[class*="woo-picture-main"] img', 'img[src*="sinaimg.cn"]'];
                    for (const sel of ogPicSels) {
                        repostArea.querySelectorAll(sel).forEach(img => {
                            const src = img.src || img.getAttribute('data-src');
                            if (src && !src.includes('avatar') && !src.includes('emotion')) {
                                const largeSrc = src.replace(/\\/thumb\\d+\\//, '/large/').replace(/\\/orj\\d+\\//, '/large/').replace(/\\/mw\\d+\\//, '/large/');
                                if (!result.images.includes(largeSrc)) result.images.push(largeSrc);
                            }
                        });
                    }
                }

                // 正文内容
                const contentSelectors = ['[class*="_wbtext_"]', '[class*="detail_wbtext"]', '.wbpro-feed-content'];
                if (result.is_repost) {
                    for (const sel of contentSelectors) {
                        const elems = document.querySelectorAll(sel);
                        for (const elem of elems) {
                            if (!elem.closest('[class*="repost"]') && !elem.closest('[class*="ogText"]')) {
                                result.content = elem.textContent.trim();
                                if (result.content) break;
                            }
                        }
                        if (result.content) break;
                    }
                } else {
                    for (const sel of contentSelectors) {
                        const elem = document.querySelector(sel);
                        if (elem) {
                            result.content = elem.textContent.trim();
                            if (result.content) break;
                        }
                    }
                }

                // 发布时间
                const timeSelectors = ['[class*="_time_"]', '[class*="head-info_time"]', 'time'];
                for (const sel of timeSelectors) {
                    const elem = document.querySelector(sel);
                    if (elem) {
                        result.created_at = elem.textContent.trim();
                        if (result.created_at) break;
                    }
                }

                // 互动数据
                const footer = document.querySelector('footer[aria-label]');
                if (footer) {
                    const label = footer.getAttribute('aria-label');
                    if (label) {
                        const parts = label.split(',');
                        if (parts.length >= 3) {
                            result.reposts_count = parseInt(parts[0]) || 0;
                            result.comments_count = parseInt(parts[1]) || 0;
                            result.likes_count = parseInt(parts[2]) || 0;
                        }
                    }
                }

                // 图片
                if (!result.is_repost || result.images.length === 0) {
                    const picContainers = document.querySelectorAll('.picture, [class*="woo-picture-main"]');
                    const seenUrls = new Set(result.images);
                    picContainers.forEach(container => {
                        container.querySelectorAll('img').forEach(img => {
                            const src = img.src || img.getAttribute('data-src');
                            if (!src || !src.includes('sinaimg.cn')) return;
                            if (src.includes('avatar') || src.includes('emotion')) return;
                            const largeSrc = src.replace(/\\/thumb\\d+\\//, '/large/').replace(/\\/orj\\d+\\//, '/large/').replace(/\\/mw\\d+\\//, '/large/');
                            const imgId = largeSrc.replace(/https?:\\/\\/[^/]+/, '');
                            if (!seenUrls.has(imgId)) {
                                seenUrls.add(imgId);
                                result.images.push(largeSrc);
                            }
                        });
                    });
                }

                return result;
            }
        """
