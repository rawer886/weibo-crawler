"""
日志模块

职责：
- 统一日志配置
- 彩色终端输出
- 文件日志记录
"""
import logging
import os

from config import DATA_DIR, CRAWLER_CONFIG

# 日志内部配置
_LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
_LOG_FILE = os.path.join(DATA_DIR, "logs", "crawler.log")


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器（仅终端输出）"""
    COLORS = {
        logging.WARNING: '\033[93m',    # 黄色
        logging.ERROR: '\033[91m',      # 红色
        logging.CRITICAL: '\033[91;1m', # 红色加粗
    }
    RESET = '\033[0m'

    def format(self, record):
        message = super().format(record)
        color = self.COLORS.get(record.levelno)
        if color:
            return f"{color}{message}{self.RESET}"
        return message


def setup_logging():
    """初始化日志配置，应在程序入口处调用一次"""
    # 文件处理器（无颜色）
    file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    # 终端处理器（带颜色）
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(ColoredFormatter(_LOG_FORMAT))

    log_level = CRAWLER_CONFIG.get("log_level", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level),
        handlers=[file_handler, stream_handler]
    )


def get_logger(name: str) -> logging.Logger:
    """获取 logger 实例"""
    return logging.getLogger(name)
