# CLAUDE.md

Claude Code 工作指引。**请先阅读 `README.md` 了解项目用法和配置。**

## 项目结构

```
crawler/
├── main.py          # 入口：URL 解析 → commands
├── src/             # 核心模块（全部使用相对导入）
│   ├── commands.py  # 命令处理：单条/批量抓取
│   ├── crawler.py   # 爬虫调度器，协调各模块
│   ├── browser.py   # Playwright 生命周期、Cookie、登录
│   ├── api.py       # 移动端 API、持久化缓存
│   ├── parser.py    # DOM 解析微博/评论数据
│   ├── database.py  # SQLite（上下文管理器）
│   ├── image.py     # 图片下载 {uid}/{YYYY-MM}/{mid}_{index}.jpg
│   ├── display.py   # 控制台格式化输出
│   ├── logger.py    # 彩色终端 + 文件日志
│   ├── config.py    # 配置常量
│   └── utils.py     # 时间解析、mid 转换
└── scripts/         # 辅助脚本（使用 src. 前缀导入）
```

## 关键实现

**URL 格式**: `/u/UID`、`/UID`、`/UID/MID`（MID 支持字母数字或纯数字）

**反风控**: 可配置延迟（默认 15s ± 25% 随机抖动），编辑 `src/config.py`

**登录**: 首次运行手动登录，Cookie 保存到 `../data/cookies.json`

**时间格式**: 统一存储为 `YYYY-MM-DD HH:MM`，`utils.parse_weibo_time()` 处理各种输入

**数据目录**: `../data/`（项目同级）

## 抓取模式

### History（默认）
从历史向更老方向抓取，更新 `history_end` 边界

### New
从最新向历史方向抓取到 `history_start`，衔接后更新边界

```
[最新] A → B → C → D → E → F → G → H → I → J [最老]
                    ↑                   ↑
             history_start        history_end
```

## 数据库表

- `bloggers` - 用户信息
- `posts` - 微博，`detail_status`: 0=待抓取, 1=已完成, 2=不可访问
- `comments` - 评论，含回复关系和 `blogger_reply` 标记
- `crawl_progress` - 抓取边界（`history_start/end_mid/time`）
