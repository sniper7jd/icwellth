from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import sqlite3
import yfinance as yf
from datetime import date
import uvicorn

app = FastAPI()
templates = Jinja2Templates(directory="templates")

def get_db():
    conn = sqlite3.connect("wealth.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY, name TEXT, type TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY, account_id INTEGER, date TEXT, type TEXT, amount REAL, description TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS portfolio (id INTEGER PRIMARY KEY, brokerage TEXT, ticker TEXT, shares REAL, avg_cost REAL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS emulator_holdings (id INTEGER PRIMARY KEY, ticker TEXT, shares REAL, avg_cost REAL)''')
    conn.commit()
    conn.close()

init_db()

# --- DASHBOARD ROUTE ---
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    conn = get_db()
    
    # Calculate Cash
    # Calculate Cash
    cash_data = conn.execute('''
        SELECT transactions.type, SUM(transactions.amount) as total 
        FROM transactions 
        JOIN accounts ON transactions.account_id = accounts.id 
        WHERE accounts.type = 'Bank Account' 
        GROUP BY transactions.type
    ''').fetchall()
    
    # Bank: Debit adds, Credit subtracts (also legacy Deposit/Withdrawal)
    bank_in = sum([row['total'] for row in cash_data if row['type'] in ('Debit', 'Deposit')])
    bank_out = sum([row['total'] for row in cash_data if row['type'] in ('Credit', 'Withdrawal')])
    total_cash = bank_in - bank_out

    # Calculate Debt - Credit Card: Expense adds debt, Refund/Payment subtract (also legacy Debit/Credit)
    credit_data = conn.execute('''
        SELECT transactions.type, SUM(transactions.amount) as total 
        FROM transactions 
        JOIN accounts ON transactions.account_id = accounts.id 
        WHERE accounts.type = 'Credit Card' 
        GROUP BY transactions.type
    ''').fetchall()
    debt_in = sum([row['total'] for row in credit_data if row['type'] in ('Expense', 'Debit')])
    debt_out = sum([row['total'] for row in credit_data if row['type'] in ('Refund', 'Payment', 'Credit')])
    total_debt = debt_in - debt_out
    # Calculate Portfolio - fetch each ticker individually for reliable price
    portfolio = conn.execute("SELECT * FROM portfolio").fetchall()
    total_invested = 0.0
    if portfolio:
        for row in portfolio:
            try:
                data = yf.download(row['ticker'], period="1d", progress=False, auto_adjust=True)
                if not data.empty and 'Close' in data.columns:
                    price = float(data['Close'].iloc[-1])
                else:
                    info = yf.Ticker(row['ticker']).info
                    price = info.get('regularMarketPrice') or info.get('previousClose') or row['avg_cost']
                total_invested += price * row['shares']
            except Exception:
                total_invested += row['shares'] * row['avg_cost']

    net_worth = total_cash - total_debt + total_invested
    accounts = conn.execute("SELECT * FROM accounts").fetchall()
    conn.close()

    def fmt(v):
        return f"{(v if v != 0 else 0):,.2f}"
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "net_worth": fmt(net_worth), "total_cash": fmt(total_cash),
        "total_debt": fmt(total_debt), "total_debt_abs": fmt(abs(total_debt)),
        "total_invested": fmt(total_invested), "accounts": accounts,
        "net_worth_val": net_worth, "total_cash_val": total_cash, "total_debt_val": total_debt, "total_invested_val": total_invested,
        "chart_history": [net_worth * 0.9, net_worth * 0.95, net_worth * 0.98, net_worth * 1.02, net_worth]
    })

# --- ACCOUNT ROUTES ---
@app.post("/add_account")
async def add_account(name: str = Form(...), type: str = Form(...)):
    conn = get_db()
    conn.execute("INSERT INTO accounts (name, type) VALUES (?, ?)", (name, type))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.get("/account/{account_id}", response_class=HTMLResponse)
async def view_account(request: Request, account_id: int):
    conn = get_db()
    account = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    txs = conn.execute("SELECT * FROM transactions WHERE account_id=? ORDER BY date DESC", (account_id,)).fetchall()
    
    # Calculate specific account balance
    bal = 0.0
    if account['type'] == 'Bank Account':
        for tx in txs:
            if tx['type'] in ('Debit', 'Deposit'): bal += tx['amount']
            else: bal -= tx['amount']
    else:  # Credit Card
        for tx in txs:
            if tx['type'] in ('Expense', 'Debit'): bal += tx['amount']
            else: bal -= tx['amount']
        
    conn.close()
    return templates.TemplateResponse("account.html", {"request": request, "account": account, "transactions": txs, "balance": f"{bal:,.2f}"})

@app.post("/account/{account_id}/transaction")
async def add_transaction(account_id: int, type: str = Form(...), amount: float = Form(...), description: str = Form(...)):
    conn = get_db()
    conn.execute("INSERT INTO transactions (account_id, date, type, amount, description) VALUES (?, ?, ?, ?, ?)", 
                 (account_id, date.today().isoformat(), type, amount, description))
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/account/{account_id}", status_code=303)

@app.post("/account/{account_id}/delete")
async def delete_account(account_id: int):
    conn = get_db()
    conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
    conn.execute("DELETE FROM transactions WHERE account_id=?", (account_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

# --- PORTFOLIO ROUTES ---
@app.get("/portfolio", response_class=HTMLResponse)
async def view_portfolio(request: Request):
    conn = get_db()
    portfolio = conn.execute("SELECT * FROM portfolio").fetchall()
    conn.close()
    return templates.TemplateResponse("portfolio.html", {"request": request, "portfolio": portfolio})

@app.post("/add_holding")
async def add_holding(brokerage: str = Form(...), ticker: str = Form(...), shares: float = Form(...), avg_cost: float = Form(...)):
    conn = get_db()
    conn.execute("INSERT INTO portfolio (brokerage, ticker, shares, avg_cost) VALUES (?, ?, ?, ?)", 
                 (brokerage, ticker.upper(), shares, avg_cost))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/portfolio", status_code=303)

@app.post("/portfolio/remove/{holding_id}")
async def portfolio_remove(holding_id: int):
    conn = get_db()
    conn.execute("DELETE FROM portfolio WHERE id=?", (holding_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/portfolio", status_code=303)

# --- PORTFOLIO EMULATOR ---
@app.get("/emulator", response_class=HTMLResponse)
async def emulator_page(request: Request):
    conn = get_db()
    holdings = conn.execute("SELECT * FROM emulator_holdings").fetchall()
    conn.close()
    return templates.TemplateResponse("emulator.html", {
        "request": request, "holdings": [dict(h) for h in holdings],
        "error": request.query_params.get("error", ""),
        "error_ticker": request.query_params.get("ticker", "")
    })

def _is_valid_ticker(ticker: str) -> bool:
    """Verify ticker exists in Yahoo Finance search (catches typos like mfst)."""
    try:
        search = yf.Search(ticker)
        quotes = list(getattr(search, 'quotes', None) or [])
        valid_symbols = {q.get('symbol', '').upper() for q in quotes if q.get('quoteType') in ('EQUITY', 'ETF', 'MUTUALFUND')}
        return ticker.upper() in valid_symbols
    except Exception:
        return False

@app.post("/emulator/add")
async def emulator_add(ticker: str = Form(...), shares: float = Form(...), avg_cost: float = Form(default=0.0)):
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) < 2:
        return RedirectResponse(url="/emulator?error=invalid_ticker&ticker=" + ticker, status_code=303)
    if not _is_valid_ticker(ticker):
        return RedirectResponse(url="/emulator?error=invalid_ticker&ticker=" + ticker, status_code=303)
    use_fetched = avg_cost is None or avg_cost <= 0
    if use_fetched:
        avg_cost = 0
        try:
            data = yf.download(ticker, period="1d", progress=False, auto_adjust=True, threads=False)
            if not data.empty:
                last = data['Close'].iloc[-1]
                avg_cost = round(float(last.squeeze()) if hasattr(last, 'squeeze') else float(last), 2)
            if avg_cost <= 0:
                info = yf.Ticker(ticker).info
                avg_cost = float(info.get('regularMarketPrice') or info.get('previousClose') or 0)
        except Exception:
            pass
    if avg_cost <= 0:
        return RedirectResponse(url="/emulator?error=invalid_ticker&ticker=" + ticker, status_code=303)
    conn = get_db()
    conn.execute("INSERT INTO emulator_holdings (ticker, shares, avg_cost) VALUES (?, ?, ?)", 
                 (ticker, shares, avg_cost))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/emulator", status_code=303)

@app.post("/emulator/remove/{holding_id}")
async def emulator_remove(holding_id: int):
    conn = get_db()
    conn.execute("DELETE FROM emulator_holdings WHERE id=?", (holding_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/emulator", status_code=303)

@app.post("/emulator/sell/{holding_id}")
async def emulator_sell(holding_id: int, shares: float = Form(...)):
    conn = get_db()
    row = conn.execute("SELECT * FROM emulator_holdings WHERE id=?", (holding_id,)).fetchone()
    if not row:
        conn.close()
        return RedirectResponse(url="/emulator", status_code=303)
    new_shares = row['shares'] - shares
    if new_shares <= 0:
        conn.execute("DELETE FROM emulator_holdings WHERE id=?", (holding_id,))
    else:
        conn.execute("UPDATE emulator_holdings SET shares=? WHERE id=?", (new_shares, holding_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/emulator", status_code=303)

@app.get("/api/emulator/prices")
async def api_emulator_prices():
    conn = get_db()
    holdings = conn.execute("SELECT * FROM emulator_holdings").fetchall()
    conn.close()
    tickers = list(set([h['ticker'] for h in holdings]))
    result = {}
    for t in tickers:
        try:
            data = yf.download(t, period="1d", progress=False, auto_adjust=True)
            if not data.empty and 'Close' in data.columns:
                result[t] = round(float(data['Close'].iloc[-1]), 2)
            else:
                row = next((h for h in holdings if h['ticker'] == t), None)
                result[t] = row['avg_cost'] if row else 0
        except Exception:
            row = next((h for h in holdings if h['ticker'] == t), None)
            result[t] = row['avg_cost'] if row else 0
    holdings_data = []
    for h in holdings:
        price = result.get(h['ticker'], h['avg_cost'])
        value = round(h['shares'] * price, 2)
        cost_basis = round(h['shares'] * h['avg_cost'], 2)
        gain_loss = round(value - cost_basis, 2)
        holdings_data.append({
            "id": h['id'], "ticker": h['ticker'], "shares": h['shares'], "avg_cost": h['avg_cost'],
            "price": price, "value": value, "cost_basis": cost_basis, "gain_loss": gain_loss
        })
    total_value = sum(h["value"] for h in holdings_data)
    total_cost = sum(h["cost_basis"] for h in holdings_data)
    total_gain_loss = round(total_value - total_cost, 2)
    return JSONResponse({"prices": result, "holdings": holdings_data, "total_gain_loss": total_gain_loss})

@app.get("/api/emulator/search")
async def api_emulator_search(q: str = ""):
    """Ticker autocomplete - returns symbol, name for dropdown"""
    q = (q or "").strip()
    if len(q) < 1:
        return JSONResponse({"results": []})
    try:
        search = yf.Search(q)
        quotes = list(getattr(search, 'quotes', None) or [])
        results = []
        seen = set()
        for item in quotes[:12]:
            sym = (item.get('symbol') or '').upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            name = item.get('shortname') or item.get('longname') or sym
            qt = item.get('quoteType', '')
            if qt in ('EQUITY', 'ETF', 'MUTUALFUND'):
                results.append({"symbol": sym, "name": name})
        return JSONResponse({"results": results[:10]})
    except Exception:
        return JSONResponse({"results": []})

@app.get("/api/emulator/history/{ticker}")
async def api_emulator_history(ticker: str, period: str = "1mo"):
    try:
        t = yf.Ticker(ticker.upper())
        hist = t.history(period=period)
        if hist.empty:
            return JSONResponse({"labels": [], "data": []})
        hist = hist.reset_index()
        labels = [d.strftime("%Y-%m-%d") for d in hist['Date']]
        data = [round(float(p), 2) for p in hist['Close']]
        return JSONResponse({"labels": labels, "data": data})
    except Exception:
        return JSONResponse({"labels": [], "data": []})

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)