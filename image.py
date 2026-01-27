"""
图片下载模块

职责：
- 微博图片下载
- 评论图片下载
- 从浏览器缓存获取图片
"""
import base64
import logging
import os
from datetime import datetime
from typing import Optional, List

import requests

from config import CRAWLER_CONFIG

logger = logging.getLogger(__name__)


class ImageDownloader:
    """图片下载器"""

    def __init__(self, page=None):
        """
        参数:
            page: Playwright Page 对象（可选，用于从浏览器缓存获取图片）
        """
        self.page = page

    def set_page(self, page):
        """设置 Page 对象"""
        self.page = page

    def download_post_images(self, post: dict) -> List[str]:
        """下载微博图片

        目录结构: images/{uid}/{YY-MM}/{mid}_{index}.jpg
        """
        date_str = self._parse_date(post.get("created_at", ""))
        return self._download_images(
            images=post.get("images", []),
            uid=post["uid"],
            date_str=date_str,
            prefix="",
            entity_id=post["mid"]
        )

    def download_comment_images(self, comment: dict, post_uid: str) -> List[str]:
        """下载评论图片

        目录结构: images/{uid}/{YY-MM}/comment_{comment_id}_{index}.jpg
        """
        date_str = self._parse_date(comment.get("created_at", ""), is_comment=True)
        return self._download_images(
            images=comment.get("images", []),
            uid=post_uid,
            date_str=date_str,
            prefix="comment_",
            entity_id=comment["comment_id"]
        )

    def _download_images(self, images: list, uid: str, date_str: str,
                         prefix: str, entity_id: str) -> List[str]:
        """通用图片下载方法"""
        if not CRAWLER_CONFIG.get("download_images", False):
            return []

        if not images:
            return []

        save_dir = os.path.join(
            CRAWLER_CONFIG.get("images_dir", "images"),
            uid,
            date_str
        )
        os.makedirs(save_dir, exist_ok=True)

        local_paths = []
        log_prefix = "评论图片" if prefix else "图片"

        for i, img_url in enumerate(images):
            try:
                ext = self._get_extension(img_url)
                filename = f"{prefix}{entity_id}_{i+1}{ext}"
                filepath = os.path.join(save_dir, filename)

                if os.path.exists(filepath):
                    logger.debug(f"{log_prefix}已存在: {filename}")
                    local_paths.append(filepath)
                    continue

                # 尝试从浏览器获取
                img_data = self._get_from_browser(img_url)

                if img_data:
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    local_paths.append(filepath)
                    logger.debug(f"{log_prefix}已保存（浏览器缓存）: {filename}")
                else:
                    # 回退到 HTTP
                    img_data = self._download_via_http(img_url)
                    if img_data:
                        with open(filepath, "wb") as f:
                            f.write(img_data)
                        local_paths.append(filepath)
                        logger.debug(f"{log_prefix}已保存（HTTP）: {filename}")

            except Exception as e:
                logger.warning(f"下载{log_prefix}失败: {e}")

        if local_paths:
            logger.info(f"下载了 {len(local_paths)} 张{log_prefix}到 {save_dir}")

        return local_paths

    def _get_from_browser(self, img_url: str) -> Optional[bytes]:
        """从浏览器缓存获取图片"""
        if not self.page:
            return None

        try:
            js_code = """
            (url) => {
                const urlBase = url.replace(/\\/(large|orj360|mw690|thumbnail)\\//, '/PLACEHOLDER/');
                const imgs = document.querySelectorAll('img');

                for (const img of imgs) {
                    const src = img.src || '';
                    const srcBase = src.replace(/\\/(large|orj360|mw690|thumbnail)\\//, '/PLACEHOLDER/');

                    if (srcBase === urlBase || src === url) {
                        if (img.complete && img.naturalWidth > 0) {
                            try {
                                const canvas = document.createElement('canvas');
                                canvas.width = img.naturalWidth;
                                canvas.height = img.naturalHeight;
                                const ctx = canvas.getContext('2d');
                                ctx.drawImage(img, 0, 0);
                                return canvas.toDataURL('image/jpeg', 0.95);
                            } catch(e) {
                                continue;
                            }
                        }
                    }
                }
                return null;
            }
            """
            result = self.page.evaluate(js_code, img_url)

            if result and result.startswith('data:image'):
                base64_data = result.split(',')[1]
                return base64.b64decode(base64_data)

        except Exception as e:
            logger.debug(f"从浏览器缓存获取图片失败: {e}")

        return None

    def _download_via_http(self, url: str) -> Optional[bytes]:
        """通过 HTTP 下载图片"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://weibo.com/"
            }
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.content
        except Exception as e:
            logger.debug(f"HTTP下载失败: {e}")
        return None

    def _get_extension(self, url: str) -> str:
        """从 URL 推断文件扩展名"""
        url_lower = url.lower()
        if ".png" in url_lower:
            return ".png"
        elif ".gif" in url_lower:
            return ".gif"
        elif ".webp" in url_lower:
            return ".webp"
        return ".jpg"

    def _parse_date(self, created_at: str, is_comment: bool = False) -> str:
        """解析日期字符串，返回 YY-MM 格式用于图片存储目录"""
        try:
            # 统一格式: "26-01-27 17:14" -> "26-01"
            if "-" in created_at:
                parts = created_at.split()[0].split("-")
                if len(parts) == 3:
                    return f"{parts[0]}-{parts[1]}"
        except:
            pass
        return datetime.now().strftime("%y-%m")
