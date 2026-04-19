# ============================================================
# 📈 Investment & Wealth Engine
# Built by Mennahtullah Saeed
# Version 3.2 — Full Fixed Stable Version
# ============================================================

# ============================================================
# PART 1: المكتبات
# ============================================================
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import sqlite3
import warnings
import hashlib
import time
import random
import string
from io import BytesIO
from datetime import datetime, date, timedelta

warnings.filterwarnings('ignore')

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except:
    BCRYPT_AVAILABLE = False

try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except:
    TEXTBLOB_AVAILABLE = False

DB_PATH = "wealth_engine.db"
ADMIN_EMAIL    = "admin@wealthengine.com"
ADMIN_PASSWORD = "admin2024!"

# ============================================================
# PART 2: SOL 1 — Rate Limiter
# ============================================================
class RateLimiter:
    def __init__(self, min_interval=1.0):
        self.min_interval = min_interval
        self.last_called  = {}

    def wait_if_needed(self, key):
        now  = time.time()
        last = self.last_called.get(key, 0)
        elapsed = now - last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_called[key] = time.time()

rate_limiter = RateLimiter(min_interval=0.5)

# ============================================================
# PART 3: SOL 2 — Password Hashing
# ============================================================
def hash_password(password):
    if BCRYPT_AVAILABLE:
        salt   = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode(), salt)
        return hashed.decode()
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    if BCRYPT_AVAILABLE:
        try:
            return bcrypt.checkpw(password.encode(), hashed.encode())
        except:
            return hashed == hashlib.sha256(password.encode()).hexdigest()
    return hashed == hashlib.sha256(password.encode()).hexdigest()

# ============================================================
# PART 4: Database Setup
# ============================================================
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            full_name TEXT, plan TEXT DEFAULT 'free', analyses_count INTEGER DEFAULT 0,
            analyses_date TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, last_login TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS stock_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL, price_date TEXT NOT NULL,
            close_price REAL, asset_type TEXT DEFAULT 'stock', UNIQUE(ticker, price_date))""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS stock_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT NOT NULL, ticker TEXT NOT NULL,
            period TEXT NOT NULL, total_return REAL, volatility REAL, sharpe_ratio REAL, analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS reset_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL, code TEXT NOT NULL,
            expires_at TEXT NOT NULL, used INTEGER DEFAULT 0)""")
        conn.commit()

# ============================================================
# PART 5: SOL 3 — Forgot Password System
# ============================================================
def generate_reset_code(email):
    code = ''.join(random.choices(string.digits, k=6))
    expires_at = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reset_codes WHERE email = ?", (email,))
        cursor.execute("INSERT INTO reset_codes (email, code, expires_at) VALUES (?, ?, ?)", (email.lower(), code, expires_at))
        conn.commit()
    return code

def verify_reset_code(email, code):
    with get_conn() as conn:
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("SELECT id FROM reset_codes WHERE email=? AND code=? AND expires_at>? AND used=0", (email.lower(), code, now))
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE reset_codes SET used=1 WHERE id=?", (row["id"],))
            conn.commit()
            return True
    return False

def reset_password(email, new_password):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_hash = ? WHERE email = ?", (hash_password(new_password), email.lower()))
        conn.commit()
        return cursor.rowcount > 0

# ============================================================
# PART 6: User Functions
# ============================================================
def register_user(email, password, full_name):
    with get_conn() as conn:
        try:
            conn.execute("INSERT INTO users (email, password_hash, full_name) VALUES (?,?,?)",
                         (email.strip().lower(), hash_password(password), full_name.strip()))
            conn.commit()
            return True, "✅ Account created!"
        except sqlite3.IntegrityError:
            return False, "❌ Email already exists!"

def login_user(email, password):
    if email.strip().lower() == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD:
        return "admin", {"id": 0, "email": ADMIN_EMAIL, "full_name": "Admin", "plan": "admin"}
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        if row and verify_password(password, row["password_hash"]):
            return True, dict(row)
    return False, None

def get_user_from_db(email):
    if email == ADMIN_EMAIL: return st.session_state.user
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

def increment_analysis(email):
    if not email or email == ADMIN_EMAIL: return
    with get_conn() as conn:
        conn.execute("UPDATE users SET analyses_count = analyses_count + 1 WHERE email = ?", (email,))
        conn.commit()

def upgrade_to_pro(email):
    with get_conn() as conn:
        conn.execute("UPDATE users SET plan='pro' WHERE email=?", (email,))
        conn.commit()

def downgrade_to_free(email):
    with get_conn() as conn:
        conn.execute("UPDATE users SET plan='free' WHERE email=?", (email,))
        conn.commit()

def save_prices(data, tickers, asset_types):
    saved = 0
    with get_conn() as conn:
        for ticker in tickers:
            asset_type = asset_types.get(ticker, 'stock')
            col = data[ticker] if ticker in data.columns else data
            for date_idx, price in col.items():
                conn.execute("INSERT OR IGNORE INTO stock_prices (ticker, price_date, close_price, asset_type) VALUES (?,?,?,?)",
                             (ticker, str(date_idx.date()), round(float(price), 4), asset_type))
                saved += 1
        conn.commit()
    return saved

def save_metrics(risk_data, period, user_email):
    if not user_email: return
    with get_conn() as conn:
        for row in risk_data:
            try:
                conn.execute("INSERT INTO stock_metrics (user_email, ticker, period, total_return, volatility, sharpe_ratio) VALUES (?,?,?,?,?,?)",
                             (user_email, row["Asset"], period, float(str(row["Return"]).replace("%","")), float(str(row["Volatility"]).replace("%","")), float(row["Sharpe Ratio"])))
            except: continue
        conn.commit()

# ============================================================
# PART 7: SOL 1 — Data Fetching
# ============================================================
def fetch_data_safe(tickers, period):
    valid_data, errors = {}, []
    for ticker in tickers:
        try:
            rate_limiter.wait_if_needed(ticker)
            raw = yf.download(ticker, period=period, progress=False, auto_adjust=True)['Close']
            if not raw.empty:
                valid_data[ticker] = raw.dropna()
            else: errors.append(ticker)
        except: errors.append(ticker)
    return (pd.DataFrame(valid_data), list(valid_data.keys()), errors) if valid_data else (None, [], errors)

# ============================================================
# PART 8: App Setup
# ============================================================
st.set_page_config(page_title="Investment & Wealth Engine", page_icon="📈", layout="wide")
init_database()

if "logged_in" not in st.session_state:
    st.session_state.update({"logged_in": False, "user": None, "is_admin": False})

if st.session_state.logged_in and st.session_state.user:
    email_sess = st.session_state.user.get("email", "")
    if email_sess and email_sess != ADMIN_EMAIL:
        fresh = get_user_from_db(email_sess)
        if fresh: st.session_state.user = fresh

# ============================================================
# PART 9: Auth Page
# ============================================================
def show_auth_page():
    st.markdown("# 📈 Investment & Wealth Engine")
    st.markdown("##### AI-Powered Multi-Asset Portfolio System | Built by Mennahtullah Saeed")
    st.divider()
    col_info, col_form = st.columns([1, 1])
    with col_info:
        st.markdown("### 💎 Plans")
        st.markdown("**🆓 Free — 3 analyses/day**\n- ✅ Stocks, Crypto, Commodities\n- ✅ Risk Analysis & Benchmark\n\n**⭐ Pro — $9.99/month**\n- ✅ Unlimited analyses\n- ✅ Monte Carlo Simulation\n- ✅ Investment Allocation")
    with col_form:
        tab_login, tab_register, tab_forgot = st.tabs(["🔑 Login", "📝 Register", "🔓 Forgot Password"])
        with tab_login:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_pass")
            if st.button("Login", type="primary"):
                res, user = login_user(email, password)
                if res:
                    st.session_state.update({"logged_in": True, "user": user, "is_admin": (res=="admin")})
                    st.rerun()
                else: st.error("❌ Invalid credentials")
        with tab_register:
            reg_name = st.text_input("Name")
            reg_email = st.text_input("Email", key="reg_email")
            reg_pass = st.text_input("Pass", type="password", key="reg_pass")
            if st.button("Create Account"):
                ok, msg = register_user(reg_email, reg_pass, reg_name)
                st.success(msg) if ok else st.error(msg)
        with tab_forgot:
            fp_email = st.text_input("Your Email", key="fp_email")
            if st.button("Send Reset Code"):
                code = generate_reset_code(fp_email)
                st.success(f"✅ Reset code: **{code}**")
            fp_code = st.text_input("Enter 6-Digit Code")
            fp_new = st.text_input("New Password", type="password")
            if st.button("Reset Password"):
                if verify_reset_code(fp_email, fp_code) and reset_password(fp_email, fp_new):
                    st.success("✅ Password reset! Please login.")

# ============================================================
# PART 10: Admin Dashboard
# ============================================================
def show_admin_dashboard():
    st.markdown("# 🔐 Admin Dashboard")
    if st.button("Logout"):
        st.session_state.update({"logged_in": False, "user": None, "is_admin": False})
        st.rerun()
    with get_conn() as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        st.metric("👥 Total Users", total_users)
        users_df = pd.read_sql("SELECT email, full_name, plan, analyses_count FROM users", conn)
        st.dataframe(users_df, use_container_width=True)
        email_to_mod = st.text_input("User Email to Manage")
        if st.button("Upgrade to Pro"): upgrade_to_pro(email_to_mod); st.rerun()
        if st.button("Downgrade to Free"): downgrade_to_free(email_to_mod); st.rerun()

# ============================================================
# PART 11 & 12: User Dashboard & Main Logic
# ============================================================
def show_dashboard():
    user = st.session_state.user
    is_pro = user["plan"] == "pro"
    user_email = user["email"]

    col_title, col_user = st.columns([3, 1])
    with col_title: st.markdown("# 📈 Investment & Wealth Engine")
    with col_user:
        st.write(f"**👤 {user['full_name']}** ({user['plan'].upper()})")
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

    st.divider()
    stocks = st.text_input("Asset Symbols (e.g. AAPL, BTC-USD)", "AAPL, MSFT, BTC-USD")
    period = st.selectbox("Period", ["1mo", "6mo", "1y", "2y"])
    amount = st.number_input("Investment Amount", value=10000)

    if st.button("📊 Analyze", type="primary"):
        if not is_pro and user["analyses_count"] >= 3:
            st.error("❌ Daily limit reached! Upgrade to Pro.")
            return

        tickers = [s.strip().upper() for s in stocks.split(",") if s.strip()]
        with st.spinner("Fetching data..."):
            data, valid, errs = fetch_data_safe(tickers, period)
            if data is not None:
                returns = data.pct_change().dropna()
                norm = (data / data.iloc[0]) * 100
                st.line_chart(norm)

                # --- Benchmark Logic (سطر 1015) ---
                st.subheader("🏆 Benchmark vs S&P 500")
                try:
                    sp_data = yf.download("^GSPC", period=period, progress=False, auto_adjust=True)['Close']
                    if not sp_data.empty:
                        norm_p = norm.mean(axis=1)
                        norm_sp = (sp_data / sp_data.iloc[0]) * 100
                        # التصليح النهائي هنا:
                        if not norm_p.dropna().empty:
                            bench_df = pd.DataFrame({'Portfolio': norm_p, 'S&P 500': norm_sp})
                            st.line_chart(bench_df)
                        else:
                            st.warning("Not enough data for benchmark.")
                except Exception as e:
                    st.warning(f"Benchmark error: {e}")

                # Risk Analysis Table
                risk_data = []
                for t in valid:
                    r = returns[t]
                    risk_data.append({
                        "Asset": t, "Return": f"{((data[t].iloc[-1]/data[t].iloc[0])-1)*100:.1f}%",
                        "Volatility": f"{r.std()*np.sqrt(252)*100:.1f}%",
                        "Sharpe Ratio": f"{(r.mean()*252)/(r.std()*np.sqrt(252)):.2f}"
                    })
                st.dataframe(pd.DataFrame(risk_data), use_container_width=True)
                save_metrics(risk_data, period, user_email)
                increment_analysis(user_email)
            else: st.error("❌ No data found.")

# Entry Point
if st.session_state.logged_in:
    if st.session_state.is_admin: show_admin_dashboard()
    else: show_dashboard()
else: show_auth_page()
