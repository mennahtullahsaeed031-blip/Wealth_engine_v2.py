# ============================================================
# 📈 Investment & Wealth Engine
# Built by Mennahtullah Saeed
# Version 3.2 — Security, Admin & Password Recovery
# ============================================================
#
# الأدوات المستخدمة:
# Python      → لغة البرمجة
# Streamlit   → الـ App والواجهة
# yfinance    → API الأسهم والـ Crypto
# pandas      → الجداول والبيانات
# numpy       → الحسابات الرياضية
# plotly      → الـ Charts
# SQLite      → قاعدة البيانات
# bcrypt      → تشفير الباسورد (أقوى من SHA-256)
# hashlib     → backup لو bcrypt مش متحملة
# time        → Rate Limiter عشان نحمي الـ API
# random      → عمل الـ Reset Code العشوائي
# TextBlob    → تحليل الأخبار
#
# الإضافات الجديدة في النسخة دي:
# SOL 1 → Rate Limiter: حماية الـ yfinance API من الـ Block
# SOL 2 → bcrypt: تشفير أقوى للباسورد + Salt عشوائي
# SOL 3 → Forgot Password: كود مؤقت لإعادة تعيين الباسورد
# SOL 4 → Admin Mode: صفحة إدارة كاملة
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
# string = مكتبة فيها حروف وأرقام جاهزة
# هنستخدمها عشان نعمل الـ Reset Code العشوائي

from io import BytesIO
from datetime import datetime, date, timedelta
# timedelta = بتتعامل مع فرق الوقت
# مثلاً: "الـ Code صالح 15 دقيقة بس"
warnings.filterwarnings('ignore')

# bcrypt = أقوى مكتبة تشفير
# لو مش متحملة → نرجع لـ hashlib عادي
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
# SOL 4: بيانات الـ Admin ثابتة في الكود
# في الـ Production هتحطيهم في .env file
# بس للـ Demo كده كفاية
ADMIN_EMAIL    = "admin@wealthengine.com"
ADMIN_PASSWORD = "admin2024!"
# غيري الباسورد ده لباسورد قوي خاص بيك ✅


# ============================================================
# PART 2: SOL 1 — Rate Limiter
# ============================================================
# Rate Limiter = "حارس البوابة"
# بيتأكد إن مش بنبعت طلبات كتير أوي لـ yfinance
# في فترة قصيرة جداً

class RateLimiter:
    # class = "قالب" بنعمل منه object
    # زي ما الـ Blueprint بيعمل منه عمارات

    def __init__(self, min_interval=1.0):
        # __init__ = بيشتغل أول ما بنعمل object جديد
        # min_interval = أقل وقت بين طلبين (بالثانية)
        self.min_interval = min_interval
        self.last_called  = {}
        # last_called = dictionary بيحفظ آخر مرة طلبنا كل ticker
        # مثلاً: {"AAPL": 1714000000.5, "MSFT": 1714000001.2}

    def wait_if_needed(self, key):
        # key = اسم الـ ticker اللي هنطلبه
        now  = time.time()
        # time.time() = الوقت الحالي كرقم (Unix timestamp)
        # مثلاً: 1714000000.5 (ثواني من 1970)

        last = self.last_called.get(key, 0)
        # .get(key, 0) = جيب آخر مرة طلبنا الـ key ده
        # لو مش موجود → ارجع 0

        elapsed = now - last
        # elapsed = كام ثانية فات من آخر طلب

        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            time.sleep(sleep_time)
            # time.sleep = وقف الكود للحظة
            # زي ما بتستنى في الطابور قبل ما تتكلم

        self.last_called[key] = time.time()
        # سجل إن احنا طلبنا الـ key ده دلوقتي

# نعمل instance واحد من الـ RateLimiter
# يشتغل على كل الـ App
rate_limiter = RateLimiter(min_interval=0.5)
# 0.5 ثانية بين كل طلب والتاني


# ============================================================
# PART 3: SOL 2 — Password Hashing مع bcrypt
# ============================================================
def hash_password(password):
    # SOL 2: bcrypt أقوى بكتير من SHA-256
    # ليه؟ عشان:
    # 1. بيضيف Salt عشوائي → حتى نفس الباسورد يطلع Hash مختلف
    # 2. بطيء عن قصد → صعب على الهاكر يجرب ملايين باسورد
    if BCRYPT_AVAILABLE:
        salt   = bcrypt.gensalt(rounds=12)
        # gensalt = بيعمل "ملح" عشوائي
        # rounds=12 = كام مرة بيكرر الـ hashing (أعلى = أبطأ = أأمن)
        hashed = bcrypt.hashpw(password.encode(), salt)
        return hashed.decode()
        # .encode() = بيحول النص لـ bytes (الـ bcrypt بيشتغل بـ bytes)
        # .decode() = بيرجعه نص عادي عشان نحفظه في الداتابيز
    else:
        # Fallback: لو bcrypt مش متحملة → SHA-256
        return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password, hashed):
    # بيتحقق إن الباسورد صح
    # مش بنفك التشفير — بنشفر الباسورد الجديد ونقارنه
    if BCRYPT_AVAILABLE:
        try:
            return bcrypt.checkpw(password.encode(), hashed.encode())
            # checkpw = بتشفر الباسورد وتقارنه بالـ Hash
            # بترجع True أو False
        except:
            # Fallback لو الـ hash قديم بـ SHA-256
            return hashed == hashlib.sha256(password.encode()).hexdigest()
    else:
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

        # SOL 3: جدول الـ Reset Codes
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
        # email      = إيميل المستخدم اللي طلب الـ Reset
        # code       = الكود العشوائي المؤقت (6 أرقام)
        # expires_at = امتى الكود ينتهي صلاحيته
        # used       = 0 = لسه مستخدمش | 1 = اتستخدم خلاص

        conn.commit()


# ============================================================
# PART 5: SOL 3 — Forgot Password System
# ============================================================
def generate_reset_code(email):
    # بتعمل كود عشوائي مؤقت وبتحفظه في الداتابيز
    code = ''.join(random.choices(string.digits, k=6))
    # random.choices = بيختار عشوائياً
    # string.digits = "0123456789"
    # k=6 = اختار 6 أرقام
    # النتيجة: مثلاً "847291"

    expires_at = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
    # timedelta(minutes=15) = بعد 15 دقيقة
    # الكود صالح 15 دقيقة بس

    with get_conn() as conn:
        cursor = conn.cursor()

        # شيل أي كود قديم لنفس الإيميل
        cursor.execute("DELETE FROM reset_codes WHERE email = ?", (email,))
        # DELETE = امسح
        # عشان متبقاش كودات قديمة متراكمة

        # حفظ الكود الجديد
        cursor.execute("""
            INSERT INTO reset_codes (email, code, expires_at)
            VALUES (?, ?, ?)
        """, (email.lower(), code, expires_at))
        conn.commit()

    return code


def verify_reset_code(email, code):
    # بتتحقق إن الكود صح وصالح
    with get_conn() as conn:
        cursor = conn.cursor()
        now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            SELECT id FROM reset_codes
            WHERE email     = ?
              AND code      = ?
              AND expires_at > ?
              AND used      = 0
        """, (email.lower(), code, now))
        # expires_at > now = الكود لسه صالح
        # used = 0 = مش اتستخدمش قبل كده

        row = cursor.fetchone()

        if row:
            # علم الكود كـ "اتستخدم"
            cursor.execute("""
                UPDATE reset_codes SET used = 1 WHERE id = ?
            """, (row["id"],))
            conn.commit()
            return True
        return False


def reset_password(email, new_password):
    # بتغير الباسورد في الداتابيز
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET password_hash = ? WHERE email = ?
        """, (hash_password(new_password), email.lower()))
        conn.commit()
        return cursor.rowcount > 0
        # rowcount = كام صف اتغير
        # لو 0 = الإيميل مش موجود


# ============================================================
# PART 6: User Functions
# ============================================================
def register_user(email, password, full_name):
    with get_conn() as conn:            
      cursor = conn.cursor()
      try:
           cursor.execute("""
              INSERT INTO users (email, password_hash, full_name, plan)
    VALUES (?, ?, ?, 'free')
         """, (email.strip().lower(), hash_password(password), full_name.strip()))
        conn.commit()
        return True, "✅ Account created!"
        except sqlite3.IntegrityError:
        return False, "❌ Email already exists!"


def login_user(email, password):
    # SOL 4: تحقق إن المستخدم مش الـ Admin
    # الـ Admin بيدخل بطريقة مختلفة
    if email.strip().lower() == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD:
        return "admin", {
            "id"            : 0,
            "email"         : ADMIN_EMAIL,
            "full_name"     : "Admin",
            "plan"          : "admin",
            "analyses_count": 0,
            "analyses_date" : date.today().isoformat()
        }

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, email, full_name, plan,
                   analyses_count, analyses_date, password_hash
            FROM users WHERE email = ?
        """, (email.strip().lower(),))

        row = cursor.fetchone()
        if not row:
            return False, None

        # SOL 2: استخدام verify_password بدل مقارنة مباشرة
        if not verify_password(password, row["password_hash"]):
            return False, None

        today          = date.today().isoformat()
        analyses_count = row["analyses_count"]

        # Daily Reset
        if row["analyses_date"] != today:
            analyses_count = 0
            cursor.execute("""
                UPDATE users
                SET analyses_count = 0, analyses_date = ?, last_login = ?
                WHERE email = ?
            """, (today, datetime.now().strftime("%Y-%m-%d %H:%M"),
                  email.strip().lower()))
        else:
            cursor.execute("""
                UPDATE users SET last_login = ? WHERE email = ?
            """, (datetime.now().strftime("%Y-%m-%d %H:%M"),
                  email.strip().lower()))

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
    if email == ADMIN_EMAIL:
        return st.session_state.user
    with get_conn() as conn:
        cursor = conn.cursor()
        today  = date.today().isoformat()
        cursor.execute("""
            SELECT id, email, full_name, plan,
                   analyses_count, analyses_date
            FROM users WHERE email = ?
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
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET plan='pro' WHERE email=?", (email,))
        conn.commit()


def downgrade_to_free(email):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET plan='free' WHERE email=?", (email,))
        conn.commit()


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


def save_metrics(risk_data, period, user_email):
    if not user_email: return
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
                    user_email, row["Asset"], period,
                    row.get("Type", "stock").lower(),
                    float(str(row["Return"]).replace("%", "")),
                    float(str(row["Volatility"]).replace("%", "")),
                    float(row["Sharpe Ratio"]), float(row["Beta"]),
                    float(row["Alpha"]),
                    float(str(row["Max Drawdown"]).replace("%", "")),
                    float(str(row["VaR (95%)"]).replace("%", ""))
                ))
            except: pass
        conn.commit()


# ============================================================
# PART 7: SOL 1 — yfinance مع Rate Limiter
# ============================================================
def fetch_data_safe(tickers, period):
    valid_data    = {}
    error_tickers = []

    for ticker in tickers:
        try:
            rate_limiter.wait_if_needed(ticker)
            # SOL 1: استنى لو لازم قبل ما تطلب
            # ده بيمنع الـ Block من Yahoo Finance

            raw = yf.download(ticker, period=period,
                              progress=False, auto_adjust=True)['Close']
            # auto_adjust=True = بيصحح الأسعار تلقائياً
            # مثلاً لو السهم عمل Stock Split

            if isinstance(raw, pd.DataFrame):
                raw = raw.iloc[:, 0]
            raw = raw.squeeze().dropna()

            if len(raw) < 2:
                error_tickers.append(ticker)
                continue

            valid_data[ticker] = raw

        except Exception:
            error_tickers.append(ticker)

    if not valid_data:
        return None, [], error_tickers

    return pd.DataFrame(valid_data), list(valid_data.keys()), error_tickers


# ============================================================
# PART 8: App Setup
# ============================================================
st.set_page_config(
    page_title="Investment & Wealth Engine",
    page_icon="📈",
    layout="wide"
)

init_database()

if "logged_in" not in st.session_state:
    st.session_state.logged_in  = False
    st.session_state.user       = None
    st.session_state.is_admin   = False
    # is_admin = علامة إن المستخدم ده Admin

# Session Refresh من الـ DB
if st.session_state.logged_in and st.session_state.user:
    email_sess = st.session_state.user.get("email", "")
    if email_sess and email_sess != ADMIN_EMAIL:
        fresh = get_user_from_db(email_sess)
        if fresh:
            st.session_state.user = fresh
        else:
            st.session_state.logged_in = False
            st.session_state.user      = None


# ============================================================
# PART 9: Auth Page — Login + Register + Forgot Password
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
        - ✅ Risk Analysis & Benchmark
        - ❌ Monte Carlo
        - ❌ Allocation & Full History

        ---

        **⭐ Pro — $9.99/month**
        - ✅ Unlimited analyses
        - ✅ Monte Carlo Simulation
        - ✅ Investment Allocation
        - ✅ Full History + CSV Export
        """)

    with col_form:
        # SOL 3: أضفنا Tab تالت للـ Forgot Password
        tab_login, tab_register, tab_forgot = st.tabs([
            "🔑 Login",
            "📝 Register",
            "🔓 Forgot Password"
        ])

        # ── Login ─────────────────────────────────────────────
        with tab_login:
            st.markdown("### Welcome Back!")
            email    = st.text_input("Email", key="login_email",
                                     placeholder="your@email.com")
            password = st.text_input("Password", type="password",
                                     key="login_pass")

            if st.button("Login", type="primary", use_container_width=True):
                if not email or not password:
                    st.warning("⚠️ Fill all fields")
                else:
                    result, user = login_user(email, password)

                    if result == "admin":
                        # SOL 4: Admin Login
                        st.session_state.logged_in = True
                        st.session_state.user      = user
                        st.session_state.is_admin  = True
                        st.rerun()

                    elif result:
                        st.session_state.logged_in = True
                        st.session_state.user      = user
                        st.session_state.is_admin  = False
                        st.rerun()

                    else:
                        st.error("❌ Invalid email or password")

        # ── Register ──────────────────────────────────────────
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
                    st.success(msg) if ok else st.error(msg)

        # ── SOL 3: Forgot Password ────────────────────────────
        with tab_forgot:
            st.markdown("### 🔓 Reset Your Password")
            st.caption("Enter your email → get a 6-digit code → set new password")

            fp_email = st.text_input("Your Email", key="fp_email",
                                     placeholder="your@email.com")

            if st.button("Send Reset Code", use_container_width=True):
                if not fp_email or "@" not in fp_email:
                    st.error("❌ Enter a valid email")
                else:
                    # تحقق إن الإيميل موجود في الداتابيز
                    with get_conn() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT id FROM users WHERE email=?",
                            (fp_email.strip().lower(),)
                        )
                        exists = cursor.fetchone()

                    if not exists:
                        # مش بنقول "مش موجود" عشان الأمان
                        # بنقول نفس الرسالة دايماً
                        st.info("📧 If this email exists, a code will appear below.")
                    else:
                        code = generate_reset_code(fp_email.strip().lower())
                        # في الـ Production: هنا هتبعت الـ code بإيميل حقيقي
                        # دلوقتي بنعرضه مباشرة للـ Demo
                        st.success(f"✅ Your reset code: **{code}**")
                        st.caption("⏰ Code valid for 15 minutes only")
                        st.session_state["reset_email"] = fp_email.strip().lower()

            st.divider()
            st.markdown("#### Enter Code & New Password")

            reset_email = st.session_state.get("reset_email", "")
            fp_code     = st.text_input("6-Digit Code", key="fp_code",
                                        max_chars=6, placeholder="123456")
            fp_newpass  = st.text_input("New Password", type="password",
                                        key="fp_new")
            fp_newpass2 = st.text_input("Confirm New Password", type="password",
                                        key="fp_new2")

            if st.button("Reset Password", type="primary", use_container_width=True):
                if not reset_email:
                    st.error("❌ Request a code first")
                elif not fp_code or not fp_newpass:
                    st.warning("⚠️ Fill all fields")
                elif fp_newpass != fp_newpass2:
                    st.error("❌ Passwords don't match")
                elif len(fp_newpass) < 6:
                    st.error("❌ Password must be 6+ characters")
                elif not verify_reset_code(reset_email, fp_code):
                    st.error("❌ Invalid or expired code")
                else:
                    if reset_password(reset_email, fp_newpass):
                        st.success("✅ Password reset! Login with your new password.")
                        del st.session_state["reset_email"]
                    else:
                        st.error("❌ Something went wrong. Try again.")


# ============================================================
# PART 10: SOL 4 — Admin Dashboard
# ============================================================
def show_admin_dashboard():
    st.markdown("# 🔐 Admin Dashboard")
    st.markdown("##### Investment & Wealth Engine — Admin Panel")

    if st.button("Logout", use_container_width=False):
        st.session_state.logged_in = False
        st.session_state.user      = None
        st.session_state.is_admin  = False
        st.rerun()

    st.divider()

    with get_conn() as conn:

        # ── Stats Cards ───────────────────────────────────────
        total_users = pd.read_sql(
            "SELECT COUNT(*) as n FROM users", conn
        ).iloc[0]["n"]

        pro_users = pd.read_sql(
            "SELECT COUNT(*) as n FROM users WHERE plan='pro'", conn
        ).iloc[0]["n"]

        total_analyses = pd.read_sql(
            "SELECT COUNT(*) as n FROM stock_metrics", conn
        ).iloc[0]["n"]

        total_prices = pd.read_sql(
            "SELECT COUNT(*) as n FROM stock_prices", conn
        ).iloc[0]["n"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("👥 Total Users",    total_users)
        c2.metric("⭐ Pro Users",      pro_users)
        c3.metric("📊 Total Analyses", total_analyses)
        c4.metric("💾 Price Records",  total_prices)

        st.divider()

        # ── Users Table ───────────────────────────────────────
        st.markdown("### 👥 All Users")

        users_df = pd.read_sql("""
            SELECT email, full_name, plan,
                   analyses_count AS "Today's Analyses",
                   created_at AS "Joined", last_login AS "Last Login"
            FROM users
            ORDER BY created_at DESC
        """, conn)

        if not users_df.empty:
            st.dataframe(users_df, use_container_width=True, hide_index=True)

            # ── Upgrade / Downgrade ───────────────────────────
            st.markdown("#### ⚙️ Manage User Plan")
            col_em, col_act = st.columns(2)
            with col_em:
                target_email = st.text_input("User Email", key="admin_email",
                                             placeholder="user@email.com")
            with col_act:
                action = st.selectbox("Action", ["Upgrade to Pro", "Downgrade to Free"])

            if st.button("Apply", type="primary"):
                if not target_email:
                    st.warning("Enter email first")
                else:
                    if action == "Upgrade to Pro":
                        upgrade_to_pro(target_email.strip().lower())
                        st.success(f"✅ {target_email} upgraded to Pro!")
                    else:
                        downgrade_to_free(target_email.strip().lower())
                        st.success(f"✅ {target_email} downgraded to Free!")
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
            ORDER BY analyzed_at DESC
            LIMIT 50
        """, conn)

        if not analyses_df.empty:
            # Filter بالمستخدم
            all_users   = ["All"] + sorted(analyses_df["User"].unique().tolist())
            sel_user    = st.selectbox("Filter by User", all_users)
            if sel_user != "All":
                analyses_df = analyses_df[analyses_df["User"] == sel_user]

            st.dataframe(analyses_df, use_container_width=True, hide_index=True)

            # Export
            st.download_button(
                "📥 Export All Analyses CSV",
                data=analyses_df.to_csv(index=False),
                file_name="all_analyses.csv",
                mime="text/csv"
            )
        else:
            st.info("No analyses yet")

        st.divider()

        # ── Reset Codes Monitor ───────────────────────────────
        st.markdown("### 🔓 Password Reset Requests")
        resets_df = pd.read_sql("""
            SELECT email AS User, code AS Code,
                   expires_at AS Expires,
                   CASE used WHEN 1 THEN '✅ Used'
                             ELSE '⏳ Pending' END AS Status,
                   created_at AS Requested
            FROM reset_codes
            ORDER BY created_at DESC
            LIMIT 20
        """, conn)

        if not resets_df.empty:
            st.dataframe(resets_df, use_container_width=True, hide_index=True)
        else:
            st.info("No reset requests yet")


# ============================================================
# PART 11: User Dashboard
# ============================================================
def show_dashboard():
    user       = st.session_state.user
    is_pro     = user["plan"] == "pro"
    user_email = user.get("email", "").strip().lower()

    if not user_email:
        st.error("❌ Session error. Login again.")
        st.session_state.logged_in = False
        st.rerun()
        return

    # Header
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
            st.caption(f"Today: {user['analyses_count']}/3 ({remaining} left)")
            st.caption("🔄 Resets daily at midnight")
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

    # Input
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

    uploaded_file  = st.file_uploader("📎 Upload Excel/CSV",
                                      type=["xlsx","xls","csv"])
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
    with c4: optimize_btn = st.button("⚡ Optimize (Pro)", use_container_width=True, disabled=not is_pro)

    if analyze_btn or optimize_btn:

        fresh = get_user_from_db(user_email)
        if fresh:
            st.session_state.user["analyses_count"] = fresh["analyses_count"]
            user = st.session_state.user

        if not is_pro and user["analyses_count"] >= 3:
            st.error("❌ Daily limit (3/3) reached! Upgrade or try tomorrow.")
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

        with st.spinner("⏳ Fetching data (Rate-limited for stability)..."):

            # SOL 1: Rate Limiter شغال هنا
            data, valid_tickers, error_tickers = fetch_data_safe(tickers, period)

            if error_tickers:
                st.warning(
                    f"⚠️ Could not fetch: **{', '.join(error_tickers)}**\n\n"
                    "Check: symbol spelling | '.CA' for Egypt | "
                    "'-USD' for Crypto | API may be busy (try again)"
                )

            if data is None or not valid_tickers:
                st.error("❌ No valid data. Check symbols.")
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
                u = yf.download("DX-Y.NYB", period=period,
                                progress=False)['Close']
                if isinstance(u, pd.DataFrame): u = u.iloc[:,0]
                if len(u)>1: usd_data = u.squeeze()
            except: pass

            returns    = data.pct_change().dropna()
            rows_saved = save_prices(data, tickers, asset_types)
            increment_analysis(user_email)
            st.session_state.user["analyses_count"] += 1

        st.divider()

        # Asset Summary
        type_emoji = {'stock':'🏢','crypto':'🪙','commodity':'🥇','bond':'📊','egypt':'🇪🇬'}
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("🏢 Stocks",      sum(1 for t in tickers if asset_types.get(t)=='stock'))
        c2.metric("🪙 Crypto",      sum(1 for t in tickers if asset_types.get(t)=='crypto'))
        c3.metric("🥇 Commodities", sum(1 for t in tickers if asset_types.get(t)=='commodity'))
        c4.metric("📊 Bonds",       sum(1 for t in tickers if asset_types.get(t)=='bond'))
        c5.metric("🇪🇬 Egypt",      sum(1 for t in tickers if asset_types.get(t)=='egypt'))

        # Portfolio Overview
        st.markdown("### 📊 Portfolio Overview")
        overview = []
        for ticker in tickers:
            try:
                ret    = ((data[ticker].iloc[-1]/data[ticker].iloc[0])-1)*100
                sharpe = (returns[ticker].mean()*252)/(returns[ticker].std()*np.sqrt(252))
                price  = float(data[ticker].iloc[-1])
                atype  = asset_types.get(ticker,'stock')
                signal = "✅ Strong" if sharpe>1 else ("⚠️ Hold" if sharpe>0 else "🔴 Weak")
                overview.append({
                    "Type": type_emoji.get(atype,'📈'), "Asset": ticker,
                    "Price": f"${price:.2f}", "Return": f"{ret:.1f}%",
                    "Sharpe": f"{sharpe:.2f}", "Signal": signal
                })
            except: pass
        if overview:
            st.dataframe(pd.DataFrame(overview), use_container_width=True, hide_index=True)

        # Normalized Chart
        st.markdown("### 📈 Normalized Performance (Base = 100)")
        try:
            norm = data.div(data.iloc[0])*100
            fig  = px.line(norm, title="All assets start at 100 — shows relative growth")
            fig.update_layout(paper_bgcolor='#0f1117', plot_bgcolor='#1e2130',
                              font={'color':'white'}, hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"Chart error: {e}")

       # Benchmark
        st.markdown("### 🏆 Benchmark vs S&P 500")
        if sp500_data is not None and len(sp500_data)>1:
            try:
                port_ret = float(np.mean([((data[t].iloc[-1]/data[t].iloc[0])-1)*100 for t in tickers]))
                sp_ret   = float(((sp500_data.iloc[-1]/sp500_data.iloc[0])-1)*100)
                diff     = port_ret - sp_ret
                b1,b2,b3 = st.columns(3)
                b1.metric("📊 Your Portfolio", f"{port_ret:.1f}%")
                b2.metric("📈 S&P 500",        f"{sp_ret:.1f}%")
                b3.metric("🎯 vs Benchmark",   f"{diff:.1f}%", delta=f"{diff:.1f}%")
                msg = (f"✅ Beat S&P 500 by **{diff:.1f}%**!" if diff>0
                       else f"⚠️ Underperformed by **{abs(diff):.1f}%**")
                st.success(msg) if diff>0 else st.warning(msg)
                # بدل المتوسط المباشر
# نعمل Normalized لكل سهم الأول وبعدين ناخد المتوسط
                normalized_each = data.div(data.iloc[0]) * 100
# div(data.iloc[0]) = كل سهم يبدأ من 100
# بعدين المتوسط بيبقى منطقي
                norm_p = normalized_each.mean(axis=1)
# دلوقتي المتوسط بين أرقام كلها حوالين 100
# مش بين 180 و 50,000
                norm_sp  = (sp500_data / sp500_data.iloc[0]) * 100

# تأكد إن norm_p مش فاضية
if norm_p.dropna().empty:
    st.warning("Not enough data for benchmark comparison")
else:
    bench_df = pd.DataFrame({
        'Your Portfolio': norm_p,
        'S&P 500'       : norm_sp
    }).dropna()

    if bench_df.empty:
        st.warning("No overlapping dates between portfolio and S&P 500")
    else:
        fig_b = px.line(bench_df, ...)
        st.plotly_chart(fig_b, ...)
        fig_b = px.line(bench_df, title="Portfolio vs S&P 500",
                                color_discrete_map={'Your Portfolio':'#00b4d8','S&P 500':'#f4a261'})
        fig_b.update_layout(paper_bgcolor='#0f1117', plot_bgcolor='#1e2130', font={'color':'white'})
        st.plotly_chart(fig_b, use_container_width=True)
        except Exception as e:
        st.warning(f"Benchmark error: {e}")

        # Comparison Chart
        st.markdown("### 🥇 Multi-Asset Comparison")
        comparison = []
        type_label = {'stock':'Stock','crypto':'Crypto','commodity':'Commodity',
                      'bond':'Bond','egypt':'Egypt'}
        for t in tickers:
            try:
                ret = float(((data[t].iloc[-1]/data[t].iloc[0])-1)*100)
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
                             title=f"Return — {period}", text="Return",
                             color_discrete_map={'Stock':'#00b4d8','Crypto':'#9b5de5',
                                                 'Commodity':'#f4a261','Bond':'#2a9d8f',
                                                 'Currency':'#e9c46a','Index':'#e76f51','Egypt':'#06d6a0'})
            fig_c.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig_c.update_layout(paper_bgcolor='#0f1117', plot_bgcolor='#1e2130', font={'color':'white'})
            st.plotly_chart(fig_c, use_container_width=True)
            best_i = int(np.argmax([c['Return'] for c in comparison]))
            st.info(f"🏆 Best: **{comparison[best_i]['Asset']}** = **{comparison[best_i]['Return']:.1f}%**")

        # Risk Analysis
        st.markdown("### ⚠️ Risk Analysis")
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
                    if len(common)>=2:
                        r_al=r.loc[common]; m_al=mkt.loc[common]
                        beta  = float(r_al.cov(m_al)/m_al.var())
                        alpha = float((r_al.mean()*252)-(m_al.mean()*252))
                risk_data.append({
                    "Type": atype.title(), "Asset": ticker,
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
            st.dataframe(pd.DataFrame(risk_data), use_container_width=True, hide_index=True)
            save_metrics(risk_data, period, user_email)
            st.success(f"✅ Saved {rows_saved} records")

        # Correlation
        if len(tickers)>1:
            st.markdown("### 🔗 Correlation Heatmap")
            try:
                corr     = returns.corr()
                fig_corr = px.imshow(corr, text_auto=True,
                                     color_continuous_scale='RdBu_r',
                                     title="Asset Correlation Matrix")
                fig_corr.update_layout(paper_bgcolor='#0f1117', font={'color':'white'})
                st.plotly_chart(fig_corr, use_container_width=True)
            except Exception as e:
                st.warning(f"Correlation error: {e}")

        # Monte Carlo — Pro Only
        best = None
        if is_pro:
            st.markdown("### 🎲 Monte Carlo Simulation")
            try:
                mean_r=returns.mean(); cov_m=returns.cov(); n=len(tickers); mcs=[]
                for _ in range(1000):
                    w=np.random.random(n); w=w/w.sum()
                    ret=float(np.sum(mean_r.values*w)*252)
                    rsk=float(np.sqrt(np.dot(w.T, np.dot(cov_m.values*252,w))))
                    mcs.append({'Return':ret,'Risk':rsk,'Sharpe':ret/rsk if rsk>0 else 0,'Weights':w})
                rdf=pd.DataFrame(mcs); best_i=int(rdf['Sharpe'].values.argmax()); best=rdf.iloc[best_i]
                fig_mc=px.scatter(rdf,x='Risk',y='Return',color='Sharpe',
                                  title='Monte Carlo: 1,000 Simulations',
                                  color_continuous_scale='Viridis')
                fig_mc.update_layout(paper_bgcolor='#0f1117', plot_bgcolor='#1e2130', font={'color':'white'})
                st.plotly_chart(fig_mc, use_container_width=True)
                opt=[{"Asset":t,"Weight":f"{best['Weights'][i]*100:.1f}%"} for i,t in enumerate(tickers)]
                st.dataframe(pd.DataFrame(opt), use_container_width=True, hide_index=True)
                st.success(f"🏆 Return {best['Return']*100:.1f}% | Risk {best['Risk']*100:.1f}% | Sharpe {best['Sharpe']:.2f}")
            except Exception as e:
                st.warning(f"Monte Carlo error: {e}")
        else:
            st.markdown("### 🎲 Monte Carlo")
            st.warning("⭐ Pro Feature — Upgrade to unlock")

        # Allocation — Pro Only
        if is_pro and amount>0 and best is not None:
            st.markdown(f"### 💰 Allocation — {currency} {amount:,}")
            try:
                alloc=[]; lt=0
                for i,t in enumerate(tickers):
                    w=float(best['Weights'][i]); money=amount*w
                    price=float(data[t].iloc[-1]); units=int(money/price)
                    leftover=money-(units*price); lt+=leftover
                    alloc.append({"Asset":t,"Type":asset_types.get(t,'stock').title(),
                                  "Weight":f"{w*100:.1f}%","Amount":f"{money:,.0f}",
                                  "Units":units,"Price":f"${price:.2f}","Leftover":f"{leftover:,.0f}"})
                st.dataframe(pd.DataFrame(alloc), use_container_width=True, hide_index=True)
                a1,a2,a3=st.columns(3)
                a1.metric("💰 Total",f"{amount:,}")
                a2.metric("✅ Invested",f"{amount-lt:,.0f}")
                a3.metric("🔄 Leftover",f"{lt:,.0f}")
            except Exception as e:
                st.warning(f"Allocation error: {e}")
        elif not is_pro and amount>0:
            st.markdown("### 💰 Allocation")
            st.warning("⭐ Pro Feature — Upgrade to unlock")

        # Rebalancing
        st.markdown("### 🔔 Rebalancing Alerts")
        try:
            vals={t:float(data[t].iloc[-1]) for t in tickers}; tv=sum(vals.values()); found=False
            for t,v in vals.items():
                w=(v/tv)*100
                if w>40:   st.error(f"🚨 **{t}** = {w:.1f}% — exceeds 40%!"); found=True
                elif w>30: st.warning(f"⚠️ **{t}** = {w:.1f}% — concentrated"); found=True
            if not found: st.success("✅ Well-balanced!")
        except Exception as e:
            st.warning(f"Rebalancing error: {e}")

        # Sentiment
        st.markdown("### 📰 News Sentiment")
        if TEXTBLOB_AVAILABLE:
            scols=st.columns(min(len(tickers),3))
            for idx,t in enumerate(tickers):
                try:
                    news=yf.Ticker(t).news[:3]
                    scores=[TextBlob(a.get('title','')).sentiment.polarity for a in news if a.get('title','')]
                    if scores:
                        avg=float(np.mean(scores))
                        mood="😊 Positive" if avg>0.1 else ("😟 Negative" if avg<-0.1 else "😐 Neutral")
                        scols[idx%3].metric(t, mood, f"{avg:.2f}")
                except: pass

        # AI Recommendation
        st.markdown("### 💡 AI Recommendation")
        if risk_data:
            try:
                avg_s=np.mean([float(r["Sharpe Ratio"]) for r in risk_data])
                avg_b=np.mean([float(r["Beta"])         for r in risk_data])
                if avg_s>1 and avg_b<1.2:   st.success(f"✅ **Strong** | Sharpe:{avg_s:.2f} Beta:{avg_b:.2f}")
                elif avg_s>0 and avg_b<1.5: st.warning(f"🟡 **Moderate** | Sharpe:{avg_s:.2f} Beta:{avg_b:.2f}")
                else:                        st.error(f"🔴 **High Risk** | Sharpe:{avg_s:.2f} Beta:{avg_b:.2f}")
            except: pass

    # History
    st.divider()
    st.markdown("### 📜 My Analysis History")
    try:
        with get_conn() as conn:
            if is_pro:
                hist = pd.read_sql("""
                    SELECT asset_type AS Type, ticker AS Asset, period AS Period,
                           total_return AS "Return%", sharpe_ratio AS Sharpe,
                           beta AS Beta, analyzed_at AS Date
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
                types   = ["All"]+sorted(hist["Type"].dropna().unique().tolist())
                sel     = st.selectbox("Filter by Type", types)
                if sel!="All": hist=hist[hist["Type"]==sel]
            st.dataframe(hist, use_container_width=True, hide_index=True)
            if is_pro:
                st.download_button("📥 Export CSV", data=hist.to_csv(index=False),
                                   file_name="my_history.csv", mime="text/csv")
        else:
            st.info("📭 No history yet!")
    except:
        st.info("📭 No history yet!")


# ============================================================
# PART 12: Main Entry Point
# ============================================================
if st.session_state.logged_in:
    if st.session_state.is_admin:
        show_admin_dashboard()   # SOL 4: Admin Dashboard
    else:
        show_dashboard()         # User Dashboard
else:
    show_auth_page()             # Login / Register / Forgot Password
