import pandas as pd
import os

# Define local storage files
FILES = {
    "bank": "bank_ledger.csv",
    "credit": "credit_ledger.csv",
    "portfolio": "portfolio_holdings.csv"
}

def load_data(file_key, columns):
    """Loads a CSV or creates an empty dataframe with specified columns."""
    if os.path.exists(FILES[file_key]):
        return pd.read_csv(FILES[file_key])
    return pd.DataFrame(columns=columns)

def save_data(file_key, df):
    """Saves the dataframe back to the local CSV."""
    df.to_csv(FILES[file_key], index=False)