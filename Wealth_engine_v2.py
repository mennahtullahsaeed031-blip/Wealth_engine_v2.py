# ============================================================
# 📈 Investment & Wealth Engine
# Built by Mennahtullah Saeed
# Version 3.1 — Security & Stability Fix
# ============================================================
#
# الأدوات المستخدمة:
# Python     → لغة البرمجة
# Streamlit  → الـ App والواجهة
# yfinance   → API الأسهم والـ Crypto
# pandas     → الجداول والبيانات
# numpy      → الحسابات الرياضية
# plotly     → الـ Charts
# SQLite     → قاعدة البيانات (مع context manager)
# hashlib    → تشفير الباسورد
# TextBlob   → تحليل الأخبار
#
# الإصلاحات في النسخة دي:
# FIX 1 → Security: التحقق من الـ email في كل DB operation
# FIX 2 → Session: إعادة تحميل بيانات المستخدم من DB لو Session اتمسحت
# FIX 3 → yfinance Error Handling: رسايل واضحة للمستخدم
# FIX 4 → Database: context manager بدل conn ثابت
# FIX 5 → Daily Reset: العداد بيرجع 0 كل يوم تلقائياً
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
from io import BytesIO
from datetime import datetime, date
warnings.filterwarnings('ignore')

try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except:
    TEXTBLOB_AVAILABLE = False

DB_PATH = "wealth_engine.db"
# DB_PATH = متغير ثابت فيه اسم الداتابيز
# بدل ما نكتب "wealth_engine.db" في كل مكان
# لو غيرنا الاسم → نغيره هنا بس ✅


# ============================================================
# PART 2: Database Helpers — context manager
# ============================================================
# FIX 4: بدل conn ثابت في أول الكود
# دلوقتي كل دالة بتفتح وتقفل الاتصال بنفسها
# زي ما بتفتح ملف وبعدين بتقفله
# ده بيمنع "Database is locked" لو كذا مستخدم في نفس الوقت

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    # check_same_thread=False = بيسمح لـ Streamlit
    # يستخدم نفس الاتصال من threads مختلفة
    conn.row_factory = sqlite3.Row
    # row_factory = بيخلي النتايج تتقرأ زي Dictionary
    # بدل tuple عشان أسهل في الاستخدام
    return conn


def init_database():
    # FIX 4: بنستخدم with عشان يقفل تلقائياً
    with get_conn() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_prices (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker      TEXT NOT NULL,
                price_date  TEXT NOT NULL,
                close_price REAL,
                asset_type  TEXT DEFAULT 'stock',
                saved_at    TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, price_date)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_metrics (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email   TEXT NOT NULL,
                ticker       TEXT NOT NULL,
                period       TEXT NOT NULL,
                asset_type   TEXT DEFAULT 'stock',
                total_return REAL,
                volatility   REAL,
                sharpe_ratio REAL,
                beta         REAL,
                alpha        REAL,
                max_drawdown REAL,
                var_95       REAL,
                analyzed_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # user_email = NOT NULL الآن
        # FIX 1: مش ممكن يتحفظ تحليل بدون إيميل

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                email           TEXT UNIQUE NOT NULL,
                password_hash   TEXT NOT NULL,
                full_name       TEXT,
                plan            TEXT DEFAULT 'free',
                analyses_count  INTEGER DEFAULT 0,
                analyses_date   TEXT DEFAULT '',
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                last_login      TEXT
            )
        """)
        # analyses_date = جديد ✨ FIX 5
        # بيحفظ تاريخ آخر تحليل
        # لو التاريخ اتغير (يوم جديد) → نرجع العداد لـ 0

        conn.commit()


# ============================================================
# PART 3: User Functions
# ============================================================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def register_user(email, password, full_name):
    # FIX 4: بنفتح ونقفل الاتصال جوه الدالة
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (email, password_hash, full_name)
                VALUES (?, ?, ?)
            """, (email.strip().lower(), hash_password(password), full_name.strip()))
            conn.commit()
            return True, "✅ Account created!"
        except sqlite3.IntegrityError:
            return False, "❌ Email already exists!"


def login_user(email, password):
    # FIX 4: context manager
    with get_conn() as conn:
        cursor = conn.cursor()
        today  = date.today().isoformat()
        # isoformat() = بيحول التاريخ لنص "2026-04-17"

        cursor.execute("""
            SELECT id, email, full_name, plan,
                   analyses_count, analyses_date
            FROM users
            WHERE email = ? AND password_hash = ?
        """, (email.strip().lower(), hash_password(password)))

        row = cursor.fetchone()
        if not row:
            return False, None

        # FIX 5: Daily Reset
        # لو المستخدم دخل النهارده لأول مرة → نصفر العداد
        analyses_count = row["analyses_count"]
        analyses_date  = row["analyses_date"]

        if analyses_date != today:
            # يوم جديد → نصفر العداد
            analyses_count = 0
            cursor.execute("""
                UPDATE users
                SET analyses_count = 0,
                    analyses_date  = ?,
                    last_login     = ?
                WHERE email = ?
            """, (today, datetime.now().strftime("%Y-%m-%d %H:%M"), email.strip().lower()))
        else:
            cursor.execute("""
                UPDATE users SET last_login = ? WHERE email = ?
            """, (datetime.now().strftime("%Y-%m-%d %H:%M"), email.strip().lower()))

        conn.commit()

        return True, {
            "id"            : row["id"],
            "email"         : row["email"],
            "full_name"     : row["full_name"],
            "plan"          : row["plan"],
            "analyses_count": analyses_count,
            "analyses_date" : today
        }


def get_user_from_db(email):
    # FIX 2: بنجيب بيانات المستخدم من الـ DB في أي وقت
    # بنستخدمها لو الـ Session اتمسحت
    with get_conn() as conn:
        cursor = conn.cursor()
        today  = date.today().isoformat()

        cursor.execute("""
            SELECT id, email, full_name, plan,
                   analyses_count, analyses_date
            FROM users WHERE email = ?
        """, (email,))

        row = cursor.fetchone()
        if not row:
            return None

        # FIX 5: Daily Reset هنا برضو
        analyses_count = row["analyses_count"]
        if row["analyses_date"] != today:
            analyses_count = 0
            cursor.execute("""
                UPDATE users
                SET analyses_count = 0, analyses_date = ?
                WHERE email = ?
            """, (today, email))
            conn.commit()

        return {
            "id"            : row["id"],
            "email"         : row["email"],
            "full_name"     : row["full_name"],
            "plan"          : row["plan"],
            "analyses_count": analyses_count,
            "analyses_date" : today
        }


def increment_analysis(email):
    # FIX 1 + FIX 4 + FIX 5
    if not email:
        return
    # FIX 1: لو مفيش إيميل → متعملش حاجة

    today = date.today().isoformat()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users
            SET analyses_count = analyses_count + 1,
                analyses_date  = ?
            WHERE email = ?
        """, (today, email))
        # بنحدث التاريخ مع كل تحليل
        # عشان FIX 5 يشتغل صح
        conn.commit()


def upgrade_to_pro(email):
    # FIX 4: context manager
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET plan = 'pro' WHERE email = ?
        """, (email,))
        conn.commit()


def save_prices(data, tickers, asset_types):
    # FIX 4: context manager
    saved = 0
    with get_conn() as conn:
        cursor = conn.cursor()
        for ticker in tickers:
            try:
                asset_type = asset_types.get(ticker, 'stock')
                col = data[ticker] if ticker in data.columns else data
                for date_idx, price in col.items():
                    try:
                        cursor.execute("""
                            INSERT OR IGNORE INTO stock_prices
                            (ticker, price_date, close_price, asset_type)
                            VALUES (?, ?, ?, ?)
                        """, (ticker, str(date_idx.date()), round(float(price), 4), asset_type))
                        saved += 1
                    except:
                        pass
            except:
                pass
        conn.commit()
    return saved


def save_metrics(risk_data, period, user_email):
    # FIX 1: user_email إجباري مش اختياري
    if not user_email:
        return
    # لو مفيش إيميل → متحفظش
    # ده بيمنع تداخل البيانات بين المستخدمين

    with get_conn() as conn:
        cursor = conn.cursor()
        for row in risk_data:
            try:
                cursor.execute("""
                    INSERT INTO stock_metrics
                    (user_email, ticker, period, asset_type,
                     total_return, volatility, sharpe_ratio,
                     beta, alpha, max_drawdown, var_95)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_email,
                    row["Asset"],
                    period,
                    row.get("Type", "stock").lower(),
                    float(str(row["Return"]).replace("%", "")),
                    float(str(row["Volatility"]).replace("%", "")),
                    float(row["Sharpe Ratio"]),
                    float(row["Beta"]),
                    float(row["Alpha"]),
                    float(str(row["Max Drawdown"]).replace("%", "")),
                    float(str(row["VaR (95%)"]).replace("%", ""))
                ))
            except:
                pass
        conn.commit()


# ============================================================
# PART 4: yfinance Helper — FIX 3
# ============================================================
def fetch_data_safe(tickers, period):
    # FIX 3: Error Handling واضح للمستخدم
    # بدل ما الكود يقع بدون رسالة مفهومة
    """
    بتجيب بيانات الأسهم من yfinance بشكل آمن
    بترجع: (data, valid_tickers, error_tickers)
    data          = DataFrame فيه الأسعار
    valid_tickers = الأسهم اللي نجحت
    error_tickers = الأسهم اللي فشلت
    """
    valid_data    = {}
    error_tickers = []

    for ticker in tickers:
        try:
            if len(tickers) == 1:
                raw = yf.download(ticker, period=period, progress=False)['Close']
            else:
                raw = yf.download(ticker, period=period, progress=False)['Close']

            # تحقق إن البيانات مش فاضية
            if isinstance(raw, pd.DataFrame):
                raw = raw.iloc[:, 0]
            raw = raw.squeeze().dropna()

            if len(raw) < 2:
                # أقل من يومين = بيانات مش كافية
                error_tickers.append(ticker)
                continue

            valid_data[ticker] = raw

        except Exception:
            error_tickers.append(ticker)

    if not valid_data:
        return None, [], error_tickers

    data = pd.DataFrame(valid_data)
    return data, list(valid_data.keys()), error_tickers


# ============================================================
# PART 5: App Setup
# ============================================================
st.set_page_config(
    page_title="Investment & Wealth Engine",
    page_icon="📈",
    layout="wide"
)

# تهيئة قاعدة البيانات
init_database()

# ─── Session State ────────────────────────────────────────────
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user      = None

# FIX 2: لو في إيميل محفوظ في الـ Session
# بس البيانات اتمسحت (زي لما المستخدم يعمل refresh)
# نرجع نجيبها من الـ DB تاني
if st.session_state.logged_in and st.session_state.user:
    email_in_session = st.session_state.user.get("email", "")
    if email_in_session:
        fresh_user = get_user_from_db(email_in_session)
        if fresh_user:
            # حدّث بيانات الـ Session من الـ DB
            st.session_state.user = fresh_user
        else:
            # المستخدم مش موجود في الـ DB → logout
            st.session_state.logged_in = False
            st.session_state.user      = None


# ============================================================
# PART 6: Auth Page
# ============================================================
def show_auth_page():
    st.markdown("# 📈 Investment & Wealth Engine")
    st.markdown("##### AI-Powered Multi-Asset Portfolio System | Built by Mennahtullah Saeed")
    st.divider()

    col_info, col_form = st.columns([1, 1])

    with col_info:
        st.markdown("### 💎 Plans")
        st.markdown("""
        **🆓 Free — 3 analyses/day**
        - ✅ Stocks, Crypto, Commodities
        - ✅ Risk Analysis
        - ✅ Gold & Dollar Comparison
        - ✅ Benchmark vs S&P 500
        - ❌ Monte Carlo
        - ❌ Investment Allocation
        - ❌ Full History Export

        ---

        **⭐ Pro — $9.99/month**
        - ✅ Unlimited analyses
        - ✅ Monte Carlo Simulation
        - ✅ Investment Allocation
        - ✅ Full History + Export CSV
        - ✅ All asset types
        - ✅ Priority Support
        """)

    with col_form:
        tab_login, tab_register = st.tabs(["🔑 Login", "📝 Register"])

        with tab_login:
            st.markdown("### Welcome Back!")
            email    = st.text_input("Email", key="login_email",
                                     placeholder="your@email.com")
            password = st.text_input("Password", type="password",
                                     key="login_pass")

            if st.button("Login", type="primary", use_container_width=True):
                if not email or not password:
                    st.warning("⚠️ Please fill all fields")
                else:
                    success, user = login_user(email, password)
                    if success:
                        st.session_state.logged_in = True
                        st.session_state.user      = user
                        st.rerun()
                    else:
                        st.error("❌ Invalid email or password")

        with tab_register:
            st.markdown("### Create Free Account")
            reg_name  = st.text_input("Full Name",         key="reg_name")
            reg_email = st.text_input("Email",             key="reg_email",
                                      placeholder="your@email.com")
            reg_pass  = st.text_input("Password",          type="password", key="reg_pass")
            reg_pass2 = st.text_input("Confirm Password",  type="password", key="reg_pass2")

            if st.button("Create Account", type="primary", use_container_width=True):
                if not all([reg_name, reg_email, reg_pass, reg_pass2]):
                    st.warning("⚠️ Please fill all fields")
                elif reg_pass != reg_pass2:
                    st.error("❌ Passwords don't match!")
                elif len(reg_pass) < 6:
                    st.error("❌ Password must be 6+ characters")
                elif "@" not in reg_email:
                    st.error("❌ Invalid email format")
                else:
                    success, msg = register_user(reg_email, reg_pass, reg_name)
                    if success:
                        st.success(msg)
                        st.info("✅ Now login with your credentials!")
                    else:
                        st.error(msg)


# ============================================================
# PART 7: Main Dashboard
# ============================================================
def show_dashboard():
    user   = st.session_state.user
    is_pro = user["plan"] == "pro"

    # FIX 1: التحقق إن الـ email موجود وصح
    user_email = user.get("email", "").strip().lower()
    if not user_email:
        st.error("❌ Session error. Please login again.")
        st.session_state.logged_in = False
        st.rerun()
        return

    # ─── Header ──────────────────────────────────────────────
    col_title, col_user = st.columns([3, 1])
    with col_title:
        st.markdown("# 📈 Investment & Wealth Engine")
        st.markdown("##### AI-Powered Multi-Asset Portfolio System | Built by Mennahtullah Saeed")
    with col_user:
        plan_badge = "⭐ Pro" if is_pro else "🆓 Free"
        st.markdown(f"**👤 {user['full_name']}**")
        st.markdown(f"**{plan_badge}**")
        if not is_pro:
            remaining = max(0, 3 - user["analyses_count"])
            st.caption(f"Today: {user['analyses_count']}/3 analyses ({remaining} left)")
            st.caption("🔄 Resets daily at midnight")
            # FIX 5: بنوضح للمستخدم إن العداد بيتصفر يومياً
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user      = None
            st.rerun()

    st.divider()

    if not is_pro:
        st.warning("🆓 **Free Plan** — Upgrade for unlimited analyses & Pro features!")
        if st.button("⭐ Upgrade to Pro — $9.99/month", type="primary"):
            upgrade_to_pro(user_email)
            st.session_state.user["plan"] = "pro"
            st.success("🎉 Welcome to Pro!")
            st.rerun()

    st.divider()


    # ============================================================
    # PART 8: Input
    # ============================================================
    st.markdown("### 🔍 Enter Your Portfolio")
    st.info("""
    💡 **Supported Assets:**
    🏢 **Stocks:** AAPL, MSFT, GOOGL, TSLA, NVDA
    🪙 **Crypto:** BTC-USD, ETH-USD, BNB-USD, SOL-USD
    🥇 **Commodities:** GC=F (Gold), SI=F (Silver), CL=F (Oil)
    📊 **Bonds ETF:** TLT, IEF, BND
    🇪🇬 **Egypt:** COMI.CA, HRHO.CA
    """)

    template_df = pd.DataFrame({
        'ticker': ['AAPL', 'MSFT', 'BTC-USD', 'ETH-USD',
                   'GC=F', 'GOOGL', 'TSLA', 'NVDA', 'TLT', 'SPY']
    })
    buf = BytesIO()
    template_df.to_excel(buf, index=False)
    buf.seek(0)
    st.download_button("📥 Download Template", data=buf,
                       file_name="wealth_template.xlsx",
                       mime="application/vnd.ms-excel")

    uploaded_file = st.file_uploader("📎 Upload Excel/CSV",
                                     type=["xlsx", "xls", "csv"])
    default_stocks = "AAPL, MSFT, BTC-USD"

    if uploaded_file is not None:
        try:
            df_up = (pd.read_csv(uploaded_file)
                     if uploaded_file.name.endswith('.csv')
                     else pd.read_excel(uploaded_file))
            raw   = df_up.iloc[:, 0].dropna().tolist()
            clean = [str(t).strip().upper() for t in raw
                     if str(t).strip().upper()
                     not in ['TICKER','SYMBOL','STOCK','']]
            if clean:
                default_stocks = ", ".join(clean)
                st.success(f"✅ Loaded {len(clean)} assets!")
        except Exception as e:
            st.error(f"❌ File error: {e}")

    col1, col2 = st.columns(2)
    with col1:
        stocks = st.text_input("Asset Symbols", value=default_stocks)
    with col2:
        period = st.selectbox("Period", ["1mo","3mo","6mo","1y","2y"])

    st.markdown("### 💰 Investment Amount (Optional)")
    ca, cb = st.columns(2)
    with ca:
        amount = st.number_input("Amount", min_value=0,
                                 value=10000, step=1000)
    with cb:
        currency = st.selectbox("Currency",
                                ["USD $","EGP جنيه","EUR €"])

    c3, c4 = st.columns(2)
    with c3:
        analyze_btn  = st.button("📊 Analyze", type="primary",
                                 use_container_width=True)
    with c4:
        optimize_btn = st.button("⚡ Optimize (Pro)",
                                 use_container_width=True,
                                 disabled=not is_pro)
    
    # PART 9: Analysis Logic
    # ============================================================
    if analyze_btn or optimize_btn:

        # FIX 5: تحقق من الـ Daily Limit
        # نجيب العدد الحالي من الـ DB مش من الـ Session بس
        fresh = get_user_from_db(user_email)
        if fresh:
            st.session_state.user["analyses_count"] = fresh["analyses_count"]
            user = st.session_state.user

        if not is_pro and user["analyses_count"] >= 3:
            st.error("❌ Daily limit reached (3/3)! Upgrade to Pro or try tomorrow.")
            st.info("🔄 Your limit resets every day at midnight automatically.")
            return

        if not stocks.strip():
            st.error("❌ Please enter at least one symbol!")
            return

        tickers = [s.strip().upper() for s in stocks.split(",") if s.strip()]
        if not tickers:
            st.error("❌ No valid symbols!")
            return

        if optimize_btn:
            period = "1y"

        # تصنيف الأصول
        asset_types = {}
        for t in tickers:
            if any(x in t for x in ['-USD','-EUR','-BTC']):
                asset_types[t] = 'crypto'
            elif t in ['GC=F','SI=F','CL=F','NG=F','HG=F']:
                asset_types[t] = 'commodity'
            elif t in ['TLT','IEF','SHY','BND','AGG']:
                asset_types[t] = 'bond'
            elif t.endswith('.CA'):
                asset_types[t] = 'egypt'
            else:
                asset_types[t] = 'stock'

        with st.spinner("⏳ Fetching data..."):

            # FIX 3: استخدام الدالة الآمنة
            data, valid_tickers, error_tickers = fetch_data_safe(tickers, period)

            # FIX 3: عرض رسايل واضحة للمستخدم
            if error_tickers:
                st.warning(
                    f"⚠️ Could not fetch data for: **{', '.join(error_tickers)}**\n\n"
                    f"Possible reasons:\n"
                    f"- Symbol is wrong (e.g. GOOGL not GOOGLE)\n"
                    f"- Egyptian stocks need '.CA' suffix (e.g. COMI.CA)\n"
                    f"- Crypto needs '-USD' suffix (e.g. BTC-USD)\n"
                    f"- API temporarily unavailable — try again in 1 min"
                )

            if data is None or len(valid_tickers) == 0:
                st.error("❌ No valid data. Check all symbols and try again.")
                return

            tickers     = valid_tickers
            asset_types = {t: asset_types.get(t, 'stock') for t in tickers}

            # S&P 500
            sp500_data = market_returns = None
            try:
                sp_raw = yf.download("^GSPC", period=period, progress=False)['Close']
                if isinstance(sp_raw, pd.DataFrame): sp_raw = sp_raw.iloc[:, 0]
                sp500_data    = sp_raw.squeeze().dropna()
                market_returns = sp500_data.pct_change().dropna()
            except: pass

            # Gold & Dollar
            gold_data = usd_data = None
            try:
                g = yf.download("GC=F", period=period, progress=False)['Close']
                if isinstance(g, pd.DataFrame): g = g.iloc[:, 0]
                if len(g) > 1: gold_data = g.squeeze()
            except: pass

            try:
                u = yf.download("DX-Y.NYB", period=period, progress=False)['Close']
                if isinstance(u, pd.DataFrame): u = u.iloc[:, 0]
                if len(u) > 1: usd_data = u.squeeze()
            except: pass

            returns    = data.pct_change().dropna()
            rows_saved = save_prices(data, tickers, asset_types)

            # FIX 1 + FIX 5: نزود العداد بـ email متحقق منه
            increment_analysis(user_email)
            st.session_state.user["analyses_count"] += 1

        st.divider()


        # ============================================================
        # PART 10: Asset Summary
        # ============================================================
        stocks_l    = [t for t in tickers if asset_types.get(t) == 'stock']
        crypto_l    = [t for t in tickers if asset_types.get(t) == 'crypto']
        commodity_l = [t for t in tickers if asset_types.get(t) == 'commodity']
        bond_l      = [t for t in tickers if asset_types.get(t) == 'bond']
        egypt_l     = [t for t in tickers if asset_types.get(t) == 'egypt']

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("🏢 Stocks",      len(stocks_l))
        c2.metric("🪙 Crypto",      len(crypto_l))
        c3.metric("🥇 Commodities", len(commodity_l))
        c4.metric("📊 Bonds",       len(bond_l))
        c5.metric("🇪🇬 Egypt",      len(egypt_l))


        # ============================================================
        # PART 11: Portfolio Overview
        # ============================================================
        st.markdown("### 📊 Portfolio Overview")
        type_emoji = {'stock':'🏢','crypto':'🪙','commodity':'🥇',
                      'bond':'📊','egypt':'🇪🇬'}
        overview   = []
        for ticker in tickers:
            try:
                ret    = ((data[ticker].iloc[-1]/data[ticker].iloc[0])-1)*100
                sharpe = (returns[ticker].mean()*252)/(returns[ticker].std()*np.sqrt(252))
                price  = float(data[ticker].iloc[-1])
                atype  = asset_types.get(ticker,'stock')
                signal = "✅ Strong" if sharpe>1 else ("⚠️ Hold" if sharpe>0 else "🔴 Weak")
                overview.append({
                    "Type"         : type_emoji.get(atype,'📈'),
                    "Asset"        : ticker,
                    "Current Price": f"${price:.2f}",
                    "Return"       : f"{ret:.1f}%",
                    "Sharpe"       : f"{sharpe:.2f}",
                    "Signal"       : signal
                })
            except: pass

        if overview:
            st.dataframe(pd.DataFrame(overview),
                         use_container_width=True, hide_index=True)


        # ============================================================
        # PART 12: Normalized Price Chart
        # ============================================================
        st.markdown("### 📈 Performance (Normalized to 100)")
        try:
            norm = data.div(data.iloc[0]) * 100
            fig  = px.line(norm, title="Normalized Performance — All start at 100")
            fig.update_layout(paper_bgcolor='#0f1117', plot_bgcolor='#1e2130',
                              font={'color':'white'}, hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)
            st.caption("💡 Shows relative growth — ignores different price scales")
        except Exception as e:
            st.warning(f"Chart error: {e}")


        # ============================================================
        # PART 13: Benchmark vs S&P 500
        # ============================================================
        st.markdown("### 🏆 Benchmark vs S&P 500")
        if sp500_data is not None and len(sp500_data) > 1:
            try:
                port_ret = float(np.mean([
                    ((data[t].iloc[-1]/data[t].iloc[0])-1)*100
                    for t in tickers
                ]))
                sp_ret = float(
                    ((sp500_data.iloc[-1]/sp500_data.iloc[0])-1)*100
                )
                diff = port_ret - sp_ret

                b1,b2,b3 = st.columns(3)
                b1.metric("📊 Your Portfolio", f"{port_ret:.1f}%")
                b2.metric("📈 S&P 500",        f"{sp_ret:.1f}%")
                b3.metric("🎯 vs Benchmark",   f"{diff:.1f}%",
                          delta=f"{diff:.1f}%")

                if diff > 0:
                    st.success(f"✅ You **beat** S&P 500 by **{diff:.1f}%**!")
                elif diff < 0:
                    st.warning(f"⚠️ You **underperformed** S&P 500 by **{abs(diff):.1f}%**")
                else:
                    st.info("📊 Matched S&P 500 exactly.")

                # Benchmark Chart
                norm_p  = data.mean(axis=1)
                norm_p  = (norm_p  / norm_p.iloc[0])  * 100
                norm_sp = (sp500_data / sp500_data.iloc[0]) * 100
                bench_df = pd.DataFrame({
                    'Your Portfolio': norm_p,
                    'S&P 500'       : norm_sp
                }).dropna()
                fig_b = px.line(bench_df, title="Portfolio vs S&P 500",
                                color_discrete_map={
                                    'Your Portfolio':'#00b4d8',
                                    'S&P 500'       :'#f4a261'
                                })
                fig_b.update_layout(paper_bgcolor='#0f1117',
                                    plot_bgcolor='#1e2130',
                                    font={'color':'white'})
                st.plotly_chart(fig_b, use_container_width=True)
            except Exception as e:
                st.warning(f"Benchmark error: {e}")
        else:
            st.info("S&P 500 data unavailable")


        # ============================================================
        # PART 14: Multi-Asset Comparison
        # ============================================================
        st.markdown("### 🥇 Multi-Asset Return Comparison")
        comparison = []
        type_label_map = {'stock':'Stock','crypto':'Crypto',
                          'commodity':'Commodity','bond':'Bond','egypt':'Egypt'}

        for ticker in tickers:
            try:
                ret   = float(((data[ticker].iloc[-1]/data[ticker].iloc[0])-1)*100)
                label = type_label_map.get(asset_types.get(ticker,'stock'),'Stock')
                comparison.append({"Asset":ticker,"Return":ret,"Type":label})
            except: pass

        if gold_data is not None and 'GC=F' not in tickers:
            try:
                g = gold_data.dropna()
                comparison.append({"Asset":"🥇 Gold",
                                   "Return":float(((g.iloc[-1]/g.iloc[0])-1)*100),
                                   "Type":"Commodity"})
            except: pass

        if usd_data is not None:
            try:
                u = usd_data.dropna()
                comparison.append({"Asset":"💵 USD",
                                   "Return":float(((u.iloc[-1]/u.iloc[0])-1)*100),
                                   "Type":"Currency"})
            except: pass

        if sp500_data is not None:
            try:
                comparison.append({"Asset":"📈 S&P 500",
                                   "Return":float(((sp500_data.iloc[-1]/sp500_data.iloc[0])-1)*100),
                                   "Type":"Index"})
            except: pass

        if comparison:
            comp_df  = pd.DataFrame(comparison)
            fig_comp = px.bar(comp_df, x="Asset", y="Return", color="Type",
                              title=f"Return Comparison — {period}", text="Return",
                              color_discrete_map={
                                  'Stock':'#00b4d8','Crypto':'#9b5de5',
                                  'Commodity':'#f4a261','Bond':'#2a9d8f',
                                  'Currency':'#e9c46a','Index':'#e76f51',
                                  'Egypt':'#06d6a0'
                              })
            fig_comp.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig_comp.update_layout(paper_bgcolor='#0f1117', plot_bgcolor='#1e2130',
                                   font={'color':'white'})
            st.plotly_chart(fig_comp, use_container_width=True)

            best_idx = int(np.argmax([c['Return'] for c in comparison]))
            st.info(f"🏆 Best: **{comparison[best_idx]['Asset']}** "
                    f"with **{comparison[best_idx]['Return']:.1f}%**")


        # ============================================================
        # PART 15: Risk Analysis
        # ============================================================
        st.markdown("### ⚠️ Risk Analysis")
        risk_data = []

        for ticker in tickers:
            try:
                r     = returns[ticker].dropna()
                atype = asset_types.get(ticker,'stock')

                beta = alpha = 0.0
                if market_returns is not None:
                    mkt = market_returns.copy()
                    if isinstance(mkt, pd.DataFrame): mkt = mkt.iloc[:,0]
                    mkt          = mkt.squeeze().dropna()
                    common       = r.index.intersection(mkt.index)
                    if len(common) >= 2:
                        r_al  = r.loc[common]
                        m_al  = mkt.loc[common]
                        beta  = float(r_al.cov(m_al) / m_al.var())
                        alpha = float((r_al.mean()*252) - (m_al.mean()*252))

                risk_data.append({
                    "Type"        : atype.title(),
                    "Asset"       : ticker,
                    "Return"      : f"{((data[ticker].iloc[-1]/data[ticker].iloc[0])-1)*100:.1f}%",
                    "Volatility"  : f"{r.std()*np.sqrt(252)*100:.1f}%",
                    "Sharpe Ratio": f"{(r.mean()*252)/(r.std()*np.sqrt(252)):.2f}",
                    "Beta"        : f"{beta:.2f}",
                    "Alpha"       : f"{alpha:.2f}",
                    "Max Drawdown": f"{((data[ticker]/data[ticker].cummax())-1).min()*100:.1f}%",
                    "VaR (95%)"   : f"{r.quantile(0.05)*100:.2f}%",
                    "Kurtosis"    : f"{r.kurtosis():.2f}",
                })
            except Exception as e:
                st.warning(f"Risk error — {ticker}: {e}")

        if risk_data:
            st.dataframe(pd.DataFrame(risk_data),
                         use_container_width=True, hide_index=True)
            # FIX 1: user_email إجباري هنا
            save_metrics(risk_data, period, user_email)
            st.success(f"✅ Saved {rows_saved} records")


        # ============================================================
        # PART 16: Correlation
        # ============================================================
        if len(tickers) > 1:
            st.markdown("### 🔗 Correlation Heatmap")
            try:
                corr = returns.corr()
                fig_corr = px.imshow(corr, text_auto=True,
                                     color_continuous_scale='RdBu_r',
                                     title="Asset Correlation Matrix")
                fig_corr.update_layout(paper_bgcolor='#0f1117',
                                       font={'color':'white'})
                st.plotly_chart(fig_corr, use_container_width=True)
            except Exception as e:
                st.warning(f"Correlation error: {e}")


        # ============================================================
        # PART 17: Monte Carlo — Pro Only
        # ============================================================
        best = None
        if is_pro:
            st.markdown("### 🎲 Monte Carlo Simulation")
            try:
                mean_r = returns.mean()
                cov_m  = returns.cov()
                n      = len(tickers)
                mcs    = []

                for _ in range(1000):
                    w   = np.random.random(n); w = w/w.sum()
                    ret = float(np.sum(mean_r.values*w)*252)
                    rsk = float(np.sqrt(np.dot(w.T, np.dot(cov_m.values*252, w))))
                    s   = ret/rsk if rsk > 0 else 0
                    mcs.append({'Return':ret,'Risk':rsk,'Sharpe':s,'Weights':w})

                rdf      = pd.DataFrame(mcs)
                best_idx = int(rdf['Sharpe'].values.argmax())
                best     = rdf.iloc[best_idx]

                fig_mc = px.scatter(rdf, x='Risk', y='Return', color='Sharpe',
                                    title='Monte Carlo: 1,000 Simulations',
                                    color_continuous_scale='Viridis')
                fig_mc.update_layout(paper_bgcolor='#0f1117',
                                     plot_bgcolor='#1e2130',
                                     font={'color':'white'})
                st.plotly_chart(fig_mc, use_container_width=True)

                opt = [{"Asset":t, "Weight":f"{best['Weights'][i]*100:.1f}%"}
                       for i,t in enumerate(tickers)]
                st.dataframe(pd.DataFrame(opt),
                             use_container_width=True, hide_index=True)
                st.success(f"🏆 Return {best['Return']*100:.1f}% | "
                           f"Risk {best['Risk']*100:.1f}% | "
                           f"Sharpe {best['Sharpe']:.2f}")
            except Exception as e:
                st.warning(f"Monte Carlo error: {e}")
        else:
            st.markdown("### 🎲 Monte Carlo Simulation")
            st.warning("⭐ **Pro Feature** — Upgrade to unlock")


        # ============================================================
        # PART 18: Investment Allocation — Pro Only
        # ============================================================
        if is_pro and amount > 0 and best is not None:
            st.markdown(f"### 💰 Allocation — {currency} {amount:,}")
            try:
                alloc = []
                leftover_total = 0
                for i, ticker in enumerate(tickers):
                    w        = float(best['Weights'][i])
                    money    = amount * w
                    price    = float(data[ticker].iloc[-1])
                    units    = int(money / price)
                    spent    = units * price
                    leftover = money - spent
                    leftover_total += leftover
                    alloc.append({
                        "Asset"       : ticker,
                        "Type"        : asset_types.get(ticker,'stock').title(),
                        "Weight"      : f"{w*100:.1f}%",
                        "Amount"      : f"{money:,.0f}",
                        "Units"       : units,
                        "Price/Unit"  : f"${price:.2f}",
                        "Leftover"    : f"{leftover:,.0f}"
                    })
                st.dataframe(pd.DataFrame(alloc),
                             use_container_width=True, hide_index=True)
                a1,a2,a3 = st.columns(3)
                a1.metric("💰 Total",    f"{amount:,}")
                a2.metric("✅ Invested", f"{amount-leftover_total:,.0f}")
                a3.metric("🔄 Leftover", f"{leftover_total:,.0f}")
            except Exception as e:
                st.warning(f"Allocation error: {e}")

        elif not is_pro and amount > 0:
            st.markdown("### 💰 Investment Allocation")
            st.warning("⭐ **Pro Feature** — Upgrade to unlock")


        # ============================================================
        # PART 19: Rebalancing Alerts
        # ============================================================
        st.markdown("### 🔔 Rebalancing Alerts")
        try:
            vals      = {t: float(data[t].iloc[-1]) for t in tickers}
            total_val = sum(vals.values())
            found     = False
            for t, v in vals.items():
                w = (v/total_val)*100
                if w > 40:
                    st.error(f"🚨 **{t}** = {w:.1f}% — exceeds 40% limit!")
                    found = True
                elif w > 30:
                    st.warning(f"⚠️ **{t}** = {w:.1f}% — getting concentrated")
                    found = True
            if not found:
                st.success("✅ Portfolio is well-balanced!")
        except Exception as e:
            st.warning(f"Rebalancing error: {e}")


        # ============================================================
        # PART 20: Sentiment Analysis
        # ============================================================
        st.markdown("### 📰 News Sentiment")
        if not TEXTBLOB_AVAILABLE:
            st.info("Install: pip install textblob")
        else:
            sent_cols = st.columns(min(len(tickers), 3))
            for idx, ticker in enumerate(tickers):
                try:
                    news   = yf.Ticker(ticker).news[:3]
                    scores = [TextBlob(a.get('title','')).sentiment.polarity
                              for a in news if a.get('title','')]
                    if scores:
                        avg  = float(np.mean(scores))
                        mood = ("😊 Positive" if avg>0.1
                                else "😟 Negative" if avg<-0.1
                                else "😐 Neutral")
                        sent_cols[idx%3].metric(ticker, mood, f"{avg:.2f}")
                except: pass


        # ============================================================
        # PART 21: AI Recommendation
        # ============================================================
        st.markdown("### 💡 AI Recommendation")
        if risk_data:
            try:
                avg_s = np.mean([float(r["Sharpe Ratio"]) for r in risk_data])
                avg_b = np.mean([float(r["Beta"])         for r in risk_data])
                if avg_s > 1 and avg_b < 1.2:
                    st.success(f"✅ **Strong** | Sharpe: {avg_s:.2f} | Beta: {avg_b:.2f}")
                elif avg_s > 0 and avg_b < 1.5:
                    st.warning(f"🟡 **Moderate** | Sharpe: {avg_s:.2f} | Beta: {avg_b:.2f}")
                else:
                    st.error(f"🔴 **High Risk** | Sharpe: {avg_s:.2f} | Beta: {avg_b:.2f}")
            except: pass


    # ============================================================
    # PART 22: History — منظم حسب المستخدم
    # ============================================================
    st.divider()
    st.markdown("### 📜 My Analysis History")

    # FIX 1: بنجيب بس سجلات المستخدم الحالي
    # مش كل السجلات في الداتابيز
    try:
        with get_conn() as conn:
            if is_pro:
                history_df = pd.read_sql("""
                    SELECT asset_type AS Type, ticker AS Asset,
                           period AS Period, total_return AS "Return%",
                           sharpe_ratio AS Sharpe, beta AS Beta,
                           analyzed_at AS Date
                    FROM stock_metrics
                    WHERE user_email = ?
                    ORDER BY analyzed_at DESC
                    LIMIT 50
                """, conn, params=(user_email,))
            else:
                history_df = pd.read_sql("""
                    SELECT ticker AS Asset, period AS Period,
                           total_return AS "Return%",
                           sharpe_ratio AS Sharpe,
                           analyzed_at AS Date
                    FROM stock_metrics
                    WHERE user_email = ?
                    ORDER BY analyzed_at DESC
                    LIMIT 10
                """, conn, params=(user_email,))

        if not history_df.empty:
            # Filter للـ Pro
            if is_pro and "Type" in history_df.columns:
                types    = ["All"] + sorted(history_df["Type"].dropna().unique().tolist())
                sel_type = st.selectbox("Filter by Type", types)
                if sel_type != "All":
                    history_df = history_df[history_df["Type"]==sel_type]

            st.dataframe(history_df,
                         use_container_width=True, hide_index=True)

            if is_pro:
                st.download_button(
                    "📥 Export CSV",
                    data=history_df.to_csv(index=False),
                    file_name="my_history.csv",
                    mime="text/csv"
                )
        else:
            st.info("📭 No history yet!")

    except Exception as e:
        st.info("📭 No history yet!")


# ============================================================
# PART 23: Main Entry Point
# ============================================================
if st.session_state.logged_in:
    show_dashboard()
else:
    show_auth_page()
    # --- الكود الجديد بعد التعديل ---

def show_dashboard():
    user   = st.session_state.user
    is_pro = user["plan"] == "pro"

    # 1. هنا المكان الصح للسطر بتاعك (جوه الدالة)
    if user['email'] == "menna@example.com": # حطي إيميلك الحقيقي هنا
        st.sidebar.success("Welcome, Boss! 🔱 (Admin)")
        # ممكن كمان تضيفي زرار يصفر العداد ليكي إنتي بس
        if st.sidebar.button("Reset My Limit"):
            st.session_state.user['analyses_count'] = 0
            st.rerun()

    # 2. ده الكود اللي كان موجود أصلاً (القديم في النسخة دي)
    col_title, col_user = st.columns([3, 1])