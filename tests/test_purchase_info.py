import importlib.util
import sys
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fund_info.py"
spec = importlib.util.spec_from_file_location("fund_info", MODULE_PATH)
fund_info = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fund_info)


def test_get_purchase_info_reads_subscription_and_redemption_limits(monkeypatch):
    purchase_df = pd.DataFrame(
        [
            {
                "基金代码": "000001",
                "申购状态": "开放申购",
                "赎回状态": "开放赎回",
                "购买起点": 10,
                "日累计限定金额": 1000,
            },
            {
                "基金代码": "000002",
                "申购状态": "暂停申购",
                "赎回状态": "开放赎回",
                "购买起点": 100,
                "日累计限定金额": None,
            },
        ]
    )

    monkeypatch.setattr(fund_info.ak, "fund_purchase_em", lambda: purchase_df)

    result = fund_info.get_purchase_info("000001")

    assert result == {
        "purchase_status": "开放申购",
        "redemption_status": "开放赎回",
        "purchase_min": 10,
        "daily_purchase_limit": 1000,
    }


def test_lookup_purchase_info_reuses_loaded_purchase_table():
    purchase_df = pd.DataFrame(
        [
            {
                "基金代码": "1",
                "基金简称": "测试基金A",
                "申购状态": "开放申购",
                "赎回状态": "开放赎回",
                "购买起点": 10,
                "日累计限定金额": 1000,
            },
            {
                "基金代码": "000002",
                "基金简称": "测试基金B",
                "申购状态": "暂停申购",
                "赎回状态": "开放赎回",
                "购买起点": 100,
                "日累计限定金额": None,
            },
        ]
    )

    result = fund_info.lookup_purchase_info(purchase_df, "000001")

    assert result == {
        "code": "000001",
        "name": "测试基金A",
        "purchase_status": "开放申购",
        "redemption_status": "开放赎回",
        "purchase_min": 10,
        "daily_purchase_limit": 1000,
    }


def test_load_purchase_table_uses_same_day_cache_without_network(monkeypatch, tmp_path):
    cached_df = pd.DataFrame(
        [
            {
                "基金代码": "000001",
                "基金简称": "测试基金",
                "申购状态": "开放申购",
                "赎回状态": "开放赎回",
                "购买起点": 10,
                "日累计限定金额": 1000,
            }
        ]
    )
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_file = cache_dir / f"fund_purchase_em_{fund_info.date.today().isoformat()}.csv"
    cached_df.to_csv(cache_file, index=False)

    def fail_network_call():
        raise AssertionError("fund_purchase_em should not be called when cache is fresh")

    monkeypatch.setattr(fund_info.ak, "fund_purchase_em", fail_network_call)

    result = fund_info.load_purchase_table(cache_dir=cache_dir)

    assert result.to_dict("records") == cached_df.to_dict("records")


def test_purchase_only_cli_fetches_purchase_table_once_and_skips_slow_sections(monkeypatch, capsys):
    purchase_df = pd.DataFrame(
        [
            {
                "基金代码": "000001",
                "基金简称": "测试基金A",
                "申购状态": "开放申购",
                "赎回状态": "开放赎回",
                "购买起点": 10,
                "日累计限定金额": 1000,
            },
            {
                "基金代码": "000002",
                "基金简称": "测试基金B",
                "申购状态": "暂停申购",
                "赎回状态": "开放赎回",
                "购买起点": 100,
                "日累计限定金额": None,
            },
        ]
    )
    calls = {"purchase": 0}

    def fake_purchase_table():
        calls["purchase"] += 1
        return purchase_df

    def fail_slow_section(*args, **kwargs):
        raise AssertionError("purchase-only mode should not call slow full-report sections")

    monkeypatch.setattr(fund_info.ak, "fund_purchase_em", fake_purchase_table)
    monkeypatch.setattr(fund_info, "get_basic_info", fail_slow_section)
    monkeypatch.setattr(fund_info, "get_fee_info", fail_slow_section)
    monkeypatch.setattr(fund_info, "get_nav_history", fail_slow_section)
    monkeypatch.setattr(fund_info, "get_holdings", fail_slow_section)
    monkeypatch.setattr(fund_info, "get_performance", fail_slow_section)
    monkeypatch.setattr(sys, "argv", ["fund_info.py", "--purchase-only", "--no-cache", "000001", "000002"])

    fund_info.main()
    out = capsys.readouterr().out

    assert calls["purchase"] == 1
    assert "| 000001 | 测试基金A | 开放申购 | 开放赎回 | 10 | 1000 |  |" in out
    assert "| 000002 | 测试基金B | 暂停申购 | 开放赎回 | 100 | N/A |  |" in out


def test_sections_purchase_skips_nav_holdings_and_performance(monkeypatch, capsys):
    purchase_df = pd.DataFrame(
        [
            {
                "基金代码": "000001",
                "基金简称": "测试基金A",
                "申购状态": "开放申购",
                "赎回状态": "开放赎回",
                "购买起点": 10,
                "日累计限定金额": 1000,
            }
        ]
    )

    monkeypatch.setattr(fund_info.ak, "fund_purchase_em", lambda: purchase_df)
    monkeypatch.setattr(fund_info, "get_basic_info", lambda code: {"code": code, "name": "N/A", "short_name": "N/A"})
    monkeypatch.setattr(fund_info, "get_fee_info", lambda code: {"management_fee": "N/A", "custody_fee": "N/A"})

    def fail_slow_section(*args, **kwargs):
        raise AssertionError("sections=purchase should not call nav, holdings, or performance")

    monkeypatch.setattr(fund_info, "get_nav_history", fail_slow_section)
    monkeypatch.setattr(fund_info, "get_holdings", fail_slow_section)
    monkeypatch.setattr(fund_info, "get_performance", fail_slow_section)
    monkeypatch.setattr(sys, "argv", ["fund_info.py", "--sections", "purchase", "--no-cache", "000001"])

    fund_info.main()
    out = capsys.readouterr().out

    assert "## 基本信息" in out
    assert "## 单位净值历史" not in out
    assert "## 近期持仓" not in out
    assert "## 业绩指标" not in out


def test_run_with_timeout_returns_unavailable_when_call_exceeds_limit():
    def slow_call():
        import time

        time.sleep(0.2)
        return {"ok": True}

    result = fund_info.run_with_timeout("holdings", slow_call, timeout_seconds=0.01, fallback={})

    assert result["unavailable"] is True
    assert "timeout" in result["error"]


def test_run_with_timeout_preserves_dataframe_fallback_error():
    def slow_call():
        import time

        time.sleep(0.2)
        return pd.DataFrame({"基金代码": ["000001"]})

    fallback = pd.DataFrame()

    result = fund_info.run_with_timeout("purchase", slow_call, timeout_seconds=0.01, fallback=fallback)

    assert result.empty
    assert result.attrs["unavailable"] is True
    assert "timeout" in result.attrs["error"]


def test_lookup_purchase_info_reports_purchase_table_error():
    purchase_df = pd.DataFrame()
    purchase_df.attrs["error"] = "purchase timeout after 1s"

    result = fund_info.lookup_purchase_info(purchase_df, "000001")

    assert result["code"] == "000001"
    assert result["purchase_status"] == "N/A"
    assert result["error"] == "purchase timeout after 1s"


def test_get_nav_history_requests_shortest_supported_period(monkeypatch):
    periods = []

    def fake_nav(symbol, indicator, period):
        periods.append(period)
        if indicator == "单位净值走势":
            return pd.DataFrame(
                [
                    {"净值日期": "2026-04-01", "单位净值": 1.0, "日增长率": 0.1},
                    {"净值日期": "2026-06-01", "单位净值": 1.1, "日增长率": 0.2},
                ]
            )
        return pd.DataFrame(
            [
                {"净值日期": "2026-04-01", "累计净值": 1.0},
                {"净值日期": "2026-06-01", "累计净值": 1.1},
            ]
        )

    monkeypatch.setattr(fund_info.ak, "fund_open_fund_info_em", fake_nav)

    result = fund_info.get_nav_history(
        "000001",
        fund_info.parse_date("2026-03-24"),
        fund_info.parse_date("2026-06-22"),
    )

    assert periods == ["3月", "3月"]
    assert result["records"]


def test_render_markdown_shows_purchase_info():
    markdown = fund_info.render_markdown(
        {
            "metadata": {
                "code": "000001",
                "short_name": "测试基金",
                "type": "QDII",
                "purchase_status": "开放申购",
                "redemption_status": "开放赎回",
                "purchase_min": 10,
                "daily_purchase_limit": 1000,
            },
            "allocation": {"records": []},
            "performance": {},
            "holdings": {"period": "2026", "top10": [], "error": "无持仓数据"},
            "nav_history": {"records": [], "error": "无净值数据"},
        }
    )

    assert "| 申购状态 | 开放申购 |" in markdown
    assert "| 赎回状态 | 开放赎回 |" in markdown
    assert "| 购买起点 | 10 |" in markdown
    assert "| 日累计限定金额 | 1000 |" in markdown
