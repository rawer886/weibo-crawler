# Scripts - 数据查询和分析脚本

该目录包含用于查询和分析已抓取数据的实用脚本。

## 目录说明

scripts 目录提供各种数据查询和分析工具，帮助你：
- 查询特定微博的评论数据
- 分析博主的互动行为
- 导出和统计数据
- 生成报告

## 可用脚本

### show_blogger_comments.py

**功能**: 查询特定微博下博主自己的评论

**用法**:
```bash
python scripts/query_blogger_comments.py <微博ID>
```

**示例**:
```bash
# 查询微博 5253489136775271 下博主的评论
python scripts/query_blogger_comments.py 5253489136775271
```
