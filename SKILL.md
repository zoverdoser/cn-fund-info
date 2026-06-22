---
name: cn-fund-info
description: Use when the user asks about a Chinese domestic mutual fund — fund type, asset allocation, recent holdings, performance metrics (Sharpe ratio, max drawdown, returns), historical NAV, fees, or purchase status. Triggers on a 6-digit fund code or a Chinese fund name.
license: MIT
compatibility: Requires Python 3.8+ and the `akshare` and `pandas` packages. Network access required to fetch fund data.
metadata:
  version: '1.0'
---

# cn-fund-info：国内公募基金信息查询

## Overview

通过一条命令获取国内公募基金的完整信息，输出为结构化 Markdown，供 LLM 对话直接引用。数据源：akshare。

## When to Use

- 用户提供基金代码（6位数字）或基金名称（支持模糊匹配）
- 用户询问基金的类型、规模、经理、申购/赎回状态、限购金额、费率
- 用户询问基金的持仓、资产配置、业绩表现
- 用户询问指定时间段的历史净值

## Dependencies

首次使用前安装依赖：

```bash
pip install -r requirements.txt
```

或手动安装：

```bash
pip install akshare pandas
```

## Quick Reference

从 skill 根目录执行（即 `SKILL.md` 所在目录）：

```bash
# 按基金代码查询（默认近90天净值、当年持仓）
python scripts/fund_info.py 110011

# 按基金名称查询（模糊匹配）
python scripts/fund_info.py "易方达蓝筹"

# 快速查询申购/赎回状态和限购金额；支持批量，内部只拉一次全市场申购状态表
python scripts/fund_info.py --purchase-only 000369 006282 006105

# --purchase-only 的别名
python scripts/fund_info.py --status-only 000369 006282

# 只查询指定模块
python scripts/fund_info.py --sections basic,purchase 110011

# 指定净值时间范围
python scripts/fund_info.py 110011 --nav-start 2024-01-01 --nav-end 2024-12-31

# 指定持仓报告期（年份）
python scripts/fund_info.py 110011 --position-period 2023

# 刷新或禁用当日申购状态缓存
python scripts/fund_info.py --purchase-only --refresh-cache 000369
python scripts/fund_info.py --purchase-only --no-cache 000369

# 输出原始 JSON（调试用）
python scripts/fund_info.py 110011 --json
```

## Output Sections

| Section      | 说明                                                                                    |
| ------------ | --------------------------------------------------------------------------------------- |
| 基本信息     | 类型、成立日期、规模、经理、申购状态、赎回状态、购买起点、日累计限定金额、管理/托管费率 |
| 业绩指标     | 近1月/3月/1年涨跌幅、同类排名、夏普比率（近1年）、最大回撤（近1年）                     |
| 近期持仓     | 前十大重仓股：代码、名称、持仓占比、持仓市值（万元），注明报告期                        |
| 单位净值历史 | 自动采样：≤90天按日、91~365天按周、>365天按月；含累计净值和涨跌幅                       |

`--sections` 支持 `basic,fee,purchase,nav,holdings,performance`。若不指定，保持原完整报告行为。净值模块会按日期范围传入能覆盖该区间的最短 akshare period；如无需净值，可不选择 `nav` section。

## Sampling Strategy

净值数据根据时间跨度自动调整采样频率，防止超出 LLM 上下文窗口：

| 时间跨度       | 采样 |
| -------------- | ---- |
| ≤ 90 天        | 按日 |
| 91 天 ~ 365 天 | 按周 |
| > 365 天       | 按月 |

## Name Disambiguation

若基金名称模糊匹配到多个结果，脚本输出候选列表（Markdown 表格）并退出。
此时应提示用户选择具体代码后重新查询。

## Example

```bash
python scripts/fund_info.py 005827
```

输出示例（节选）：

```
# 基金信息：易方达蓝筹精选混合(005827)

## 基本信息
| 字段 | 值 |
|------|-----|
| 基金类型 | 混合型-偏股 |
| 成立日期 | 2018-09-05 |
| 基金规模 | 267.93亿 |
| 基金经理 | 张坤 |

## 业绩指标
| 指标 | 数值 |
|------|------|
| 近1年涨跌幅 | -8.90% |
| 夏普比率(近1年) | -0.65 |
| 最大回撤(近1年) | -17.80% |
```

## Error Handling

| 情况           | 脚本行为                                           |
| -------------- | -------------------------------------------------- |
| 基金代码不存在 | 输出错误信息，退出码非0                            |
| 名称匹配多个   | 输出候选列表，退出码0                              |
| 某接口无数据   | 对应 section 显示 `> 暂无数据`，不影响其他 section |
| 慢接口超时     | 对应 section 返回 `unavailable` 和错误信息，不阻塞其他 section |
| akshare 未安装 | 明确提示 `pip install akshare pandas`，退出        |

## Purchase Status Cache

`fund_purchase_em()` 会按自然日缓存到 `/tmp/cn-fund-info/fund_purchase_em_YYYY-MM-DD.csv`。同一天再次查询默认复用缓存；使用 `--refresh-cache` 强制刷新，或 `--no-cache` 禁用缓存。

## Codex Network Permission

This script requires network access. In Codex sandboxed environments, request escalated permissions for the script-specific command prefix:

["python", "<skill-root>/scripts/fund_info.py"]

Resolve `<skill-root>` from the current skill installation path at runtime. Do not request broad approvals such as `["python"]`.
