import importlib.util
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
