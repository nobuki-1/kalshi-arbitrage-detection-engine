import os
from dotenv import load_dotenv
from kalshi_python_sync import KalshiClient, MarketApi, Configuration, KalshiAuth


import time
# 1. Read keys from .env
load_dotenv()



API_KEY_ID = os.getenv("KALSHI_API_KEY_ID")
PRIVATE_KEY_PATH = os.getenv("KALSHI_PRIVATE_KEY_PATH")

def initialize_kalshi_client():
    with open(PRIVATE_KEY_PATH, "r") as f:
      private_key_pem = f.read()

    auth = KalshiAuth(
      key_id=API_KEY_ID,
      private_key_pem=private_key_pem,
    )

    config = Configuration()
    config.host = "https://external-api.kalshi.com/trade-api/v2"

    client = KalshiClient(configuration=config)
    client.auth = auth  # attach auth to client — confirm this attribute name works; if it errors, run: python -c "import kalshi_python_sync; print(dir(kalshi_python_sync.KalshiClient))"

    #print("Successfully connected to Kalshi PRODUCTION API client.")
    return client

#kalshi lists its prices as [price, quantity]
def get_market_prices(market_api, ticker):
  try:
    orderbook = market_api.get_market_orderbook(ticker)
    if not orderbook:
      return None, None
    ob = getattr(orderbook, 'orderbook_fp', None)
    if not ob:
      return None, None
    yes_bids = getattr(ob,'yes_dollars', None) or []
    no_bids = getattr(ob, 'no_dollars', None) or []
    best_yes_order = float(yes_bids[-1][0]) if len(yes_bids) >0 else None
    best_no_order = float(no_bids[-1][0])  if len(no_bids) >0 else None
    return best_yes_order, best_no_order
  except Exception as e:
    print(f"Error fetching ticker {ticker}: {e}")
    return None, None

def check_arbitrage(yes_price, no_price):
  implied_yes_ask = 1 - no_price
  implied_no_ask = 1 - yes_price
  yes_fee = fee_per_contract(implied_yes_ask)
  no_fee = fee_per_contract(implied_no_ask)
  total_ask_cost = implied_yes_ask + implied_no_ask + yes_fee + no_fee
  if total_ask_cost < 1:
    profit_per_contract = 1 - total_ask_cost
    return True, profit_per_contract
  return False, 0.0

#SERIES_TO_SCAN = ["KXMLBGAME", "KXATPCHALLENGERMATCH"]

client = initialize_kalshi_client()
market_api = MarketApi(client)

print("Yes ask is the best price available to buy a yes contract. No ask is best price for a no contract.")

response = market_api.get_series_list(category = 'Companies')
print(f"Total unique series: {len(response.series)}")

SERIES_TO_SCAN = []
for s in response.series:
  #if any(k in s.ticker for k in keywords):
  SERIES_TO_SCAN.append(s.ticker)
print(f"No. of series to scan: {len(SERIES_TO_SCAN)}") 

#Kalshi's taker fee = round up(0.07 × C × P × (1-P)), where C is number of contracts and P is the price as a decimal (e.g., 0.55 for 55¢)
def fee_per_contract(price):
  return round(0.07* price * (1-price), 4)


#volume is number of trades made that day, open interest represents those who hold trades from other days
def get_active_tickers(market_api, limit = 100):
  tickers = []
  for series in SERIES_TO_SCAN:
    try:
      response = market_api.get_markets(series_ticker=series, status="open", limit=limit)
      #add series_ticker="KXMLBGAME" in the brackets to search a specific market - this one does mlb matches
      #print(f"DEBUG: got {len(response.markets)} markets")

      if not response or not hasattr(response, 'markets'):
        continue
      for m in response.markets:
        if hasattr(m, 'ticker') and not m.ticker.startswith('KXMVE'):
          volume = float(getattr(m, 'volume_fp', 0) or 0)
          open_interest = float(getattr(m, 'open_interest_fp', 0) or 0)
          if volume > 0 or open_interest > 0:
            tickers.append(m.ticker)
      print(f"DEBUG: {series} — got {len(response.markets)} markets") #includes kxmve markets
      time.sleep(0.2)
    
    except Exception as e:
      print(f"Error fetching market list: {type(e).__name__}: {e}")
  return tickers

 



#time_delay is the time between running the function - it prevents too many request from crashing the page

def start_bot(time_delay=0.2, print_interval = 10):
  start_time = time.time()
  client = initialize_kalshi_client()
  market_api = MarketApi(client)
  last_wait_print = 0
  ticker_count = 0
  active_tickers = get_active_tickers(market_api)
  opportunity_count = 0
  arbitrage_opportunities = []
  if not active_tickers:
    #if now - last_wait_print > print_interval:
    print("No active tickers found.") 
    #  last_wait_print = now
    #time.sleep(time_delay)
    return #returns nothing as nothing to return
  try:
    for ticker in active_tickers:
      yes_price, no_price = get_market_prices(market_api, ticker)
      time.sleep(0.2)
      if yes_price is not None and no_price is not None:
        title = market_api.get_market(ticker = ticker).market.title
        implied_yes_ask = 1 - no_price
        implied_no_ask = 1 - yes_price
        total_ask_cost = implied_yes_ask + implied_no_ask
        opportunity, profit = check_arbitrage(yes_price, no_price)
        ticker_count = ticker_count + 1
        if opportunity:
          print(f"\n[ARBITRAGE FOUND] Current prices, {title} - YES ask (implied): ${implied_yes_ask:.2f} | NO ask (implied): ${implied_no_ask:.2f} |Total ask cost: {total_ask_cost:.2f} | Profit = ${profit:.2f}")
          opportunity_count = opportunity_count + 1
          arbitrage_opportunities.append({"ticker": ticker, "title": title, "profit": profit, "yes_ask": implied_yes_ask, "no_ask": implied_no_ask, "profit": profit})
        else:
          print(f"NO ARBITRAGE: {ticker}, {title} current prices - YES${yes_price:.2f} | NO: ${no_price:.2f}")
      else:
        now2 = time.time()
        if now2 - last_wait_print > print_interval:
          print(f"Waiting for valid ticker data ({ticker})")
          last_wait_print = now2
  except KeyboardInterrupt:
    print(f"Bot manually stopped by user after {ticker_count} tickers")
    print(f"{opportunity_count} arbitrage opportunities have been found.")
    print(arbitrage_opportunities)
    end_time = time.time()
    print(f"Total run time was {end_time - start_time:.1f}s")
    return
  end_time = time.time()
  print(f"{ticker_count} tickers have been checked.")
  print(f"{opportunity_count} arbitrage opportunities have been found.")
  print(f"There were {arbitrage_opportunities} arbitrage opportunities")           
  print(f"Total run time was {end_time - start_time:.1f}s")
    



if __name__ == "__main__":
    # Test connection initialization
    client = initialize_kalshi_client()
    
    # 4. Create an instance of the Market API to fetch live order books
    market_api = MarketApi(client)
    #code below finds specific tickers for a category: now its mlb games
    #response = market_api.get_markets(series_ticker="KXMLBGAME", status="open", limit=20)
    #for m in response.markets:
    #  print(m.ticker, "-", m.title) 
    
    
    test_ticker = "KXPEPSIPOS-26OCT03-T98" 

    single_market = market_api.get_market(ticker=test_ticker).market
    #print("SINGLE MARKET DETAIL:", single_market)
    #the code below prints the relevant info, code above prints all the info including rules, subtitiles etc - irrelevant)
    #above, the .market at the end of the line, prevents having to write single_market.market.ticker.
    print(f"""
    Ticker:           {single_market.ticker}
    Title:            {single_market.title}
    Status:           {single_market.status}
    YES bid:          ${single_market.yes_bid_dollars}
    NO bid:           ${single_market.no_bid_dollars}
    YES ask:          ${single_market.yes_ask_dollars} 
    NO ask:           ${single_market.no_ask_dollars}
    YES ask + NO ask: ${float(single_market.yes_ask_dollars) + float(single_market.no_ask_dollars)}
    Last price:       ${single_market.last_price_dollars}
    Volume:           {single_market.volume_fp}
    Open interest:    {single_market.open_interest_fp}
    Close time:       {single_market.close_time}
    """)
    #YES bid/ask: yes bid / yes ask - yes bid: highest price someone offering to pay for a yes contract, yes ask: lowest price to sell a yes contract
    #No bid ask: no bid / no ask - no bid: highest price someone offers to pay for a no contract, no ask: highest price someone is willing to sell no contract
    #yes ask + no bid = $1
    orderbook = market_api.get_market_orderbook(ticker=test_ticker)
    #print("ORDERBOOK:", orderbook)
    #the code above prints all the possible bids, i filter them out so that only the relevant ones are printed
    ob = orderbook.orderbook_fp
    best_yes_bid_price, best_yes_bid_size = ob.yes_dollars[-1] 
    best_no_bid_price, best_no_bid_size = ob.no_dollars[-1]
    
    print(f"""
    Best YES bid: ${best_yes_bid_price} - {best_yes_bid_size} contracts available  →  implied NO ask: ${1 - float(best_yes_bid_price):.2f}
    Best NO bid:  ${best_no_bid_price} - {best_no_bid_size} contracts available →  implied YES ask: ${1 - float(best_no_bid_price):.2f}
    """)

    #print("Market API interface ready for data queries.")
    #markets = market_api.get_markets(limit=5)
    #print(markets)


start_bot()

#bid: how much someone is willing to pay for a contract - it is a buy order

#if best_yes_bid + best_no_bid > 1.00:
#    → you could sell both positions right now for more than the guaranteed $1 payout
# implied yes_ask = 1 - yes_bid and same for no_ask
# implied_yes_ask + implied_no_ask < 1 => arbitrage possible as you pay less than $1


def fetch_categories():
  client = initialize_kalshi_client()
  market_api = MarketApi(client)
  category_set = set()
  response = market_api.get_series_list()
  for s in response.series:
    if hasattr(s, 'category'):
      category_set.add(s.category)
  print(category_set)




