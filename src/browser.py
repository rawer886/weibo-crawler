"""
浏览器控制模块

职责：
- Playwright 浏览器启动/停止
- Cookie 管理（加载/保存）
- 登录状态检查
"""
import json
import os
from typing import Optional

from playwright.sync_api import sync_playwright, Page, Browser

from .config import CRAWLER_CONFIG, COOKIE_FILE
from .logger import get_logger
from .utils import random_delay

logger = get_logger(__name__)


class BrowserManager:
    """浏览器管理器"""

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.is_logged_in = False
        self.headless = False
        self.cookies_for_request = {}  # 用于 requests 库的 cookies

    def start(self, url: str = None):
        """启动浏览器

        参数:
            url: 可选，启动后直接访问的URL
        """
        logger.info("启动浏览器...")
        self.playwright = sync_playwright().start()

        # 动态判断无头模式：无 cookie 时强制可见，方便登录
        headless = CRAWLER_CONFIG["headless"]
        if headless and not os.path.exists(COOKIE_FILE):
            logger.info("未找到 cookies，自动关闭无头模式")
            headless = False

        self._open_browser(headless)

        # 加载已保存的 cookies
        self._load_cookies()

        if url:
            logger.info(f"访问页面: {url}")
            self.page.goto(url)

    def _open_browser(self, headless: bool):
        """按指定模式打开浏览器窗口"""
        # 获取屏幕尺寸，根据配置的比例计算视口大小
        viewport_height = 900
        viewport_width = 720
        width_ratio = CRAWLER_CONFIG.get("browser_width_ratio", 0.5)
        height_ratio = CRAWLER_CONFIG.get("browser_height_ratio", 1.0)
        try:
            from screeninfo import get_monitors
            monitors = get_monitors()
            if monitors:
                primary = monitors[0]
                # 可用高度 = 屏幕高度 - 系统栏(约130px)
                available_height = primary.height - 130
                available_width = primary.width
                viewport_height = int(available_height * height_ratio)
                viewport_width = int(available_width * width_ratio)
                if not headless:
                    logger.info(f"检测到显示器: {primary.width}x{primary.height}, 设置视口: {viewport_width}x{viewport_height}")
        except ImportError:
            logger.debug("screeninfo 未安装，使用默认视口大小")
        except Exception as e:
            logger.debug(f"获取显示器尺寸失败: {e}")

        # 启动浏览器
        self.browser = self.playwright.chromium.launch(
            headless=headless,
            args=[
                f"--window-size={viewport_width},{viewport_height + 28}",
                "--window-position=0,25",
            ]
        )

        self.headless = headless
        self.page = self.browser.new_page(viewport={"width": viewport_width, "height": viewport_height})
        self.page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    def _ensure_visible_for_login(self):
        """手动登录必须使用可见浏览器窗口"""
        if not self.headless:
            return

        logger.info("当前为无头模式，重新打开可见浏览器用于登录")
        self._close_browser()
        self._open_browser(headless=False)
        self._load_cookies()

    def _close_browser(self):
        """关闭浏览器，忽略退出过程中的连接中断"""
        if not self.browser:
            return

        try:
            self.browser.close()
        except Exception as e:
            logger.debug(f"关闭浏览器时忽略错误: {e}")
        finally:
            self.browser = None
            self.page = None

    def _stop_playwright(self):
        """停止 Playwright，忽略退出过程中的连接中断"""
        if not self.playwright:
            return

        try:
            self.playwright.stop()
        except Exception as e:
            logger.debug(f"停止 Playwright 时忽略错误: {e}")
        finally:
            self.playwright = None

    def stop(self):
        """关闭浏览器"""
        logger.info("关闭浏览器...")
        self._close_browser()
        self._stop_playwright()

    def _save_cookies(self):
        """保存 cookies 到文件"""
        cookies = self.page.context.cookies()
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f)
        self._update_request_cookies(cookies)
        logger.info("Cookies 已更新\n")

    def _load_cookies(self):
        """从文件加载 cookies"""
        try:
            with open(COOKIE_FILE, "r") as f:
                cookies = json.load(f)
            self.page.context.add_cookies(cookies)
            self._update_request_cookies(cookies)
            logger.info("Cookies 已加载")
            return True
        except FileNotFoundError:
            logger.info("未找到 cookies 文件，需要登录")
            return False
        except Exception as e:
            logger.warning(f"加载 cookies 失败: {e}")
            return False

    def _update_request_cookies(self, cookies: list):
        """将 Playwright cookies 转换为 requests 可用的格式"""
        self.cookies_for_request = {c["name"]: c["value"] for c in cookies}

    def _has_visible_login_button(self) -> bool:
        """检查页面是否显示登录按钮"""
        try:
            login_btn = self.page.locator('text="登录"').first
            return login_btn.count() > 0 and login_btn.is_visible(timeout=1000)
        except Exception:
            return False

    def _has_user_avatar(self) -> bool:
        """检查页面是否显示登录用户头像"""
        try:
            user_avatar = self.page.locator('[class*="avatar"]').first
            return user_avatar.count() > 0
        except Exception:
            return False

    def _has_login_cookie(self) -> bool:
        """检查是否存在微博登录 cookie"""
        cookies = self.page.context.cookies()
        return any(c["name"] in {"SUB", "SSOLoginState"} for c in cookies)

    def login(self) -> bool:
        """登录微博（手动登录）"""
        self._ensure_visible_for_login()
        logger.info("正在打开微博登录页面...")
        self.page.goto("https://weibo.com/login.php")

        print("\n" + "=" * 50, flush=True)
        print("请在浏览器中手动登录微博", flush=True)
        print("登录成功后，按 Enter 键继续...", flush=True)
        print("=" * 50 + "\n", flush=True)

        input()

        print("正在验证登录状态...", flush=True)
        try:
            # 验证登录状态
            self.page.goto("https://weibo.com", wait_until="domcontentloaded", timeout=15000)
            random_delay(1)
            try:
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception as e:
                logger.debug(f"等待页面稳定时出错: {e}")

            if "login" in self.page.url.lower() or "passport" in self.page.url.lower():
                logger.warning("未检测到登录状态，已退出")
                return False

            if self._has_visible_login_button():
                logger.warning("未检测到登录状态，已退出")
                return False

            if self._has_user_avatar() or self._has_login_cookie():
                self.is_logged_in = True
                self._save_cookies()
                logger.info("登录成功！")
                return True
        except Exception as e:
            logger.warning("登录未完成或浏览器已关闭")
            logger.debug(f"检查登录状态时出错: {e}")
            return False

        logger.warning("未检测到登录状态，已退出")
        return False

    def check_login_status(self) -> bool:
        """检查当前登录状态"""
        logger.info("检查登录状态...")

        try:
            current_url = self.page.url
            if not current_url or "weibo.com" not in current_url:
                self.page.goto("https://weibo.com")
                random_delay(2.5)

            self.page.wait_for_load_state("networkidle", timeout=15000)

            # 检查是否被重定向到登录页
            if "login" in self.page.url.lower() or "passport" in self.page.url.lower():
                self.is_logged_in = False
                return False

            # 检查页面是否有登录用户的特征
            try:
                user_avatar = self.page.locator('[class*="avatar"]').first
                if user_avatar.count() > 0:
                    self.is_logged_in = True
                    self._save_cookies()
                    return True
            except:
                pass

            # 备用检查：查看是否有登录按钮
            try:
                login_btn = self.page.locator('text="登录"').first
                if login_btn.count() > 0 and login_btn.is_visible(timeout=1000):
                    self.is_logged_in = False
                    return False
            except:
                pass

            self.is_logged_in = True
            self._save_cookies()
            return True

        except Exception as e:
            logger.warning(f"检查登录状态失败: {e}")
            return False

    def goto(self, url: str):
        """导航到指定 URL"""
        self.page.goto(url)

    def smooth_scroll_to_element(self, element):
        """平滑滚动到元素位置"""
        try:
            element.evaluate("""
                el => el.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                })
            """)
            random_delay(1.5)
        except Exception as e:
            logger.debug(f"平滑滚动失败: {e}")
            element.scroll_into_view_if_needed()

    def scroll_page(self, distance: int):
        """滚动页面"""
        self.page.evaluate(f"""
            () => {{
                window.scrollBy({{
                    top: {distance},
                    behavior: 'smooth'
                }});
            }}
        """)
