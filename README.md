# Kalshi Arbitrage Detection Engine

A Python bot that connects to Kalshi's live prediction-market API to detect risk-free arbitrage opportunities in real time.

## What it does

Kalshi's exchange lists binary (YES/NO) contracts on real-world events, where the winning side always pays out $1. In theory, buying both sides of a market should never cost less than $1 combined — if it does, that's a genuine, risk-free arbitrage opportunity.

This engine:
- Authenticates with Kalshi's API using RSA-signed requests
- Pulls live orderbook data (which only exposes **bid** prices) and derives the true executable **ask** price for each side, using the fact that a bid on one side is mathematically equivalent to an ask on the other (`ask = 1 − opposite bid`)
- Factors in Kalshi's real trading fee (`0.07 × price × (1 − price)` per contract) before judging whether a gap is genuinely profitable
- Scans a configurable set of market series, staying within Kalshi's API rate limits
- Logs every detected opportunity with its ticker, title, implied prices, and estimated profit per contract

## What it doesn't do

This is a **detection** tool, not a trading bot — it identifies and logs opportunities but does not place real orders. It also doesn't currently check available order size before flagging a gap, so a detected opportunity isn't guaranteed to be tradeable at meaningful volume.

## Setup

1. Clone this repo and install dependencies: `pip install kalshi_python_sync python-dotenv`
2. Create a `.env` file in the project root (not committed to this repo) with the following two lines, replacing the placeholder values with your own:
```
   KALSHI_API_KEY_ID=your_key_id
   KALSHI_PRIVATE_KEY_PATH=path/to/your/private_key.txt
```

3. Run: `python main.py`

## Key technical challenges solved

- **Bid/ask confusion**: an early version compared raw bid prices instead of deriving true ask prices, causing every market to falsely register as arbitrage
- **API scale and rate limits**: an unscoped, exchange-wide scan failed to complete after 4+ hours and triggered rate-limit errors; switching to a curated, series-scoped approach reduced this to a reliable, repeatable process
- Validated at scale: 30,000+ individual markets checked across 15+ market categories
