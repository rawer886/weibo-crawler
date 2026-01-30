# CLAUDE.md

Claude Code 工作指引。**请先阅读 `README.md` 了解项目用法和配置。**

## 架构概览

**入口流程**: `main.py` → `commands.py` → `WeiboCrawler` (crawler.py)

**核心模块**:
- `crawler.py` - 爬虫调度器，协调各模块工作
- `browser.py` - Playwright 浏览器生命周期、Cookie 持久化、登录处理
- `api.py` - 微博移动端 API 客户端，`APICache` 实现持久化缓存
- `parser.py` - DOM 解析，从 Playwright 页面提取微博/评论数据
- `database.py` - SQLite 操作，使用上下文管理器管理连接
- `image.py` - 图片下载，按 `{uid}/{YYYY-MM}/{mid}_{index}.jpg` 组织
- `display.py` - 格式化控制台输出
- `logger.py` - 彩色控制台 + 文件日志
- `utils.py` - 时间解析工具

**数据目录**: `../data/`（项目同级目录）

## 关键实现细节

**URL 格式**: 支持 `/u/UID`、`/UID`、`/UID/MID`，MID 可以是字母数字或纯数字

**反风控策略**: 可配置延迟（默认 15s ± 25% 随机抖动），编辑 `config.py` 调整

**登录机制**: 首次运行打开浏览器手动登录，Cookie 保存到 `cookies.json`，删除此文件可重新登录

**按需列表获取**: history 模式下，当待处理队列不足时按需获取微博列表

**时间标准化**: 所有日期存储为 `YYYY-MM-DD HH:MM` 格式，`utils.parse_weibo_time()` 处理各种输入格式

**抓取进度**: `crawl_progress` 表记录每个用户的 `list_scan_oldest_mid`，支持断点续传

## 数据库表

- `bloggers` - 用户信息（uid, nickname, followers_count）
- `posts` - 微博，`detail_status` 字段追踪状态（0=待抓取, 1=已完成）
- `comments` - 评论，含回复关系和 `blogger_reply` 标记
- `crawl_progress` - 抓取进度
