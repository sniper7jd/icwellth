import streamlit as st
import pandas as pd
from datetime import date
from data_manager import load_data, save_data

st.set_page_config(page_title="Credit Cards", layout="wide")
st.title("💳 Credit Cards")

# Load existing credit card data
df = load_data("credit", ["Date", "Card Name", "Type", "Amount", "Description"])

# --- Add New Transaction ---
with st.expander("➕ Log Credit Transaction"):
    with st.form("add_credit_tx", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        tx_date = c1.date_input("Date", value=date.today())
        card_name = c2.selectbox("Card", ["Chase Sapphire", "Fidelity Visa", "Other"])
        # Standard accounting terms for credit accounts
        tx_type = c3.selectbox("Type", ["Debit", "Credit"])
        
        c4, c5 = st.columns([1, 2])
        amount = c4.number_input("Amount ($)", min_value=0.0, step=0.01)
        desc = c5.text_input("Description", placeholder="e.g., Cloud Hosting, Groceries, etc.")
        
        if st.form_submit_button("Save Transaction") and amount > 0:
            new_row = pd.DataFrame([{
                "Date": tx_date, "Card Name": card_name, 
                "Type": tx_type, "Amount": amount, "Description": desc
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            save_data("credit", df)
            st.success("Transaction saved!")
            st.rerun()

# --- Display Debt by Card ---
if not df.empty:
    st.markdown("### Outstanding Balances")
    cards = df["Card Name"].unique()
    
    cols = st.columns(len(cards))
    
    for i, card in enumerate(cards):
        card_df = df[df["Card Name"] == card]
        # Calculate debt: Debits (Spending) - Credits (Payments)
        debt = card_df[card_df["Type"] == "Debit"].Amount.astype(float).sum() - card_df[card_df["Type"] == "Credit"].Amount.astype(float).sum()
        
        # Display in red if there is debt, green if overpaid
        if debt > 0:
            cols[i].metric(card, f"${debt:,.2f}", delta="Debt", delta_color="inverse")
        else:
            cols[i].metric(card, f"${debt:,.2f}", delta="Paid Off", delta_color="normal")

    # --- Master Ledger ---
    st.markdown("___")
    st.write("**Edit Master Ledger** (Select a row's left edge and press Delete to remove)")
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    
    if st.button("Save Edits"):
        save_data("credit", edited_df)
        st.success("Ledger updated!")
        st.rerun()
else:
    st.info("No credit card transactions logged yet.")