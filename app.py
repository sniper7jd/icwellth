import streamlit as st
import pandas as pd
import yfinance as yf
import os
from datetime import date

st.set_page_config(page_title="Wealth App", layout="wide", initial_sidebar_state="expanded")

# --- 1. Database Setup ---
FILES = {"accounts": "accounts.csv", "txs": "transactions.csv", "portfolio": "portfolio.csv"}

def load_df(key, cols):
    if os.path.exists(FILES[key]): return pd.read_csv(FILES[key])
    return pd.DataFrame(columns=cols)

def save_df(key):
    st.session_state[key].to_csv(FILES[key], index=False)

if "accounts" not in st.session_state:
    st.session_state.accounts = load_df("accounts", ["Account Name", "Type"])
    st.session_state.txs = load_df("txs", ["Date", "Account Name", "Type", "Amount", "Description"])
    st.session_state.portfolio = load_df("portfolio", ["Brokerage", "Ticker", "Shares", "Avg Cost"])

# --- 2. Sidebar: Rare Actions (Setup & Settings) ---
with st.sidebar:
    st.header("⚙️ App Settings")
    st.markdown("Create new accounts or add stock holdings here.")
    
    with st.expander("🏦 Add Bank or Credit Card"):
        with st.form("new_account_form", clear_on_submit=True):
            new_acc_name = st.text_input("Account Name (e.g., Chase Checking)")
            new_acc_type = st.selectbox("Account Type", ["Bank Account", "Credit Card"])
            if st.form_submit_button("Create Account") and new_acc_name:
                if new_acc_name not in st.session_state.accounts["Account Name"].values:
                    new_row = pd.DataFrame([{"Account Name": new_acc_name, "Type": new_acc_type}])
                    st.session_state.accounts = pd.concat([st.session_state.accounts, new_row], ignore_index=True)
                    save_df("accounts")
                    st.success(f"{new_acc_name} created!")
                    st.rerun()

    with st.expander("📈 Add Stock Position"):
        with st.form("new_stock_form", clear_on_submit=True):
            brokerage = st.selectbox("Brokerage", ["Robinhood", "Fidelity", "Other"])
            ticker = st.text_input("Ticker Symbol").upper()
            shares = st.number_input("Shares", min_value=0.0, step=1.0)
            cost = st.number_input("Avg Cost ($)", min_value=0.0, step=0.01)
            if st.form_submit_button("Add Holding") and ticker:
                new_row = pd.DataFrame([{"Brokerage": brokerage, "Ticker": ticker, "Shares": shares, "Avg Cost": cost}])
                st.session_state.portfolio = pd.concat([st.session_state.portfolio, new_row], ignore_index=True)
                save_df("portfolio")
                st.success(f"{ticker} added!")
                st.rerun()

# --- 3. Dashboard Data Processing ---
# Calculate Cash
bank_txs = st.session_state.txs[st.session_state.txs["Account Name"].isin(st.session_state.accounts[st.session_state.accounts["Type"] == "Bank Account"]["Account Name"])]
total_cash = bank_txs[bank_txs["Type"] == "Deposit"].Amount.astype(float).sum() - bank_txs[bank_txs["Type"] == "Withdrawal"].Amount.astype(float).sum()

# Calculate Debt
credit_txs = st.session_state.txs[st.session_state.txs["Account Name"].isin(st.session_state.accounts[st.session_state.accounts["Type"] == "Credit Card"]["Account Name"])]
total_debt = credit_txs[credit_txs["Type"] == "Debit"].Amount.astype(float).sum() - credit_txs[credit_txs["Type"] == "Credit"].Amount.astype(float).sum()

# Calculate Live Portfolio
total_invested = 0.0
port_df = st.session_state.portfolio.copy()
if not port_df.empty:
    tickers = port_df["Ticker"].unique().tolist()
    try:
        live_data = yf.download(tickers, period="1d", progress=False)['Close']
        live_prices = []
        for t in port_df["Ticker"]:
            price = float(live_data.iloc[-1]) if len(tickers) == 1 else float(live_data[t].iloc[-1])
            live_prices.append(price)
            total_invested += price * float(port_df.loc[port_df["Ticker"] == t, "Shares"].values[0])
        port_df["Live Price"] = live_prices
        port_df["Total Value"] = port_df["Shares"].astype(float) * port_df["Live Price"]
    except Exception:
        port_df["Total Value"] = port_df["Shares"].astype(float) * port_df["Avg Cost"].astype(float)
        total_invested = port_df["Total Value"].sum()

net_worth = total_cash - total_debt + total_invested

# --- 4. Main UI: The Command Center ---
st.title("📊 Wealth Command Center")

# Top Level Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Net Worth", f"${net_worth:,.2f}")
c2.metric("Cash Balance", f"${total_cash:,.2f}")
c3.metric("Credit Card Debt", f"${total_debt:,.2f}", delta="Debt", delta_color="inverse")
c4.metric("Market Portfolio", f"${total_invested:,.2f}")

st.markdown("___")

# Visual Breakdown Chart
st.subheader("Asset Breakdown")
chart_data = pd.DataFrame({"Category": ["Cash", "Investments", "Credit Debt"], "Balance": [total_cash, total_invested, -total_debt]}).set_index("Category")
st.bar_chart(chart_data, height=200)

st.markdown("___")

# --- 5. Dynamic Account Cards ---
st.subheader("Your Accounts")

# Render Bank Accounts
bank_accounts = st.session_state.accounts[st.session_state.accounts["Type"] == "Bank Account"]["Account Name"].tolist()
for acc in bank_accounts:
    acc_data = st.session_state.txs[st.session_state.txs["Account Name"] == acc]
    bal = acc_data[acc_data["Type"] == "Deposit"].Amount.astype(float).sum() - acc_data[acc_data["Type"] == "Withdrawal"].Amount.astype(float).sum()
    
    with st.expander(f"🏦 {acc} | Balance: **${bal:,.2f}**"):
        with st.form(f"form_{acc}", clear_on_submit=True):
            col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
            tx_date = col1.date_input("Date", value=date.today(), key=f"d_{acc}")
            tx_type = col2.selectbox("Type", ["Deposit", "Withdrawal"], key=f"t_{acc}")
            amt = col3.number_input("Amount", min_value=0.0, step=0.01, key=f"a_{acc}")
            desc = col4.text_input("Description", key=f"desc_{acc}")
            if st.form_submit_button("Log Transaction") and amt > 0:
                new_tx = pd.DataFrame([{"Date": tx_date, "Account Name": acc, "Type": tx_type, "Amount": amt, "Description": desc}])
                st.session_state.txs = pd.concat([st.session_state.txs, new_tx], ignore_index=True)
                save_df("txs")
                st.rerun()
        if not acc_data.empty: st.dataframe(acc_data.tail(5), hide_index=True, use_container_width=True)

# Render Credit Cards
credit_accounts = st.session_state.accounts[st.session_state.accounts["Type"] == "Credit Card"]["Account Name"].tolist()
for acc in credit_accounts:
    acc_data = st.session_state.txs[st.session_state.txs["Account Name"] == acc]
    bal = acc_data[acc_data["Type"] == "Debit"].Amount.astype(float).sum() - acc_data[acc_data["Type"] == "Credit"].Amount.astype(float).sum()
    
    with st.expander(f"💳 {acc} | Outstanding: **${bal:,.2f}**"):
        with st.form(f"form_{acc}", clear_on_submit=True):
            col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
            tx_date = col1.date_input("Date", value=date.today(), key=f"d_{acc}")
            tx_type = col2.selectbox("Type", ["Debit", "Credit"], key=f"t_{acc}")
            amt = col3.number_input("Amount", min_value=0.0, step=0.01, key=f"a_{acc}")
            desc = col4.text_input("Description", key=f"desc_{acc}")
            if st.form_submit_button("Log Transaction") and amt > 0:
                new_tx = pd.DataFrame([{"Date": tx_date, "Account Name": acc, "Type": tx_type, "Amount": amt, "Description": desc}])
                st.session_state.txs = pd.concat([st.session_state.txs, new_tx], ignore_index=True)
                save_df("txs")
                st.rerun()
        if not acc_data.empty: st.dataframe(acc_data.tail(5), hide_index=True, use_container_width=True)

# Render Portfolio
with st.expander(f"📈 Investment Portfolio | Value: **${total_invested:,.2f}**"):
    if not port_df.empty:
        st.dataframe(port_df, hide_index=True, use_container_width=True, 
                     column_config={"Total Value": st.column_config.NumberColumn(format="$%.2f")})
    else:
        st.info("No holdings yet. Add stocks via the sidebar.")