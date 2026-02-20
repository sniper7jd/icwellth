import streamlit as st
import pandas as pd
import yfinance as yf
from data_manager import load_data, save_data

st.set_page_config(page_title="Portfolios", layout="wide")
st.title("📈 Portfolio Emulator")

# Load existing holdings
df = load_data("portfolio", ["Brokerage", "Ticker", "Shares", "Avg Cost"])

# --- Add New Position ---
with st.expander("➕ Add New Holding"):
    with st.form("add_holding", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        brokerage = c1.selectbox("Brokerage", ["Robinhood", "Fidelity", "Student Fund", "Other"])
        # Adding a familiar default ticker to test the yfinance pull
        ticker = c2.text_input("Ticker Symbol", value="STRL").upper()
        shares = c3.number_input("Shares", min_value=0.0, step=1.0)
        cost = c4.number_input("Avg Cost ($)", min_value=0.0, step=0.01)
        
        if st.form_submit_button("Add to Portfolio") and ticker:
            new_row = pd.DataFrame([{"Brokerage": brokerage, "Ticker": ticker, "Shares": shares, "Avg Cost": cost}])
            df = pd.concat([df, new_row], ignore_index=True)
            save_data("portfolio", df)
            st.success(f"Added {ticker} to {brokerage}!")
            st.rerun()

# --- Live Emulator ---
if not df.empty:
    st.markdown("### Live Brokerage Breakdown")
    
    # Group by Brokerage so you can see Robinhood vs Fidelity separate
    brokerages = df["Brokerage"].unique()
    
    for broker in brokerages:
        st.subheader(f"🏛️ {broker}")
        broker_df = df[df["Brokerage"] == broker].copy()
        
        # Fetch live prices for this specific brokerage
        tickers = broker_df["Ticker"].unique().tolist()
        try:
            prices = yf.download(tickers, period="1d", progress=False)['Close']
            
            # Calculate live values
            live_values = []
            for t in broker_df["Ticker"]:
                price = float(prices.iloc[-1]) if len(tickers) == 1 else float(prices[t].iloc[-1])
                live_values.append(price)
                
            broker_df["Live Price"] = live_values
            broker_df["Total Value"] = broker_df["Shares"].astype(float) * broker_df["Live Price"]
            broker_df["P/L ($)"] = broker_df["Total Value"] - (broker_df["Shares"].astype(float) * broker_df["Avg Cost"].astype(float))
            
            st.dataframe(
                broker_df, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Total Value": st.column_config.NumberColumn(format="$%.2f"),
                    "P/L ($)": st.column_config.NumberColumn(format="$%.2f")
                }
            )
        except Exception as e:
            st.warning(f"Could not fetch live market data: {e}")
            st.dataframe(broker_df, use_container_width=True, hide_index=True)
            
    # Allow deletion/editing of the raw master table
    st.markdown("___")
    st.write("**Edit Master Holdings** (Delete rows by selecting the left column and pressing Backspace)")
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    if st.button("Save Edits"):
        save_data("portfolio", edited_df)
        st.success("Holdings updated!")
        st.rerun()
else:
    st.info("No holdings yet. Add a stock above to start the emulator.")