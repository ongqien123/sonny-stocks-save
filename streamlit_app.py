"""
Stock Watchlist Dashboard
-------------------------
A simple, auto-refreshing Streamlit dashboard that shows live quotes
for a custom watchlist of stocks and indices, using Yahoo Finance
(via the yfinance library) — no API key required.

Run with:
    streamlit run streamlit_app.py
"""

from datetime import datetime

import pandas as pd
import streamlit as st
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
st.set_page_config(page_title="Stock Watchlist Dashboard", layout="wide")

# Grouped by market/currency, since mixing USD and SGD stocks on one
# chart would be misleading. SPY is used as the S&P 500 proxy (more
# reliable in Yahoo Finance than the raw ^GSPC index ticker).
US_TICKERS = ["GOOG", "AAPL", "NVDA", "MSFT", "AMZN"]
SG_TICKERS = ["D05.SI", "S63.SI", "O39.SI"]  # DBS, ST Engineering, OCBC Bank
ETF_TICKERS = ["SPY"]  # State Street SPDR S&P 500 ETF Trust

DEFAULT_TICKERS = US_TICKERS + SG_TICKERS + ETF_TICKERS

# --------------------------------------------------------------------------
# SIDEBAR — SETTINGS
# --------------------------------------------------------------------------
st.sidebar.title("⚙️ Settings")
st.sidebar.caption(
    "Data comes from Yahoo Finance (via yfinance) — no API key needed. "
    "Use `.SI` suffix for Singapore Exchange stocks (e.g. `D05.SI` for DBS, "
    "`S63.SI` for ST Engineering, `O39.SI` for OCBC Bank), and `SPY` as a "
    "liquid proxy for the S&P 500."
)

tickers_input = st.sidebar.text_area(
    "Watchlist (comma-separated tickers)",
    value=", ".join(DEFAULT_TICKERS),
    height=80,
)
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

refresh_seconds = st.sidebar.slider(
    "Auto-refresh interval (seconds)", min_value=15, max_value=300, value=30, step=15
)

show_names = st.sidebar.checkbox("Show company names", value=True)

# Auto-refresh the whole app on the chosen interval
st_autorefresh(interval=refresh_seconds * 1000, key="datarefresh")

# --------------------------------------------------------------------------
# MAIN TITLE
# --------------------------------------------------------------------------
st.title("📈 Stock Watchlist Dashboard")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if not tickers:
    st.info("Add at least one ticker to your watchlist in the sidebar.")
    st.stop()

# --------------------------------------------------------------------------
# DATA FETCHING
# --------------------------------------------------------------------------
@st.cache_data(ttl=60 * 60 * 24)  # company names rarely change; cache for a day
def get_company_name(symbol: str) -> str:
    try:
        info = yf.Ticker(symbol).info
        return info.get("longName") or info.get("shortName") or symbol
    except Exception:
        return symbol


def get_quote(symbol: str) -> dict:
    try:
        info = yf.Ticker(symbol).info
        current = info.get("regularMarketPrice") or info.get("currentPrice")
        prev_close = info.get("regularMarketPreviousClose") or info.get(
            "previousClose"
        )
        if current is None or prev_close is None:
            return {"error": "missing price data"}
        return {
            "c": current,
            "pc": prev_close,
            "d": current - prev_close,
            "dp": ((current - prev_close) / prev_close * 100) if prev_close else 0,
            "h": info.get("dayHigh", 0),
            "l": info.get("dayLow", 0),
            "o": info.get("regularMarketOpen") or info.get("open", 0),
        }
    except Exception as e:
        return {"error": str(e)}


rows = []
errors = []

for symbol in tickers:
    quote = get_quote(symbol)

    if "error" in quote:
        errors.append(symbol)
        continue

    current = quote.get("c", 0)
    change = quote.get("d", 0)
    pct_change = quote.get("dp", 0)
    high = quote.get("h", 0)
    low = quote.get("l", 0)
    open_price = quote.get("o", 0)
    prev_close = quote.get("pc", 0)

    name = get_company_name(symbol) if show_names else symbol

    rows.append(
        {
            "Ticker": symbol,
            "Name": name,
            "Price": current,
            "Change": change,
            "% Change": pct_change,
            "Open": open_price,
            "High": high,
            "Low": low,
            "Prev Close": prev_close,
        }
    )

# --------------------------------------------------------------------------
# DISPLAY
# --------------------------------------------------------------------------
if errors:
    st.error(
        f"Couldn't fetch data for: {', '.join(errors)}. "
        "Double-check the ticker symbol (e.g. `.SI` suffix for SGX stocks, "
        "`^` prefix for indices), or Yahoo Finance may be temporarily "
        "rate-limiting requests — try again in a moment."
    )

if rows:
    df = pd.DataFrame(rows)

    # Summary metric cards
    cols = st.columns(min(len(df), 6))
    for i, (_, row) in enumerate(df.iterrows()):
        with cols[i % len(cols)]:
            st.metric(
                label=row["Ticker"],
                value=f"${row['Price']:.2f}",
                delta=f"{row['Change']:.2f} ({row['% Change']:.2f}%)",
            )

    st.markdown("---")

    # Styled table
    def color_change(val):
        color = "green" if val > 0 else "red" if val < 0 else "gray"
        return f"color: {color}"

    styled_df = (
        df.style.map(color_change, subset=["Change", "% Change"])
        .format(
            {
                "Price": "${:.2f}",
                "Change": "{:+.2f}",
                "% Change": "{:+.2f}%",
                "Open": "${:.2f}",
                "High": "${:.2f}",
                "Low": "${:.2f}",
                "Prev Close": "${:.2f}",
            }
        )
    )

    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    # ----------------------------------------------------------------------
    # BIGGEST MOVERS (TOP 3 BY ABSOLUTE % CHANGE)
    # ----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("🚩 Biggest movers today")
    top_movers = df.reindex(
        df["% Change"].abs().sort_values(ascending=False).index
    ).head(3)
    for _, row in top_movers.iterrows():
        direction = "🔺" if row["% Change"] > 0 else "🔻"
        st.write(f"{direction} **{row['Ticker']}** — {row['% Change']:+.2f}%")

    # ----------------------------------------------------------------------
    # HISTORICAL TRENDS, GROUPED BY MARKET
    # ----------------------------------------------------------------------
    st.markdown("---")
    period_choice = st.radio("Time range", ["1 Month", "1 Year"], horizontal=True)
    period_map = {"1 Month": "1mo", "1 Year": "1y"}
    selected_period = period_map[period_choice]

    st.header(f"📊 Price Trends ({period_choice})")
    st.caption(
        "Charts are grouped by market/currency (US stocks in USD, "
        "Singapore stocks in SGD) so prices stay comparable within each chart."
    )

    @st.cache_data(ttl=60 * 15)  # historical daily data refreshes every 15 min
    def get_history(symbol: str, period: str = "1mo"):
        try:
            hist = yf.Ticker(symbol).history(period=period)
            return hist["Close"] if not hist.empty else pd.Series(dtype=float)
        except Exception:
            return pd.Series(dtype=float)

    normalize = st.checkbox(
        "Show % change instead of raw price (recommended — makes lines comparable)",
        value=True,
    )

    def plot_group(title: str, symbols: list):
        st.subheader(title)
        relevant = [s for s in symbols if s in tickers]
        if not relevant:
            st.caption("No tickers from this group are in your current watchlist.")
            return
        series_data = {}
        for sym in relevant:
            s = get_history(sym, period=selected_period)
            if not s.empty:
                series_data[sym] = s
        if series_data:
            hist_df = pd.DataFrame(series_data)
            if normalize:
                hist_df = (hist_df / hist_df.iloc[0] - 1) * 100
                st.line_chart(hist_df)
                st.caption("Y-axis: % change since start of period")
            else:
                st.line_chart(hist_df)
        else:
            st.caption(f"No historical data available for: {', '.join(relevant)}")

    plot_group("🇺🇸 US Stocks (USD)", US_TICKERS)
    plot_group("🇸🇬 Singapore Stocks (SGD)", SG_TICKERS)
    plot_group("📈 ETFs / Indices (USD)", ETF_TICKERS)
else:
    st.info("No data to display yet.")