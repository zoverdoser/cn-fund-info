# cn-fund-info

A Claude Code / Agent Skill for fetching Chinese domestic mutual fund information via [akshare](https://github.com/akfamily/akshare).

Outputs structured Markdown (tables + lists) that LLMs can easily reference in conversations.

## Features

- **Fund basics**: type, founded date, scale, manager, purchase/redemption status, purchase minimum, daily purchase limit, management/custody fees
- **Performance metrics**: 1M/3M/1Y returns, peer ranking, Sharpe ratio (1Y), max drawdown (1Y)
- **Top 10 holdings**: code, name, ratio, market value — with report period
- **NAV history**: with automatic sampling (daily ≤90d / weekly ≤365d / monthly >365d) to fit LLM context windows
- **Name fuzzy search**: query by 6-digit code or Chinese fund name

## Installation

### Via `skills.sh` CLI (recommended)

```bash
npx skills add zoverdoser/cn-fund-info
```

### Manual

Clone into your agent's skills directory:

```bash
# Claude Code
git clone https://github.com/zoverdoser/cn-fund-info ~/.claude/skills/cn-fund-info
```

Then install Python dependencies:

```bash
pip install -r ~/.claude/skills/cn-fund-info/requirements.txt
```

## Usage

Once installed, Claude will invoke the skill automatically when you ask about a Chinese fund. You can also run the script directly:

```bash
# By fund code
python scripts/fund_info.py 110011

# By fund name (fuzzy match)
python scripts/fund_info.py "易方达蓝筹"

# With custom NAV date range
python scripts/fund_info.py 110011 --nav-start 2024-01-01 --nav-end 2024-12-31

# Specify holdings report period (year)
python scripts/fund_info.py 110011 --position-period 2023

# Raw JSON output (for debugging)
python scripts/fund_info.py 110011 --json
```

## Requirements

- Python 3.8+
- `akshare >= 1.12.0`
- `pandas >= 2.0.0`
- Network access (to reach data sources: eastmoney.com, xueqiu.com via akshare)

## Data Source

All data is fetched through [akshare](https://github.com/akfamily/akshare), which aggregates public Chinese financial data from sources like 东方财富网 and 雪球基金. No web scraping, no authentication required.

## Project Structure

```
cn-fund-info/
├── SKILL.md              # Skill manifest (metadata + instructions for LLMs)
├── scripts/
│   └── fund_info.py      # Main data fetching script
├── tests/
│   └── test_purchase_info.py
├── requirements.txt      # Python dependencies
├── README.md
└── LICENSE
```

## License

MIT
