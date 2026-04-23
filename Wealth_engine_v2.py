# ============================================================
# 📈 Investment & Wealth Engine
# Built by Mennahtullah Saeed
# Version 3.3 — Final Fixes
# ============================================================
#
# الأدوات المستخدمة:
# Python    → لغة البرمجة
# Streamlit → الـ App والواجهة
# yfinance  → API الأسهم والـ Crypto
# pandas    → الجداول والبيانات
# numpy     → الحسابات الرياضية
# plotly    → الـ Charts
# SQLite    → قاعدة البيانات
# bcrypt    → تشفير الباسورد
# hashlib   → backup للتشفير
# time      → Rate Limiter
# random    → Reset Code العشوائي
# TextBlob  → تحليل الأخبار
#
# الإصلاحات في النسخة دي:
# FIX 1 → nan% في Benchmark: Normalized Portfolio بدل mean مباشر
# FIX 2 → Upgrade بيشتغل بدون إذن: بقى Request بس مش Upgrade تلقائي
# FIX 3 → Admin Dashboard: بيشوف الـ Requests ويوافق يدوياً
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

# ─── Admin Credentials ────────────────────────────────────────
# غيري الإيميل والباسورد دول لبياناتك الخاصة
ADMIN_EMAIL    = "admin@wealthengine.com"
ADMIN_PASSWORD = "admin2024!"
CONTACT_EMAIL  = "mennahtullahsaeed031@gmail.com"
# CONTACT_EMAIL = إيميلك الحقيقي على Gmail
# المستخدمين هيشوفوه ويبعتوا عليه الطلبات ✅


# ============================================================
# PART 2: Rate Limiter — SOL 1
# ============================================================
class RateLimiter:
    def __init__(self, min_interval=0.5):
        self.min_interval = min_interval
        self.last_called  = {}

    def wait_if_needed(self, key):
        now     = time.time()
        elapsed = now - self.last_called.get(key, 0)
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_called[key] = time.time()

rate_limiter = RateLimiter(min_interval=0.5)


# ============================================================
# PART 3: Password Hashing — SOL 2
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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reset_codes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                email       TEXT NOT NULL,
                code        TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                used        INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # FIX 2 + FIX 3: جدول طلبات الـ Upgrade
        # بدل ما الـ Upgrade يحصل تلقائياً
        # المستخدم بيبعت Request والـ Admin يوافق يدوياً
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS upgrade_requests (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                email        TEXT NOT NULL,
                full_name    TEXT,
                message      TEXT,
                status       TEXT DEFAULT 'pending',
                requested_at TEXT DEFAULT CURRENT_TIMESTAMP,
                reviewed_at  TEXT
            )
        """)
        # status: 'pending' = لسه ماتراجعتيش
        #         'approved' = وافقتِ
        #         'rejected' = رفضتِ

        conn.commit()


# ============================================================
# PART 5: User Functions
# ============================================================
def register_user(email, password, full_name):
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
    # تحقق من الـ Admin الأول
    if email.strip().lower() == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD:
        return "admin", {
            "id": 0, "email": ADMIN_EMAIL,
            "full_name": "Admin", "plan": "admin",
            "analyses_count": 0, "analyses_date": date.today().isoformat()
        }

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, email, full_name, plan,
                   analyses_count, analyses_date, password_hash
            FROM users WHERE email = ?
        """, (email.strip().lower(),))

        row = cursor.fetchone()
        if not row: return False, None
        if not verify_password(password, row["password_hash"]): return False, None

        today          = date.today().isoformat()
        analyses_count = row["analyses_count"]

        if row["analyses_date"] != today:
            # يوم جديد → صفر العداد
            analyses_count = 0
            cursor.execute("""
                UPDATE users SET analyses_count=0, analyses_date=?, last_login=?
                WHERE email=?
            """, (today, datetime.now().strftime("%Y-%m-%d %H:%M"),
                  email.strip().lower()))
        else:
            cursor.execute("""
                UPDATE users SET last_login=? WHERE email=?
            """, (datetime.now().strftime("%Y-%m-%d %H:%M"), email.strip().lower()))

        conn.commit()
        return True, {
            "id": row["id"], "email": row["email"],
            "full_name": row["full_name"], "plan": row["plan"],
            "analyses_count": analyses_count, "analyses_date": today
        }


def get_user_from_db(email):
    if email == ADMIN_EMAIL: return st.session_state.user
    with get_conn() as conn:
        cursor = conn.cursor()
        today  = date.today().isoformat()
        cursor.execute("""
            SELECT id, email, full_name, plan, analyses_count, analyses_date
            FROM users WHERE email=?
        """, (email,))
        row = cursor.fetchone()
        if not row: return None
        analyses_count = row["analyses_count"]
        if row["analyses_date"] != today:
            analyses_count = 0
            cursor.execute("""
                UPDATE users SET analyses_count=0, analyses_date=? WHERE email=?
            """, (today, email))
            conn.commit()
        return {
            "id": row["id"], "email": row["email"],
            "full_name": row["full_name"], "plan": row["plan"],
            "analyses_count": analyses_count, "analyses_date": today
        }


def increment_analysis(email):
    if not email or email == ADMIN_EMAIL: return
    today = date.today().isoformat()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET analyses_count=analyses_count+1, analyses_date=?
            WHERE email=?
        """, (today, email))
        conn.commit()


def upgrade_to_pro(email):
    # دي بتستخدمها الـ Admin بس من لوحة التحكم
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET plan='pro' WHERE email=?", (email,))
        # بعد الموافقة نحدث حالة الـ Request
        cursor.execute("""
            UPDATE upgrade_requests SET status='approved', reviewed_at=?
            WHERE email=? AND status='pending'
        """, (datetime.now().strftime("%Y-%m-%d %H:%M"), email))
        conn.commit()


def downgrade_to_free(email):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET plan='free' WHERE email=?", (email,))
        conn.commit()


def submit_upgrade_request(email, full_name, message=""):
    # FIX 2: بدل Upgrade تلقائي → بنحفظ Request بس
    with get_conn() as conn:
        cursor = conn.cursor()

        # تحقق مش عنده request pending قبل كده
        cursor.execute("""
            SELECT id FROM upgrade_requests
            WHERE email=? AND status='pending'
        """, (email,))
        existing = cursor.fetchone()

        if existing:
            return False, "⏳ You already have a pending request!"

        cursor.execute("""
            INSERT INTO upgrade_requests (email, full_name, message)
            VALUES (?, ?, ?)
        """, (email, full_name, message))
        conn.commit()
        return True, "✅ Request submitted!"


def save_prices(data, tickers, asset_types):
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
                        """, (ticker, str(date_idx.date()),
                              round(float(price), 4), asset_type))
                        saved += 1
                    except: pass
            except: pass
        conn.commit()
    return saved


def safe_float(val, default=0.0):
    # بتحول أي قيمة لرقم آمن
    # لو nan أو None أو فيه % → بترجع default
    try:
        result = float(str(val).replace("%","").replace("nan","").strip())
        if result != result:  # nan != nan دايماً True
            return default
        return result
    except:
        return default


def save_metrics(risk_data, period, user_email):
    if not user_email: return
    with get_conn() as conn:
        cursor = conn.cursor()
        for row in risk_data:
            try:
                # safe_float = بتتأكد إن القيمة مش nan قبل الحفظ
                cursor.execute("""
                    INSERT INTO stock_metrics
                    (user_email, ticker, period, asset_type,
                     total_return, volatility, sharpe_ratio,
                     beta, alpha, max_drawdown, var_95)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_email, row["Asset"], period,
                    row.get("Type","stock").lower(),
                    safe_float(row["Return"]),
                    safe_float(row["Volatility"]),
                    safe_float(row["Sharpe Ratio"]),
                    safe_float(row["Beta"]),
                    safe_float(row["Alpha"]),
                    safe_float(row["Max Drawdown"]),
                    safe_float(row["VaR (95%)"])
                ))
            except: pass
        conn.commit()


# ============================================================
# PART 6: Reset Code Functions — SOL 3
# ============================================================
def generate_reset_code(email):
    code       = ''.join(random.choices(string.digits, k=6))
    expires_at = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reset_codes WHERE email=?", (email,))
        cursor.execute("""
            INSERT INTO reset_codes (email, code, expires_at)
            VALUES (?, ?, ?)
        """, (email.lower(), code, expires_at))
        conn.commit()
    return code


def verify_reset_code(email, code):
    with get_conn() as conn:
        cursor = conn.cursor()
        now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            SELECT id FROM reset_codes
            WHERE email=? AND code=? AND expires_at>? AND used=0
        """, (email.lower(), code, now))
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE reset_codes SET used=1 WHERE id=?", (row["id"],))
            conn.commit()
            return True
        return False


def reset_password(email, new_password):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_hash=? WHERE email=?",
                       (hash_password(new_password), email.lower()))
        conn.commit()
        return cursor.rowcount > 0


# ============================================================
# PART 7: yfinance with Rate Limiter
# ============================================================
def fetch_data_safe(tickers, period):
    valid_data    = {}
    error_tickers = []
    for ticker in tickers:
        try:
            rate_limiter.wait_if_needed(ticker)
            raw = yf.download(ticker, period=period,
                              progress=False, auto_adjust=True)['Close']
            # FIX MultiIndex: yfinance الجديد بيرجع ("Close","AAPL") بدل "AAPL"
            if isinstance(raw, pd.DataFrame):
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = raw.columns.get_level_values(-1)
                raw = raw.iloc[:,0]
            raw = raw.squeeze().dropna()
            if len(raw) < 2:
                error_tickers.append(ticker)
                continue
            valid_data[ticker] = raw
        except:
            error_tickers.append(ticker)

    if not valid_data:
        return None, [], error_tickers
    data = pd.DataFrame(valid_data)
    # FIX MultiIndex في الـ DataFrame النهائي
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(-1)
    return data, list(valid_data.keys()), error_tickers


# ============================================================
# PART 8: App Setup
# ============================================================
st.set_page_config(
    page_title="Investment & Wealth Engine",
    page_icon="📈",
    layout="wide"
)

# ─── Custom CSS ───────────────────────────────────────────────
st.markdown("""
<style>
/* Font */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Space+Grotesk:wght@400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

/* Background */
.stApp {
    background: linear-gradient(135deg, #0a0e1a 0%, #0d1117 50%, #0a0f1e 100%);
}

/* Metric Cards */
[data-testid="metric-container"] {
    background: linear-gradient(135deg, #1a1f2e 0%, #151a28 100%);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.3);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
[data-testid="metric-container"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(0,180,216,0.15);
}

/* Metric label */
[data-testid="metric-container"] label {
    font-size: 11px !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: rgba(255,255,255,0.45) !important;
}

/* Metric value */
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 26px !important;
    font-weight: 700 !important;
    color: #ffffff !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border-radius: 12px !important;
    overflow: hidden !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
}

/* Buttons */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    transition: all 0.2s ease !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #00b4d8, #0077b6) !important;
    border: none !important;
    color: white !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #00caf0, #0096c7) !important;
    box-shadow: 0 4px 20px rgba(0,180,216,0.4) !important;
    transform: translateY(-1px) !important;
}

/* Input fields */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div {
    background: #1a1f2e !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
    color: white !important;
}

/* Expander */
[data-testid="stExpander"] {
    background: #131824 !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 12px !important;
    overflow: hidden !important;
}
[data-testid="stExpander"] summary {
    font-weight: 600 !important;
    font-size: 14px !important;
    color: rgba(255,255,255,0.85) !important;
    padding: 14px 18px !important;
}

/* Divider */
hr {
    border-color: rgba(255,255,255,0.06) !important;
    margin: 20px 0 !important;
}

/* Warning / Success / Error */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    border-left-width: 4px !important;
    font-size: 14px !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    background: #0d1117 !important;
    border-radius: 10px !important;
    padding: 4px !important;
    gap: 4px !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    color: rgba(255,255,255,0.5) !important;
    padding: 8px 18px !important;
}
.stTabs [aria-selected="true"] {
    background: #1a1f2e !important;
    color: white !important;
}

/* Hide Streamlit branding */
#MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

init_database()

if "logged_in" not in st.session_state:
    st.session_state.logged_in    = False
    st.session_state.user         = None
    st.session_state.is_admin     = False
    st.session_state.saved_email  = ""
    st.session_state.saved_admin  = False
    # saved_email = بنحفظ الإيميل هنا
    # بيفضل محفوظ حتى بعد Refresh
    # عشان الـ App يعرف يرجع يجيب بيانات المستخدم

# FIX 2: Session Restore بعد Refresh
# لو الـ logged_in اتمسح بسبب Refresh
# بنرجع نجيب البيانات من الـ DB بالإيميل المحفوظ
if not st.session_state.logged_in and st.session_state.saved_email:
    email_saved = st.session_state.saved_email
    if email_saved == ADMIN_EMAIL and st.session_state.saved_admin:
        # رجّع الـ Admin session
        st.session_state.logged_in = True
        st.session_state.is_admin  = True
        st.session_state.user      = {
            "id": 0, "email": ADMIN_EMAIL,
            "full_name": "Admin", "plan": "admin",
            "analyses_count": 0,
            "analyses_date": date.today().isoformat()
        }
    elif email_saved and email_saved != ADMIN_EMAIL:
        # رجّع الـ User session من الـ DB
        restored = get_user_from_db(email_saved)
        if restored:
            st.session_state.logged_in = True
            st.session_state.user      = restored
            st.session_state.is_admin  = False

# Session Refresh — تحديث البيانات لو الـ Session موجود
if st.session_state.logged_in and st.session_state.user:
    email_sess = st.session_state.user.get("email","")
    if email_sess and email_sess != ADMIN_EMAIL:
        fresh = get_user_from_db(email_sess)
        if fresh:
            st.session_state.user = fresh
        else:
            st.session_state.logged_in   = False
            st.session_state.user        = None
            st.session_state.saved_email = ""


# ============================================================
# PART 9: Auth Page
# ============================================================
def show_auth_page():
    st.markdown("# 📈 Investment & Wealth Engine")
    st.markdown("##### AI-Powered Multi-Asset Portfolio System | Built by Mennahtullah Saeed")
    st.divider()

    col_info, col_form = st.columns([1,1])

    with col_info:
        st.markdown("### 💎 Plans")
        st.markdown(f"""
        **🆓 Free — 3 analyses/day**
        - ✅ Stocks, Crypto, Commodities
        - ✅ Risk Analysis & Benchmark
        - ❌ Monte Carlo
        - ❌ Allocation & Full History

        ---

        **⭐ Pro — $9.99/month**
        - ✅ Unlimited analyses
        - ✅ Monte Carlo Simulation
        - ✅ Investment Allocation
        - ✅ Full History + CSV Export

        *Login and click the Upgrade button to request Pro access.*
        """)

    with col_form:
        tab_login, tab_register, tab_forgot = st.tabs([
            "🔑 Login", "📝 Register", "🔓 Forgot Password"
        ])

        with tab_login:
            st.markdown("### Welcome Back!")
            email    = st.text_input("Email", key="login_email",
                                     placeholder="your@email.com")
            password = st.text_input("Password", type="password", key="login_pass")

            if st.button("Login", type="primary", use_container_width=True):
                if not email or not password:
                    st.warning("⚠️ Fill all fields")
                else:
                    result, user = login_user(email, password)
                    if result == "admin":
                        st.session_state.logged_in   = True
                        st.session_state.user        = user
                        st.session_state.is_admin    = True
                        st.session_state.saved_email = ADMIN_EMAIL
                        st.session_state.saved_admin = True
                        # نحفظ الإيميل عشان Refresh ميلوش session ✅
                        st.rerun()
                    elif result:
                        st.session_state.logged_in   = True
                        st.session_state.user        = user
                        st.session_state.is_admin    = False
                        st.session_state.saved_email = user["email"]
                        st.session_state.saved_admin = False
                        # نحفظ الإيميل عشان Refresh ميلوش session ✅
                        st.rerun()
                    else:
                        st.error("❌ Invalid email or password")

        with tab_register:
            st.markdown("### Create Free Account")
            reg_name  = st.text_input("Full Name", key="reg_name")
            reg_email = st.text_input("Email",     key="reg_email")
            reg_pass  = st.text_input("Password",  type="password", key="reg_pass")
            reg_pass2 = st.text_input("Confirm",   type="password", key="reg_pass2")

            if st.button("Create Account", type="primary", use_container_width=True):
                if not all([reg_name, reg_email, reg_pass, reg_pass2]):
                    st.warning("⚠️ Fill all fields")
                elif "@" not in reg_email:
                    st.error("❌ Invalid email")
                elif reg_pass != reg_pass2:
                    st.error("❌ Passwords don't match")
                elif len(reg_pass) < 6:
                    st.error("❌ Password must be 6+ characters")
                else:
                    ok, msg = register_user(reg_email, reg_pass, reg_name)
                    if ok:
                        # FIX: بنحفظ رسالة النجاح في session_state
                        # وبعدين نعمل rerun عشان نتجنب DeltaGenerator error
                        st.session_state["reg_success"] = True
                        st.session_state["reg_msg"]     = msg
                        st.rerun()
                    else:
                        st.error(msg)

            # بنعرض رسالة النجاح بره الـ button block عشان مفيش conflict
            if st.session_state.get("reg_success", False):
                st.success(st.session_state.get("reg_msg", "✅ Account created!"))
                st.info("👉 Go to Login tab to sign in")
                st.session_state["reg_success"] = False

        with tab_forgot:
            st.markdown("### 🔓 Reset Password")
            fp_email = st.text_input("Your Email", key="fp_email")
            if st.button("Send Code", use_container_width=True):
                if not fp_email or "@" not in fp_email:
                    st.error("❌ Enter valid email")
                else:
                    with get_conn() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM users WHERE email=?",
                                       (fp_email.strip().lower(),))
                        exists = cursor.fetchone()
                    if exists:
                        code = generate_reset_code(fp_email.strip().lower())
                        st.success(f"✅ Your code: **{code}**")
                        st.caption("⏰ Valid for 15 minutes")
                        st.session_state["reset_email"] = fp_email.strip().lower()
                    else:
                        st.info("📧 If email exists, code will appear here.")

            st.divider()
            reset_email = st.session_state.get("reset_email","")
            fp_code    = st.text_input("6-Digit Code", key="fp_code", max_chars=6)
            fp_new     = st.text_input("New Password", type="password", key="fp_new")
            fp_new2    = st.text_input("Confirm",      type="password", key="fp_new2")

            if st.button("Reset Password", type="primary", use_container_width=True):
                if not reset_email:
                    st.error("❌ Request a code first")
                elif not fp_code or not fp_new:
                    st.warning("⚠️ Fill all fields")
                elif fp_new != fp_new2:
                    st.error("❌ Passwords don't match")
                elif len(fp_new) < 6:
                    st.error("❌ Min 6 characters")
                elif not verify_reset_code(reset_email, fp_code):
                    st.error("❌ Invalid or expired code")
                else:
                    if reset_password(reset_email, fp_new):
                        st.success("✅ Password reset! Login now.")
                        del st.session_state["reset_email"]
                    else:
                        st.error("❌ Something went wrong.")


# ============================================================
# PART 10: Admin Dashboard — FIX 3
# ============================================================
def show_admin_dashboard():
    st.markdown("# 🔐 Admin Dashboard")
    st.markdown("##### Investment & Wealth Engine — Control Panel")

    if st.button("Logout"):
        st.session_state.logged_in   = False
        st.session_state.user        = None
        st.session_state.is_admin    = False
        st.session_state.saved_email = ""
        st.session_state.saved_admin = False
        st.rerun()

    st.divider()

    with get_conn() as conn:

        # ── Stats ─────────────────────────────────────────────
        total_users    = pd.read_sql("SELECT COUNT(*) as n FROM users", conn).iloc[0]["n"]
        pro_users      = pd.read_sql("SELECT COUNT(*) as n FROM users WHERE plan='pro'", conn).iloc[0]["n"]
        total_analyses = pd.read_sql("SELECT COUNT(*) as n FROM stock_metrics", conn).iloc[0]["n"]
        pending_req    = pd.read_sql("SELECT COUNT(*) as n FROM upgrade_requests WHERE status='pending'", conn).iloc[0]["n"]

        c1,c2,c3,c4 = st.columns(4)
        c1.metric("👥 Users",          total_users)
        c2.metric("⭐ Pro",            pro_users)
        c3.metric("📊 Analyses",       total_analyses)
        c4.metric("🔔 Pending Upgrades", pending_req)

        st.divider()

        # ── FIX 3: Upgrade Requests ───────────────────────────
        # هنا الـ Admin بيشوف الطلبات ويوافق يدوياً
        st.markdown("### 🔔 Upgrade Requests")

        req_df = pd.read_sql("""
            SELECT email AS Email, full_name AS Name,
                   message AS Message, status AS Status,
                   requested_at AS "Requested At"
            FROM upgrade_requests
            ORDER BY requested_at DESC
            LIMIT 30
        """, conn)

        if not req_df.empty:
            # فلتر بالحالة
            filter_status = st.selectbox(
                "Filter", ["pending","approved","rejected","all"],
                key="req_filter"
            )
            filtered = req_df if filter_status == "all" else req_df[req_df["Status"] == filter_status]
            st.dataframe(filtered, use_container_width=True, hide_index=True)

            # ── موافقة / رفض ──────────────────────────────────
            st.markdown("#### ✅ Approve or ❌ Reject")
            col_e, col_a = st.columns(2)
            with col_e:
                target = st.text_input("User Email", key="req_email",
                                       placeholder="user@email.com")
            with col_a:
                action = st.selectbox("Action",
                                      ["✅ Approve (Upgrade to Pro)",
                                       "❌ Reject Request",
                                       "⬇️ Downgrade to Free"],
                                      key="req_action")

            if st.button("Apply Decision", type="primary"):
                if not target:
                    st.warning("Enter email first")
                else:
                    t = target.strip().lower()
                    if "Approve" in action:
                        upgrade_to_pro(t)
                        st.success(f"✅ {t} upgraded to Pro!")
                    elif "Reject" in action:
                        with get_conn() as c2:
                            c2.cursor().execute("""
                                UPDATE upgrade_requests
                                SET status='rejected', reviewed_at=?
                                WHERE email=? AND status='pending'
                            """, (datetime.now().strftime("%Y-%m-%d %H:%M"), t))
                            c2.commit()
                        st.warning(f"❌ {t} request rejected.")
                    elif "Downgrade" in action:
                        downgrade_to_free(t)
                        st.info(f"⬇️ {t} downgraded to Free.")
                    st.rerun()
        else:
            st.info("📭 No upgrade requests yet")

        st.divider()

        # ── Users Table ───────────────────────────────────────
        st.markdown("### 👥 All Users")
        users_df = pd.read_sql("""
            SELECT email AS Email, full_name AS Name,
                   plan AS Plan,
                   analyses_count AS "Today's Analyses",
                   created_at AS Joined, last_login AS "Last Login"
            FROM users ORDER BY created_at DESC
        """, conn)

        if not users_df.empty:
            st.dataframe(users_df, use_container_width=True, hide_index=True)

            # ── إدارة الـ Plan مباشرة من جدول المستخدمين ─────
            st.markdown("#### ⚙️ Manage User Plan")
            st.caption("Upgrade or downgrade any user directly without needing a request")

            col_em, col_pl, col_btn = st.columns([2, 1, 1])
            with col_em:
                direct_email = st.text_input(
                    "User Email",
                    key="direct_email",
                    placeholder="user@email.com"
                )
            with col_pl:
                direct_action = st.selectbox(
                    "New Plan",
                    ["⭐ Upgrade to Pro", "⬇️ Downgrade to Free"],
                    key="direct_action"
                )
            with col_btn:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                # سطر فراغ عشان الزرار يتنازل مع الحقول
                apply_direct = st.button(
                    "✅ Apply",
                    type="primary",
                    use_container_width=True,
                    key="apply_direct"
                )

            if apply_direct:
                if not direct_email.strip():
                    st.warning("⚠️ Enter user email first")
                else:
                    t = direct_email.strip().lower()
                    # تحقق إن المستخدم موجود
                    with get_conn() as check_conn:
                        cur = check_conn.cursor()
                        cur.execute("SELECT plan FROM users WHERE email=?", (t,))
                        existing = cur.fetchone()

                    if not existing:
                        st.error(f"❌ User {t} not found!")
                    elif "Upgrade" in direct_action:
                        upgrade_to_pro(t)
                        st.success(f"✅ {t} upgraded to Pro!")
                        st.rerun()
                    else:
                        downgrade_to_free(t)
                        st.info(f"⬇️ {t} downgraded to Free.")
                        st.rerun()
        else:
            st.info("No users yet")

        st.divider()

        # ── Recent Analyses ───────────────────────────────────
        st.markdown("### 📊 Recent Analyses")
        analyses_df = pd.read_sql("""
            SELECT user_email AS User, ticker AS Asset,
                   asset_type AS Type, period AS Period,
                   total_return AS "Return%",
                   sharpe_ratio AS Sharpe,
                   analyzed_at AS Date
            FROM stock_metrics
            ORDER BY analyzed_at DESC LIMIT 50
        """, conn)

        if not analyses_df.empty:
            sel_u = st.selectbox("Filter by User",
                                 ["All"]+sorted(analyses_df["User"].unique().tolist()))
            if sel_u != "All":
                analyses_df = analyses_df[analyses_df["User"]==sel_u]
            st.dataframe(analyses_df, use_container_width=True, hide_index=True)
            st.download_button("📥 Export CSV",
                               data=analyses_df.to_csv(index=False),
                               file_name="analyses.csv", mime="text/csv")
        else:
            st.info("No analyses yet")

        st.divider()

        # ── Reset Codes Monitor ───────────────────────────────
        st.markdown("### 🔓 Password Reset Requests")
        resets_df = pd.read_sql("""
            SELECT email, code, expires_at,
                   CASE used WHEN 1 THEN '✅ Used' ELSE '⏳ Pending' END AS Status,
                   created_at
            FROM reset_codes ORDER BY created_at DESC LIMIT 20
        """, conn)
        if not resets_df.empty:
            st.dataframe(resets_df, use_container_width=True, hide_index=True)
        else:
            st.info("No reset requests")


# ============================================================
# PART 11: User Dashboard
# ============================================================
def show_dashboard():
    user       = st.session_state.user
    is_pro     = user["plan"] == "pro"
    user_email = user.get("email","").strip().lower()

    if not user_email:
        st.error("❌ Session error. Login again.")
        st.session_state.logged_in = False
        st.rerun()
        return

    # Header
    col_title, col_user = st.columns([3,1])
    with col_title:
        st.markdown("# 📈 Investment & Wealth Engine")
        st.markdown("##### AI-Powered Multi-Asset Portfolio System | Built by Mennahtullah Saeed")
    with col_user:
        badge = "⭐ Pro" if is_pro else "🆓 Free"
        st.markdown(f"**👤 {user['full_name']}**")
        st.markdown(f"**{badge}**")
        if not is_pro:
            remaining = max(0, 3 - user["analyses_count"])
            st.caption(f"Today: {user['analyses_count']}/3 ({remaining} left)")
            st.caption("🔄 Resets daily at midnight")
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in   = False
            st.session_state.user        = None
            st.session_state.saved_email = ""
            st.session_state.saved_admin = False
            # نمسح الإيميل المحفوظ عشان ميرجعش تاني ✅
            st.rerun()

    st.divider()

    # ── Upgrade Banner ────────────────────────────────────────
    if not is_pro:
        st.warning("🆓 **Free Plan** — Upgrade to Pro for unlimited analyses & all features!")

        if st.button("⭐ Upgrade to Pro — $9.99/month",
                     type="primary", use_container_width=True,
                     key="show_upgrade_form"):
            st.session_state["show_upgrade"] = True

        if st.session_state.get("show_upgrade", False):
            st.markdown("---")
            st.markdown("### 📋 Upgrade Request Form")
            st.caption("Fill in your details and we will contact you to confirm your upgrade.")

            upg_name = st.text_input(
                "Full Name *",
                value=user["full_name"],
                key="upg_name"
            )
            st.text_input(
                "Email (auto-filled)",
                value=user_email,
                key="upg_email_field",
                disabled=True
            )
            upg_phone = st.text_input(
                "Phone / WhatsApp *",
                key="upg_phone",
                placeholder="+20 1XX XXX XXXX"
            )
            upg_msg = st.text_area(
                "Additional Message (optional)",
                key="upg_msg",
                placeholder="Any notes or questions..."
            )

            col_send, col_cancel = st.columns(2)
            with col_send:
                if st.button("📨 Send Request", type="primary",
                             use_container_width=True, key="send_upg"):
                    if not upg_phone.strip():
                        st.warning("⚠️ Phone number is required")
                    else:
                        full_msg = (
                            f"Name: {upg_name} | "
                            f"Phone: {upg_phone} | "
                            f"Notes: {upg_msg}"
                        )
                        ok, msg = submit_upgrade_request(
                            user_email,
                            upg_name,
                            full_msg
                        )
                        if ok:
                            st.success("✅ Request sent! We will contact you soon.")
                            st.session_state["show_upgrade"] = False
                        else:
                            st.warning(msg)
            with col_cancel:
                if st.button("✖ Cancel", use_container_width=True,
                             key="cancel_upg"):
                    st.session_state["show_upgrade"] = False
                    st.rerun()


    st.divider()

    # Input Section
    st.markdown("### 🔍 Enter Your Portfolio")
    st.info("""
    💡 **Supported:** 🏢 Stocks: AAPL, MSFT | 🪙 Crypto: BTC-USD, ETH-USD
    🥇 Commodities: GC=F (Gold) | 📊 Bonds: TLT | 🇪🇬 Egypt: COMI.CA
    """)

    template_df = pd.DataFrame({'ticker': ['AAPL','MSFT','BTC-USD','ETH-USD',
                                            'GC=F','GOOGL','TSLA','NVDA','TLT','SPY']})
    buf = BytesIO()
    template_df.to_excel(buf, index=False)
    buf.seek(0)
    st.download_button("📥 Template", data=buf,
                       file_name="template.xlsx",
                       mime="application/vnd.ms-excel")

    uploaded_file  = st.file_uploader("📎 Upload Excel/CSV", type=["xlsx","xls","csv"])
    default_stocks = "AAPL, MSFT, BTC-USD"

    if uploaded_file:
        try:
            df_up = (pd.read_csv(uploaded_file)
                     if uploaded_file.name.endswith('.csv')
                     else pd.read_excel(uploaded_file))
            clean = [str(t).strip().upper() for t in df_up.iloc[:,0].dropna()
                     if str(t).strip().upper() not in ['TICKER','SYMBOL','STOCK','']]
            if clean:
                default_stocks = ", ".join(clean)
                st.success(f"✅ Loaded {len(clean)} assets!")
        except Exception as e:
            st.error(f"❌ File error: {e}")

    col1, col2 = st.columns(2)
    with col1: stocks = st.text_input("Asset Symbols", value=default_stocks)
    with col2: period = st.selectbox("Period", ["1mo","3mo","6mo","1y","2y"])

    st.markdown("### 💰 Investment Amount")
    ca, cb = st.columns(2)
    with ca: amount   = st.number_input("Amount", min_value=0, value=10000, step=1000)
    with cb: currency = st.selectbox("Currency", ["USD $","EGP جنيه","EUR €"])

    c3, c4 = st.columns(2)
    with c3: analyze_btn  = st.button("📊 Analyze", type="primary", use_container_width=True)
    with c4: optimize_btn = st.button("⚡ Optimize (Pro)", use_container_width=True,
                                      disabled=not is_pro)


    # ============================================================
    # PART 12: Analysis Logic
    # ============================================================
    if analyze_btn or optimize_btn:

        fresh = get_user_from_db(user_email)
        if fresh:
            st.session_state.user["analyses_count"] = fresh["analyses_count"]
            user = st.session_state.user

        if not is_pro and user["analyses_count"] >= 3:
            st.error("❌ Daily limit (3/3)! Upgrade or try tomorrow.")
            return

        if not stocks.strip():
            st.error("❌ Enter at least one symbol!")
            return

        tickers = [s.strip().upper() for s in stocks.split(",") if s.strip()]
        if not tickers: return
        if optimize_btn: period = "1y"

        asset_types = {}
        for t in tickers:
            if any(x in t for x in ['-USD','-EUR','-BTC']):
                asset_types[t] = 'crypto'
            elif t in ['GC=F','SI=F','CL=F','NG=F']:
                asset_types[t] = 'commodity'
            elif t in ['TLT','IEF','SHY','BND','AGG']:
                asset_types[t] = 'bond'
            elif t.endswith('.CA'):
                asset_types[t] = 'egypt'
            else:
                asset_types[t] = 'stock'

        with st.spinner("⏳ Fetching data..."):

            data, valid_tickers, error_tickers = fetch_data_safe(tickers, period)

            if error_tickers:
                st.warning(
                    f"⚠️ Could not fetch: **{', '.join(error_tickers)}**\n\n"
                    "Check: spelling | '.CA' for Egypt | '-USD' for Crypto"
                )

            if data is None or not valid_tickers:
                st.error("❌ No valid data.")
                return

            tickers     = valid_tickers
            asset_types = {t: asset_types.get(t,'stock') for t in tickers}

            # S&P 500
            sp500_data = market_returns = None
            try:
                rate_limiter.wait_if_needed("^GSPC")
                sp_raw = yf.download("^GSPC", period=period,
                                     progress=False, auto_adjust=True)['Close']
                if isinstance(sp_raw, pd.DataFrame): sp_raw = sp_raw.iloc[:,0]
                sp500_data     = sp_raw.squeeze().dropna()
                market_returns = sp500_data.pct_change().dropna()
            except: pass

            gold_data = usd_data = None
            try:
                rate_limiter.wait_if_needed("GC=F")
                g = yf.download("GC=F", period=period,
                                progress=False, auto_adjust=True)['Close']
                if isinstance(g, pd.DataFrame): g = g.iloc[:,0]
                if len(g)>1: gold_data = g.squeeze()
            except: pass

            try:
                rate_limiter.wait_if_needed("DX-Y.NYB")
                u = yf.download("DX-Y.NYB", period=period, progress=False)['Close']
                if isinstance(u, pd.DataFrame): u = u.iloc[:,0]
                if len(u)>1: usd_data = u.squeeze()
            except: pass

            returns    = data.pct_change().dropna()
            rows_saved = save_prices(data, tickers, asset_types)
            increment_analysis(user_email)
            st.session_state.user["analyses_count"] += 1

        st.divider()

        # ── الـ Layout الجديد ─────────────────────────────────
        # فكرة: نحسب كل البيانات الأول
        # وبعدين نعرضها في Layout منظم بـ Expanders

        type_emoji = {'stock':'🏢','crypto':'🪙','commodity':'🥇',
                      'bond':'📊','egypt':'🇪🇬'}

        # ── حساب Overview ────────────────────────────────────
        overview = []
        for ticker in tickers:
            try:
                clean_col = data[ticker].dropna()
                if len(clean_col) < 2: continue
                ret    = ((float(clean_col.iloc[-1]) / float(clean_col.iloc[0])) - 1) * 100
                sharpe = (returns[ticker].mean()*252)/(returns[ticker].std()*np.sqrt(252))
                vol    = returns[ticker].std()*np.sqrt(252)*100
                price  = float(clean_col.iloc[-1])
                atype  = asset_types.get(ticker,'stock')
                signal = "✅ Strong" if sharpe>1 else ("⚠️ Hold" if sharpe>0 else "🔴 Weak")
                overview.append({
                    "emoji": type_emoji.get(atype,'📈'),
                    "ticker": ticker, "price": price,
                    "ret": ret, "sharpe": sharpe,
                    "vol": vol, "signal": signal,
                    "atype": atype
                })
            except: pass

        # ── حساب Risk Data ────────────────────────────────────
        risk_data = []
        for ticker in tickers:
            try:
                r     = returns[ticker].dropna()
                atype = asset_types.get(ticker,'stock')
                beta  = alpha = 0.0
                if market_returns is not None:
                    mkt = market_returns.copy()
                    if isinstance(mkt, pd.DataFrame): mkt = mkt.iloc[:,0]
                    mkt    = mkt.squeeze().dropna()
                    common = r.index.intersection(mkt.index)
                    if len(common) >= 2:
                        r_al=r.loc[common]; m_al=mkt.loc[common]
                        beta  = float(r_al.cov(m_al)/m_al.var())
                        alpha = float((r_al.mean()*252)-(m_al.mean()*252))
                clean = data[ticker].dropna()
                if len(clean) < 2: continue
                first_price = float(clean.iloc[0])
                last_price  = float(clean.iloc[-1])
                ret_pct     = ((last_price / first_price) - 1) * 100
                risk_data.append({
                    "Type"        : atype.title(),
                    "Asset"       : ticker,
                    "Return"      : f"{ret_pct:.1f}%",
                    "Volatility"  : f"{r.std()*np.sqrt(252)*100:.1f}%",
                    "Sharpe Ratio": f"{(r.mean()*252)/(r.std()*np.sqrt(252)):.2f}",
                    "Beta"        : f"{beta:.2f}",
                    "Alpha"       : f"{alpha:.2f}",
                    "Max Drawdown": f"{((data[ticker]/data[ticker].cummax())-1).min()*100:.1f}%",
                    "VaR (95%)"   : f"{r.quantile(0.05)*100:.2f}%",
                    "Kurtosis"    : f"{r.kurtosis():.2f}",
                })
            except: pass

        if risk_data:
            save_metrics(risk_data, period, user_email)

        # ════════════════════════════════════════════════════════
        # ROW 1: KPI Cards — صف واحد فيه أهم الأرقام
        # ════════════════════════════════════════════════════════
        st.markdown("### 📊 Portfolio Snapshot")

        # Portfolio Return vs Benchmark
        individual_returns = []
        for t in tickers:
            try:
                clean_t = data[t].dropna()
                if len(clean_t) >= 2:
                    r = float(((clean_t.iloc[-1]/clean_t.iloc[0])-1)*100)
                    if not np.isnan(r): individual_returns.append(r)
            except: pass

        port_ret = float(np.mean(individual_returns)) if individual_returns else 0.0
        sp_ret   = float(((sp500_data.iloc[-1]/sp500_data.iloc[0])-1)*100) if sp500_data is not None and len(sp500_data)>1 else None
        diff     = port_ret - sp_ret if sp_ret is not None else None

        avg_sharpe = float(np.mean([float(r["Sharpe Ratio"]) for r in risk_data])) if risk_data else 0.0
        avg_vol    = float(np.mean([float(r["Volatility"].replace("%","")) for r in risk_data])) if risk_data else 0.0

        # صف الـ KPIs الأساسية
        kc1, kc2, kc3, kc4, kc5 = st.columns(5)
        kc1.metric("📈 Portfolio Return",  f"{port_ret:.1f}%",
                   delta=f"{diff:+.1f}% vs S&P" if diff is not None else None)
        kc2.metric("📊 S&P 500",           f"{sp_ret:.1f}%" if sp_ret is not None else "N/A")
        kc3.metric("⚡ Avg Sharpe Ratio",  f"{avg_sharpe:.2f}")
        kc4.metric("📉 Avg Volatility",    f"{avg_vol:.1f}%")
        kc5.metric("🔢 Assets Analyzed",   str(len(tickers)))

        # AI Recommendation بعد الـ KPIs مباشرة
        if risk_data:
            try:
                avg_b = float(np.mean([float(r["Beta"]) for r in risk_data]))
                if avg_sharpe > 1 and avg_b < 1.2:
                    st.success(f"✅ **Strong Portfolio** — Well-balanced risk/return | Sharpe: {avg_sharpe:.2f} | Beta: {avg_b:.2f}")
                elif avg_sharpe > 0 and avg_b < 1.5:
                    st.warning(f"🟡 **Moderate Portfolio** — Consider diversifying | Sharpe: {avg_sharpe:.2f} | Beta: {avg_b:.2f}")
                else:
                    st.error(f"🔴 **High Risk Portfolio** — Review selection | Sharpe: {avg_sharpe:.2f} | Beta: {avg_b:.2f}")
            except: pass

        st.divider()

        # ════════════════════════════════════════════════════════
        # ROW 2: Asset Type Counts + Best Asset
        # ════════════════════════════════════════════════════════
        tc1,tc2,tc3,tc4,tc5 = st.columns(5)
        tc1.metric("🏢 Stocks",      sum(1 for t in tickers if asset_types.get(t)=='stock'))
        tc2.metric("🪙 Crypto",      sum(1 for t in tickers if asset_types.get(t)=='crypto'))
        tc3.metric("🥇 Commodities", sum(1 for t in tickers if asset_types.get(t)=='commodity'))
        tc4.metric("📊 Bonds",       sum(1 for t in tickers if asset_types.get(t)=='bond'))
        tc5.metric("🇪🇬 Egypt",      sum(1 for t in tickers if asset_types.get(t)=='egypt'))

        st.divider()

        # ════════════════════════════════════════════════════════
        # ROW 3: Charts في عمودين جنب بعض
        # ════════════════════════════════════════════════════════
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            try:
                norm = data.div(data.dropna().iloc[0])*100
                fig  = px.line(norm, title="📈 Normalized Performance")
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(15,17,23,0.8)',
                    font={'color':'white','size':11},
                    hovermode='x unified',
                    margin=dict(l=10,r=10,t=40,b=10),
                    legend=dict(orientation="h", y=-0.15)
                )
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.warning(f"Chart: {e}")

        with chart_col2:
            if sp500_data is not None and len(sp500_data) > 1:
                try:
                    norm_each = data.div(data.iloc[0]) * 100
                    norm_p    = norm_each.mean(axis=1).dropna()
                    norm_sp   = (sp500_data/sp500_data.iloc[0])*100
                    bench_df  = pd.DataFrame({
                        'Your Portfolio': norm_p,
                        'S&P 500'       : norm_sp
                    }).dropna()
                    if not bench_df.empty:
                        fig_b = px.line(bench_df,
                                        title="🏆 Portfolio vs S&P 500",
                                        color_discrete_map={
                                            'Your Portfolio':'#00b4d8',
                                            'S&P 500':'#f4a261'
                                        })
                        fig_b.update_layout(
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(15,17,23,0.8)',
                            font={'color':'white','size':11},
                            margin=dict(l=10,r=10,t=40,b=10),
                            legend=dict(orientation="h", y=-0.15)
                        )
                        st.plotly_chart(fig_b, use_container_width=True)
                except Exception as e:
                    st.caption(f"Benchmark: {e}")

        st.divider()

        # ════════════════════════════════════════════════════════
        # Expanders — التفاصيل بدون Scroll كتير
        # ════════════════════════════════════════════════════════

        # ── Expander 1: Portfolio Table ───────────────────────
        with st.expander("📋 Portfolio Overview — Full Table", expanded=True):
            if overview:
                overview_df = pd.DataFrame([{
                    "": o["emoji"], "Asset": o["ticker"],
                    "Price": f"${o['price']:.2f}",
                    "Return": f"{o['ret']:.1f}%",
                    "Sharpe": f"{o['sharpe']:.2f}",
                    "Volatility": f"{o['vol']:.1f}%",
                    "Signal": o["signal"]
                } for o in overview])
                st.dataframe(overview_df, use_container_width=True, hide_index=True)

        # ── Expander 2: Multi-Asset Comparison ────────────────
        with st.expander("🥇 Multi-Asset Return Comparison"):
            comparison  = []
            type_label  = {'stock':'Stock','crypto':'Crypto','commodity':'Commodity',
                           'bond':'Bond','egypt':'Egypt'}
            for t in tickers:
                try:
                    c = data[t].dropna()
                    if len(c) >= 2:
                        ret = float(((c.iloc[-1]/c.iloc[0])-1)*100)
                        if not np.isnan(ret):
                            comparison.append({"Asset":t,"Return":ret,
                                               "Type":type_label.get(asset_types.get(t,'stock'),'Stock')})
                except: pass
            if gold_data is not None and 'GC=F' not in tickers:
                try:
                    g=gold_data.dropna()
                    comparison.append({"Asset":"🥇 Gold","Return":float(((g.iloc[-1]/g.iloc[0])-1)*100),"Type":"Commodity"})
                except: pass
            if usd_data is not None:
                try:
                    u=usd_data.dropna()
                    comparison.append({"Asset":"💵 USD","Return":float(((u.iloc[-1]/u.iloc[0])-1)*100),"Type":"Currency"})
                except: pass
            if sp500_data is not None:
                try:
                    comparison.append({"Asset":"📈 S&P 500","Return":float(((sp500_data.iloc[-1]/sp500_data.iloc[0])-1)*100),"Type":"Index"})
                except: pass

            if comparison:
                comp_df = pd.DataFrame(comparison)
                fig_c   = px.bar(comp_df, x="Asset", y="Return", color="Type",
                                 title=f"Return Comparison — {period}", text="Return",
                                 color_discrete_map={'Stock':'#00b4d8','Crypto':'#9b5de5',
                                                     'Commodity':'#f4a261','Bond':'#2a9d8f',
                                                     'Currency':'#e9c46a','Index':'#e76f51','Egypt':'#06d6a0'})
                fig_c.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                fig_c.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(15,17,23,0.8)',
                                    font={'color':'white'}, margin=dict(t=40))
                st.plotly_chart(fig_c, use_container_width=True)
                best_i = int(np.argmax([c['Return'] for c in comparison]))
                st.info(f"🏆 Best: **{comparison[best_i]['Asset']}** = **{comparison[best_i]['Return']:.1f}%**")

        # ── Expander 3: Risk Analysis ─────────────────────────
        with st.expander("⚠️ Detailed Risk Analysis"):
            if risk_data:
                st.dataframe(pd.DataFrame(risk_data), use_container_width=True, hide_index=True)
                st.success(f"✅ Analysis saved — {rows_saved} records stored")

        # ── Expander 4: Correlation ───────────────────────────
        if len(tickers) > 1:
            with st.expander("🔗 Correlation Heatmap"):
                try:
                    corr     = returns.corr()
                    fig_corr = px.imshow(corr, text_auto=True,
                                         color_continuous_scale='RdBu_r',
                                         title="Asset Correlation Matrix")
                    fig_corr.update_layout(paper_bgcolor='rgba(0,0,0,0)',
                                           font={'color':'white'})
                    st.plotly_chart(fig_corr, use_container_width=True)
                    st.caption("💡 Values near -1 = good diversification | Near +1 = move together")
                except Exception as e:
                    st.warning(f"Correlation: {e}")

        # ── Expander 5: Rebalancing ───────────────────────────
        with st.expander("🔔 Rebalancing Alerts"):
            try:
                vals={t:float(data[t].dropna().iloc[-1]) for t in tickers}
                tv=sum(vals.values()); found=False
                reb_rows = []
                for t,v in vals.items():
                    w=(v/tv)*100
                    status = "🚨 Overweight" if w>40 else ("⚠️ Watch" if w>30 else "✅ OK")
                    reb_rows.append({"Asset":t, "Current Weight":f"{w:.1f}%", "Status":status})
                st.dataframe(pd.DataFrame(reb_rows), use_container_width=True, hide_index=True)
            except Exception as e:
                st.warning(f"Rebalancing: {e}")

        # ── Expander 6: Monte Carlo (Pro) ─────────────────────
        best = None
        with st.expander("🎲 Monte Carlo Simulation" + (" — ⭐ Pro" if not is_pro else "")):
            if is_pro:
                try:
                    mean_r=returns.mean(); cov_m=returns.cov(); n=len(tickers); mcs=[]
                    for _ in range(1000):
                        w=np.random.random(n); w=w/w.sum()
                        ret=float(np.sum(mean_r.values*w)*252)
                        rsk=float(np.sqrt(np.dot(w.T, np.dot(cov_m.values*252,w))))
                        mcs.append({'Return':ret,'Risk':rsk,
                                    'Sharpe':ret/rsk if rsk>0 else 0,'Weights':w})
                    rdf=pd.DataFrame(mcs)
                    best_i=int(rdf['Sharpe'].values.argmax())
                    best=rdf.iloc[best_i]
                    fig_mc=px.scatter(rdf, x='Risk', y='Return', color='Sharpe',
                                      title='1,000 Portfolio Simulations',
                                      color_continuous_scale='Viridis')
                    fig_mc.update_layout(paper_bgcolor='rgba(0,0,0,0)',
                                         plot_bgcolor='rgba(15,17,23,0.8)',
                                         font={'color':'white'})
                    st.plotly_chart(fig_mc, use_container_width=True)
                    mc1,mc2,mc3 = st.columns(3)
                    mc1.metric("📈 Expected Return", f"{best['Return']*100:.1f}%")
                    mc2.metric("📉 Risk",            f"{best['Risk']*100:.1f}%")
                    mc3.metric("⚡ Sharpe",           f"{best['Sharpe']:.2f}")
                    opt=[{"Asset":t,"Optimal Weight":f"{best['Weights'][i]*100:.1f}%"}
                         for i,t in enumerate(tickers)]
                    st.dataframe(pd.DataFrame(opt), use_container_width=True, hide_index=True)
                except Exception as e:
                    st.warning(f"Monte Carlo: {e}")
            else:
                st.warning("⭐ **Pro Feature** — Request upgrade above to unlock Monte Carlo Simulation")

        # ── Expander 7: Investment Allocation (Pro) ───────────
        with st.expander("💰 Investment Allocation" + (" — ⭐ Pro" if not is_pro else "")):
            if is_pro and amount > 0 and best is not None:
                try:
                    alloc=[]; lt=0
                    for i,t in enumerate(tickers):
                        w=float(best['Weights'][i]); money=amount*w
                        price=float(data[t].dropna().iloc[-1]); units=int(money/price)
                        leftover=money-(units*price); lt+=leftover
                        alloc.append({"Asset":t,"Type":asset_types.get(t,'stock').title(),
                                      "Weight":f"{w*100:.1f}%","Amount":f"{money:,.0f}",
                                      "Units":units,"Price/Unit":f"${price:.2f}",
                                      "Leftover":f"{leftover:,.0f}"})
                    st.dataframe(pd.DataFrame(alloc), use_container_width=True, hide_index=True)
                    a1,a2,a3=st.columns(3)
                    a1.metric("💰 Total",    f"{currency} {amount:,}")
                    a2.metric("✅ Invested", f"{amount-lt:,.0f}")
                    a3.metric("🔄 Leftover", f"{lt:,.0f}")
                except Exception as e:
                    st.warning(f"Allocation: {e}")
            elif is_pro and best is None:
                st.info("Run Optimize first to get allocation weights")
            else:
                st.warning("⭐ **Pro Feature** — Request upgrade above to unlock Investment Allocation")

        # ── Expander 8: News Sentiment ────────────────────────
        with st.expander("📰 News Sentiment Analysis"):
            if TEXTBLOB_AVAILABLE:
                scols=st.columns(min(len(tickers),3))
                for idx,t in enumerate(tickers):
                    try:
                        news=yf.Ticker(t).news[:3]
                        scores=[TextBlob(a.get('title','')).sentiment.polarity
                                for a in news if a.get('title','')]
                        if scores:
                            avg=float(np.mean(scores))
                            mood=("😊 Positive" if avg>0.1
                                  else "😟 Negative" if avg<-0.1 else "😐 Neutral")
                            scols[idx%3].metric(t, mood, f"Score: {avg:.2f}")
                    except: pass
            else:
                st.info("Install textblob: pip install textblob")

    # History
    st.divider()
    st.markdown("### 📜 My Analysis History")
    try:
        with get_conn() as conn:
            if is_pro:
                hist = pd.read_sql("""
                    SELECT asset_type AS Type, ticker AS Asset,
                           period AS Period, total_return AS "Return%",
                           sharpe_ratio AS Sharpe, beta AS Beta,
                           analyzed_at AS Date
                    FROM stock_metrics WHERE user_email=?
                    ORDER BY analyzed_at DESC LIMIT 50
                """, conn, params=(user_email,))
            else:
                hist = pd.read_sql("""
                    SELECT ticker AS Asset, period AS Period,
                           total_return AS "Return%", sharpe_ratio AS Sharpe,
                           analyzed_at AS Date
                    FROM stock_metrics WHERE user_email=?
                    ORDER BY analyzed_at DESC LIMIT 10
                """, conn, params=(user_email,))

        if not hist.empty:
            if is_pro and "Type" in hist.columns:
                types = ["All"]+sorted(hist["Type"].dropna().unique().tolist())
                sel   = st.selectbox("Filter", types)
                if sel != "All": hist=hist[hist["Type"]==sel]
            st.dataframe(hist, use_container_width=True, hide_index=True)
            if is_pro:
                st.download_button("📥 Export CSV",
                                   data=hist.to_csv(index=False),
                                   file_name="history.csv", mime="text/csv")
        else:
            st.info("📭 No history yet!")
    except:
        st.info("📭 No history yet!")


# ============================================================
# PART 13: Main Entry Point
# ============================================================
if st.session_state.logged_in:
    if st.session_state.is_admin:
        show_admin_dashboard()
    else:
        show_dashboard()
else:
    show_auth_page()

# ============================================================
# نهاية الكود 🎉
# ============================================================
