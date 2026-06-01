#!/usr/bin/env python3
"""
cn-fund-info: 获取国内公募基金信息
用法: python fund_info.py <基金代码或名称> [--nav-start YYYY-MM-DD] [--nav-end YYYY-MM-DD] [--position-period 2024]
"""

import argparse
import sys
import json
from datetime import datetime, timedelta, date

try:
    import akshare as ak
    import pandas as pd
except ImportError as e:
    print(f"错误：缺少依赖，请运行 `pip install akshare pandas`\n{e}", file=sys.stderr)
    sys.exit(1)

# ──────────────────────────────────────────
# Schema 映射表：统一 akshare 各接口的列名为英文 key
# ──────────────────────────────────────────
COLUMN_MAP = {
    # 净值历史
    "净值日期": "date",
    "单位净值": "net_value",
    "累计净值": "accum_value",
    "日增长率": "daily_change",
    # 持仓
    "序号": "rank",
    "股票代码": "code",
    "股票名称": "name",
    "占净值比例": "ratio",
    "持仓市值": "value_million",
    "持仓市值(万元)": "value_million",
    # 基础信息
    "基金简称": "fund_name",
    "基金代码": "fund_code",
    # 排名
    "同类排名": "peer_rank",
    "百分比": "rank_pct",
}


def normalize_columns(df: "pd.DataFrame") -> "pd.DataFrame":
    """将 DataFrame 列名统一映射为英文 key。"""
    return df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns})


# ──────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────
def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def date_range_days(start: date, end: date) -> int:
    return (end - start).days


def sample_nav(df: "pd.DataFrame", start: date, end: date) -> "pd.DataFrame":
    """
    根据时间跨度对净值数据采样，防止超出 LLM 上下文窗口。
    ≤90天: 按日  |  91~365天: 按周  |  >365天: 按月
    """
    days = date_range_days(start, end)
    df = df.copy()
    # 确保 date 列是 datetime 类型以便 resample
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    # 过滤到指定范围
    df = df[str(start):str(end)]
    if df.empty:
        return df.reset_index()

    if days <= 90:
        sample_period = "daily"
        result = df
    elif days <= 365:
        sample_period = "weekly"
        # 按周重采样，取最后一个有效值
        result = df.resample("W").last().dropna(how="all")
    else:
        sample_period = "monthly"
        result = df.resample("ME").last().dropna(how="all")

    result = result.reset_index()
    result.attrs["sample_period"] = sample_period
    return result


def safe_float(val, default=None):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_pct(val, default="N/A"):
    """将 '1.23%' 或 0.0123 统一为百分比字符串。"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    if isinstance(val, str) and "%" in val:
        return val.strip()
    try:
        f = float(val)
        return f"{f:+.2f}%"
    except (TypeError, ValueError):
        return str(val)


def clean_value(val, default="N/A"):
    """清理 akshare 返回值，保留数值原类型以便 JSON 输出。"""
    if val is None:
        return default
    try:
        if pd.isna(val):
            return default
    except (TypeError, ValueError):
        pass
    return val


def display_value(val):
    """Markdown 展示用：整数金额不显示 .0。"""
    if val in (None, "N/A", ""):
        return "N/A"
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val)


# ──────────────────────────────────────────
# 数据获取函数
# ──────────────────────────────────────────
def resolve_fund_code(query: str) -> str:
    """
    将基金名称（模糊）解析为基金代码。
    若 query 是纯数字，直接返回。
    若匹配多个，打印候选列表并退出让用户确认。
    """
    if query.isdigit():
        return query

    try:
        all_funds = ak.fund_name_em()
    except Exception as e:
        print(f"错误：无法获取基金列表：{e}", file=sys.stderr)
        sys.exit(1)

    # 模糊匹配：简称或代码包含 query
    mask = all_funds.apply(lambda row: query in str(row.get("基金简称", "")) or
                                        query in str(row.get("基金代码", "")), axis=1)
    matched = all_funds[mask]

    if matched.empty:
        print(f"未找到名称包含「{query}」的基金，请确认名称或直接使用6位基金代码。")
        sys.exit(1)

    if len(matched) == 1:
        code = str(matched.iloc[0].get("基金代码", matched.iloc[0].iloc[0]))
        return code

    # 多个匹配，输出 Markdown 表格让用户确认
    print(f"找到 {len(matched)} 个匹配的基金，请使用具体基金代码重新查询：\n")
    print("| 基金代码 | 基金简称 |")
    print("|---------|---------|")
    for _, row in matched.head(20).iterrows():
        code = str(row.get("基金代码", row.iloc[0]))
        name = str(row.get("基金简称", row.iloc[1]))
        print(f"| {code} | {name} |")
    if len(matched) > 20:
        print(f"\n（仅显示前20条，共 {len(matched)} 条）")
    sys.exit(0)


def get_basic_info(code: str) -> dict:
    """获取基金基础信息（雪球）。"""
    try:
        df = ak.fund_individual_basic_info_xq(symbol=code)
        # 返回 key-value DataFrame，列名为 item / value
        info = dict(zip(df.iloc[:, 0], df.iloc[:, 1]))
        return {
            "code": code,
            "name": info.get("基金名称") or info.get("基金全称") or info.get("name", "N/A"),
            "short_name": info.get("基金名称", "N/A"),
            "type": info.get("基金类型", "N/A"),
            "founded": info.get("成立时间", info.get("成立日期", "N/A")),
            "scale": info.get("最新规模", info.get("基金规模", info.get("资产规模", "N/A"))),
            "manager": info.get("基金经理", info.get("基金经理人", "N/A")),
            "status": info.get("申购状态", "N/A"),
            "raw": info,
        }
    except Exception as e:
        return {
            "code": code, "name": "N/A", "short_name": "N/A", "type": "N/A",
            "founded": "N/A", "scale": "N/A", "manager": "N/A", "status": "N/A",
            "error": str(e),
        }


def get_fee_info(code: str) -> dict:
    """获取费率信息（雪球交易规则）。"""
    try:
        df = ak.fund_individual_detail_info_xq(symbol=code)
        mgmt_fee = "N/A"
        custody_fee = "N/A"

        if df is not None and not df.empty:
            for _, row in df.iterrows():
                row_str = " ".join(str(v) for v in row.values)
                if "管理费" in row_str:
                    vals = [str(v) for v in row.values if "%" in str(v)]
                    if vals:
                        mgmt_fee = vals[0]
                elif "托管费" in row_str:
                    vals = [str(v) for v in row.values if "%" in str(v)]
                    if vals:
                        custody_fee = vals[0]

        return {
            "management_fee": mgmt_fee,
            "custody_fee": custody_fee,
        }
    except Exception as e:
        return {
            "management_fee": "N/A",
            "custody_fee": "N/A",
            "error": str(e),
        }


def get_purchase_info(code: str) -> dict:
    """获取天天基金/东方财富口径的申购、赎回状态和日累计限额。"""
    empty = {
        "purchase_status": "N/A",
        "redemption_status": "N/A",
        "purchase_min": "N/A",
        "daily_purchase_limit": "N/A",
    }
    try:
        df = ak.fund_purchase_em()
        if df is None or df.empty:
            return {**empty, "error": "无申购状态数据"}

        fund_codes = df["基金代码"].astype(str).str.zfill(6)
        row = df[fund_codes == str(code).zfill(6)]
        if row.empty:
            return {**empty, "error": "未找到该基金申购状态"}

        record = row.iloc[0]
        return {
            "purchase_status": clean_value(record.get("申购状态")),
            "redemption_status": clean_value(record.get("赎回状态")),
            "purchase_min": clean_value(record.get("购买起点")),
            "daily_purchase_limit": clean_value(record.get("日累计限定金额")),
        }
    except Exception as e:
        return {**empty, "error": str(e)}


def get_nav_history(code: str, start: date, end: date) -> dict:
    """获取单位净值历史（含累计净值）。"""
    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势", period="成立来")
        df = normalize_columns(df)
        if df.empty:
            return {"sample_period": "daily", "records": [], "error": "无数据"}

        # 获取累计净值并合并
        try:
            df_accum = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势", period="成立来")
            df_accum = normalize_columns(df_accum)
            if not df_accum.empty and "accum_value" in df_accum.columns:
                df_accum["date"] = pd.to_datetime(df_accum["date"])
                df["date"] = pd.to_datetime(df["date"])
                df = df.merge(df_accum[["date", "accum_value"]], on="date", how="left")
        except Exception:
            df["accum_value"] = None

        # 采样
        sampled = sample_nav(df, start, end)
        sample_period = sampled.attrs.get("sample_period", "daily")

        records = []
        for _, row in sampled.iterrows():
            records.append({
                "date": str(row["date"])[:10],
                "net_value": safe_float(row.get("net_value")),
                "accum_value": safe_float(row.get("accum_value")),
                "daily_change": safe_pct(row.get("daily_change")),
            })
        return {"sample_period": sample_period, "records": records}
    except Exception as e:
        return {"sample_period": "daily", "records": [], "error": str(e)}


def get_holdings(code: str, period: str) -> dict:
    """获取基金持仓（前十大重仓股）。"""
    try:
        df = ak.fund_portfolio_hold_em(symbol=code, date=period)
        df = normalize_columns(df)
        if df.empty:
            return {"period": period, "update_date": "N/A", "top10": [], "error": "无持仓数据"}

        top10 = []
        for i, row in df.head(10).iterrows():
            top10.append({
                "rank": int(row.get("rank", i + 1)),
                "code": str(row.get("code", "N/A")),
                "name": str(row.get("name", "N/A")),
                "ratio": safe_float(row.get("ratio")),
                "value_million": safe_float(row.get("value_million")),
            })

        update_date = period
        return {"period": period, "update_date": update_date, "top10": top10}
    except Exception as e:
        return {"period": period, "update_date": "N/A", "top10": [], "error": str(e)}


def get_performance(code: str) -> dict:
    """获取业绩指标（涨跌幅、同类排名、夏普、最大回撤）。"""
    result = {
        "return_1m": "N/A",
        "return_3m": "N/A",
        "return_1y": "N/A",
        "rank_1y": "N/A",
        "sharpe_1y": "N/A",
        "max_drawdown_1y": "N/A",
    }

    # 1. 涨跌幅：从开放式基金排行获取（需按基金类型查询）
    fund_types = ["全部", "混合型", "股票型", "债券型", "指数型", "QDII", "FOF"]
    for ftype in fund_types:
        try:
            df = ak.fund_open_fund_rank_em(symbol=ftype)
            if df is None or df.empty:
                continue
            row = df[df["基金代码"].astype(str) == code]
            if not row.empty:
                r = row.iloc[0]
                result["return_1m"] = safe_pct(r.get("近1月"))
                result["return_3m"] = safe_pct(r.get("近3月"))
                result["return_1y"] = safe_pct(r.get("近1年"))
                break
        except Exception:
            continue

    # 2. 夏普比率 & 最大回撤：fund_individual_analysis_xq
    try:
        df = ak.fund_individual_analysis_xq(symbol=code)
        if df is not None and not df.empty:
            row_1y = df[df["周期"].astype(str).str.contains("近1年|1年", na=False)]
            if not row_1y.empty:
                r = row_1y.iloc[0]
                sharpe = safe_float(r.get("年化夏普比率"))
                drawdown = safe_float(r.get("最大回撤"))
                result["sharpe_1y"] = str(sharpe) if sharpe is not None else "N/A"
                result["max_drawdown_1y"] = f"-{drawdown:.2f}%" if drawdown is not None else "N/A"
    except Exception as e:
        result["_analysis_error"] = str(e)

    # 3. 同类排名：fund_open_fund_info_em
    try:
        rank_df = ak.fund_open_fund_info_em(symbol=code, indicator="同类排名走势", period="1年")
        if rank_df is not None and not rank_df.empty:
            latest = rank_df.sort_values(rank_df.columns[0]).iloc[-1]
            peer_rank = latest.get("同类型排名-每日近三月排名")
            total_rank = latest.get("总排名-每日近三月排名")
            if peer_rank is not None:
                if total_rank is not None:
                    result["rank_1y"] = f"同类第{int(peer_rank)}名（总第{int(total_rank)}名）"
                else:
                    result["rank_1y"] = f"同类第{int(peer_rank)}名"
    except Exception:
        pass

    return result


# ──────────────────────────────────────────
# Markdown 渲染
# ──────────────────────────────────────────
def render_markdown(data: dict) -> str:
    meta = data.get("metadata", {})
    alloc = data.get("allocation", {})
    perf = data.get("performance", {})
    holdings = data.get("holdings", {})
    nav = data.get("nav_history", {})

    lines = []

    # 标题
    name = meta.get("short_name") or meta.get("name", "未知")
    code = meta.get("code", "")
    lines.append(f"# 基金信息：{name}({code})\n")

    # 基本信息
    lines.append("## 基本信息")
    lines.append("| 字段 | 值 |")
    lines.append("|------|-----|")
    purchase_status = meta.get("purchase_status")
    if purchase_status in (None, "N/A", ""):
        purchase_status = meta.get("status")
    fields = [
        ("基金类型", meta.get("type")),
        ("成立日期", meta.get("founded")),
        ("基金规模", meta.get("scale")),
        ("基金经理", meta.get("manager")),
        ("申购状态", purchase_status),
        ("赎回状态", meta.get("redemption_status")),
        ("购买起点", display_value(meta.get("purchase_min"))),
        ("日累计限定金额", display_value(meta.get("daily_purchase_limit"))),
        ("管理费率", meta.get("management_fee")),
        ("托管费率", meta.get("custody_fee")),
    ]
    for label, val in fields:
        if val and val != "N/A":
            lines.append(f"| {label} | {val} |")
    lines.append("")

    # 资产配置（如果有）
    if alloc and alloc.get("records"):
        update = alloc.get("update_date", "N/A")
        lines.append(f"## 资产配置(截至 {update})")
        lines.append("| 资产类型 | 占比 |")
        lines.append("|---------|------|")
        for rec in alloc["records"]:
            lines.append(f"| {rec['type']} | {rec['ratio']} |")
        lines.append("")

    # 业绩指标
    lines.append("## 业绩指标")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    perf_fields = [
        ("近1月涨跌幅", perf.get("return_1m")),
        ("近3月涨跌幅", perf.get("return_3m")),
        ("近1年涨跌幅", perf.get("return_1y")),
        ("同类排名(近1年)", perf.get("rank_1y")),
        ("夏普比率(近1年)", perf.get("sharpe_1y")),
        ("最大回撤(近1年)", perf.get("max_drawdown_1y")),
    ]
    for label, val in perf_fields:
        display = val if val not in (None, "N/A") else "暂无数据"
        lines.append(f"| {label} | {display} |")
    lines.append("")

    # 持仓
    period = holdings.get("period", "N/A")
    update_date = holdings.get("update_date", "N/A")
    top10 = holdings.get("top10", [])
    if holdings.get("error"):
        lines.append(f"## 近期持仓({period})")
        lines.append(f"> {holdings['error']}\n")
    elif top10:
        lines.append(f"## 近期持仓({period}，报告期：{update_date})")
        lines.append("| 排名 | 代码 | 名称 | 持仓占比 | 持仓市值(万元) |")
        lines.append("|------|------|------|---------|----------------|")
        for h in top10:
            ratio_str = f"{h['ratio']:.2f}%" if h.get("ratio") else "N/A"
            val_str = f"{h['value_million']:.0f}" if h.get("value_million") else "N/A"
            lines.append(f"| {h['rank']} | {h['code']} | {h['name']} | {ratio_str} | {val_str} |")
        lines.append("")
    else:
        lines.append(f"## 近期持仓({period})")
        lines.append("> 暂无持仓数据\n")

    # 净值历史
    records = nav.get("records", [])
    sp = nav.get("sample_period", "daily")
    sp_label = {"daily": "按日", "weekly": "按周", "monthly": "按月"}.get(sp, sp)
    if nav.get("error"):
        lines.append("## 单位净值历史")
        lines.append(f"> {nav['error']}\n")
    elif records:
        start_d = records[0]["date"] if records else "N/A"
        end_d = records[-1]["date"] if records else "N/A"
        lines.append(f"## 单位净值历史({sp_label}采样，{start_d} ~ {end_d}，共 {len(records)} 条)")
        lines.append("| 日期 | 单位净值 | 累计净值 | 涨跌幅 |")
        lines.append("|------|---------|---------|-------|")
        for rec in records:
            nv = f"{rec['net_value']:.4f}" if rec.get("net_value") else "N/A"
            av = f"{rec['accum_value']:.4f}" if rec.get("accum_value") else "N/A"
            ch = rec.get("daily_change", "N/A")
            lines.append(f"| {rec['date']} | {nv} | {av} | {ch} |")
        lines.append("")
    else:
        lines.append("## 单位净值历史")
        lines.append("> 暂无净值数据\n")

    return "\n".join(lines)


# ──────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="获取国内公募基金信息（基于 akshare）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python fund_info.py 110011
  python fund_info.py "易方达蓝筹"
  python fund_info.py 110011 --nav-start 2023-01-01 --nav-end 2024-12-31
  python fund_info.py 110011 --position-period 2023
        """,
    )
    parser.add_argument("query", help="6位基金代码 或 基金名称（支持模糊匹配）")
    parser.add_argument("--nav-start", help="净值起始日期 YYYY-MM-DD（默认：近90天）")
    parser.add_argument("--nav-end", help="净值结束日期 YYYY-MM-DD（默认：今天）")
    parser.add_argument(
        "--position-period",
        default=str(datetime.now().year),
        help="持仓报告期，格式 YYYY 或 YYYYQ? 例如 2024 或 2024Q3（默认：当前年份）",
    )
    parser.add_argument("--json", action="store_true", help="输出原始 JSON（调试用）")
    args = parser.parse_args()

    # 解析日期
    today = date.today()
    nav_end = parse_date(args.nav_end) if args.nav_end else today
    nav_start = parse_date(args.nav_start) if args.nav_start else today - timedelta(days=90)

    # 解析持仓期（支持 2024Q3 → "2024"），akshare 只接受年份
    position_period = args.position_period
    if "Q" in position_period.upper():
        position_period = position_period.split("Q")[0].split("q")[0]

    # 解析基金代码
    print("正在解析基金代码...", file=sys.stderr)
    code = resolve_fund_code(args.query)

    # 顺序获取各项数据
    print("正在获取基础信息...", file=sys.stderr)
    basic = get_basic_info(code)

    print("正在获取费率信息...", file=sys.stderr)
    fee = get_fee_info(code)

    print("正在获取申购/赎回状态...", file=sys.stderr)
    purchase = get_purchase_info(code)

    print("正在获取净值历史...", file=sys.stderr)
    nav = get_nav_history(code, nav_start, nav_end)

    print("正在获取持仓数据...", file=sys.stderr)
    holdings = get_holdings(code, position_period)

    print("正在获取业绩指标...", file=sys.stderr)
    perf = get_performance(code)

    # 构建统一 JSON
    data = {
        "metadata": {
            "code": code,
            "name": basic.get("name", "N/A"),
            "short_name": basic.get("short_name", "N/A"),
            "type": basic.get("type", "N/A"),
            "founded": basic.get("founded", "N/A"),
            "scale": basic.get("scale", "N/A"),
            "manager": basic.get("manager", "N/A"),
            "status": basic.get("status", "N/A"),
            "purchase_status": purchase.get("purchase_status", "N/A"),
            "redemption_status": purchase.get("redemption_status", "N/A"),
            "purchase_min": purchase.get("purchase_min", "N/A"),
            "daily_purchase_limit": purchase.get("daily_purchase_limit", "N/A"),
            "purchase_error": purchase.get("error"),
            "management_fee": fee.get("management_fee", "N/A"),
            "custody_fee": fee.get("custody_fee", "N/A"),
        },
        "allocation": {"records": []},
        "performance": perf,
        "holdings": holdings,
        "nav_history": nav,
    }

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_markdown(data))


if __name__ == "__main__":
    main()
