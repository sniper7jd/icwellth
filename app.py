import streamlit as st
import pandas as pd
import datetime
import os
import robin_stocks.robinhood as r
from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv()
RH_USERNAME = os.getenv("RH_USERNAME")
RH_PASSWORD = os.getenv("RH_PASSWORD")

# --- Page Configuration ---
st.set_page_config(page_title="Local Wealth Manager", layout="wide")
st.title("💰 Personal Net Worth Dashboard")
st.markdown("___")

# --- Live Data Fetching ---
@st.cache_data(ttl=300) # Caches the data for 5 minutes to avoid spamming the API
def fetch_live_data():
    try:
        # 1. Authenticate with Robinhood
        r.login(RH_USERNAME, RH_PASSWORD)
        
        # 2. Fetch live total equity
        rh_profile = r.profiles.load_portfolio_profile()
        rh_equity = float(rh_profile.get('equity', 0.0))
        
    except Exception as e:
        st.error(f"Failed to connect to Robinhood: {e}")
        rh_equity = 0.0

    # 3. Combine live data with static/mock data for other accounts
    return {
        "Cash (Mock)": 4500.00,
        "Equities (Robinhood Live)": rh_equity,
        "Retirement (Fidelity Mock)": 8300.25,
        "Credit Card (Chase Mock)": -1200.50
    }

assets = fetch_live_data()
net_worth = sum(assets.values())

# --- Top Level Metrics ---
col1, col2, col3 = st.columns(3)
col1.metric("Total Net Worth", f"${net_worth:,.2f}")
col2.metric("Total Assets", f"${sum(v for v in assets.values() if v > 0):,.2f}")
col3.metric("Total Liabilities", f"${sum(v for v in assets.values() if v < 0):,.2f}")

st.markdown("___")

# --- Breakdown & Visualization ---
st.subheader("Asset Breakdown")
col_chart, col_data = st.columns([2, 1])

df_assets = pd.DataFrame(list(assets.items()), columns=["Account", "Balance"])

with col_chart:
    st.bar_chart(df_assets.set_index("Account"))

with col_data:
    st.dataframe(df_assets, hide_index=True, use_container_width=True)
    
st.caption(f"Last synced: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")