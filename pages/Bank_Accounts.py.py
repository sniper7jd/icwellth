import streamlit as st
import pandas as pd
from datetime import date
from data_manager import load_data, save_data

st.set_page_config(page_title="Bank Accounts", layout="wide")
st.title("🏦 Bank Accounts")

# Load existing bank data
df = load_data("bank", ["Date", "Account Name", "Type", "Amount", "Description"])

# --- Add New Transaction ---
with st.expander("➕ Log Bank Transaction"):
    with st.form("add_bank_tx", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        tx_date = c1.date_input("Date", value=date.today())
        acc_name = c2.selectbox("Account", ["Chase Checking", "Local Savings", "Other"])
        tx_type = c3.selectbox("Type", ["Deposit", "Withdrawal"])
        
        c4, c5 = st.columns([1, 2])
        amount = c4.number_input("Amount ($)", min_value=0.0, step=0.01)
        # Defaulting to common expenses
        desc = c5.text_input("Description", placeholder="e.g., Campus Job Paycheck, Bus Ticket, etc.")
        
        if st.form_submit_button("Save Transaction") and amount > 0:
            new_row = pd.DataFrame([{
                "Date": tx_date, "Account Name": acc_name, 
                "Type": tx_type, "Amount": amount, "Description": desc
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            save_data("bank", df)
            st.success("Transaction saved!")
            st.rerun()

# --- Display Balances by Account ---
if not df.empty:
    st.markdown("### Account Balances")
    accounts = df["Account Name"].unique()
    
    # Create dynamic columns based on how many accounts you have
    cols = st.columns(len(accounts))
    
    for i, acc in enumerate(accounts):
        acc_df = df[df["Account Name"] == acc]
        # Calculate balance: Deposits - Withdrawals
        balance = acc_df[acc_df["Type"] == "Deposit"].Amount.astype(float).sum() - acc_df[acc_df["Type"] == "Withdrawal"].Amount.astype(float).sum()
        cols[i].metric(acc, f"${balance:,.2f}")

    # --- Master Ledger ---
    st.markdown("___")
    st.write("**Edit Master Ledger** (Select a row's left edge and press Delete to remove)")
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    
    if st.button("Save Edits"):
        save_data("bank", edited_df)
        st.success("Ledger updated!")
        st.rerun()
else:
    st.info("No bank transactions logged yet.")