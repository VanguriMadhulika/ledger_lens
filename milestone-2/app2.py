import streamlit as st
import sqlite3
import json
import io
import hashlib
from PIL import Image, ImageOps
import pandas as pd
import google.generativeai as genai
from pdf2image import convert_from_bytes
import matplotlib.pyplot as plt

# ================= PAGE CONFIG =================
st.set_page_config(
    page_title="LedgerLens AI",
    page_icon="🧾",
    layout="wide"
)

# ================= DATABASE =================
conn = sqlite3.connect("receipts.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant TEXT,
    date TEXT,
    total REAL,
    currency TEXT,
    category TEXT,
    raw_json TEXT,
    file_hash TEXT UNIQUE
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS bill_validation (
    bill_id INTEGER PRIMARY KEY,
    total REAL,
    calculated_total REAL,
    status TEXT
)
""")
conn.commit()

# ================= HELPERS =================
def safe_float(val):
    try:
        return float(val)
    except:
        return 0.0

def classify_category(merchant):
    if not merchant:
        return "Other"
    m = merchant.lower()
    if any(x in m for x in ["grocery", "mart", "supermarket"]):
        return "Groceries"
    if any(x in m for x in ["hospital", "medical", "pharmacy"]):
        return "Medical"
    if any(x in m for x in ["restaurant", "cafe", "food"]):
        return "Restaurant"
    if any(x in m for x in ["uber", "ola", "flight", "rail"]):
        return "Travel"
    if any(x in m for x in ["electricity", "water", "gas"]):
        return "Utilities"
    return "Other"

def index_status(value):
    return "✅ Indexed" if value not in [None, "", "Unknown"] else "❌ Missing"

def preprocess_image(img):
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img)
    return img

def safe_json(text):
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except:
        return {}

# ================= AI EXTRACTION =================
def analyze_receipt(image, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = """
Return ONLY valid JSON.

Extract:
merchant, date (YYYY-MM-DD), total, currency,
items(name, price),
taxes(gst,cgst,sgst,igst,other),
discount
"""
    try:
        response = model.generate_content(
            [prompt, image],
            generation_config={"temperature": 0}
        )
        return safe_json(response.text)
    except:
        return {}

# ================= UI =================
st.title("🧾 LedgerLens AI – Receipt & Invoice Digitizer")
st.caption("AI-powered Expense Categorization & Analytics")

st.sidebar.header("🔐 API Access")
api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
if not api_key:
    st.stop()

tab1, tab2, tab3, tab4 = st.tabs(
    ["📤 Upload", "🗂 History", "📊 Analytics", "📈 Index Performance"]
)

# ================= TAB 1: UPLOAD =================
with tab1:
    file = st.file_uploader(
        "Upload Receipt / Invoice",
        type=["jpg", "jpeg", "png", "pdf"]
    )

    if file:
        file_bytes = file.read()
        file_hash = hashlib.md5(file_bytes).hexdigest()

        if cursor.execute(
            "SELECT 1 FROM receipts WHERE file_hash=?",
            (file_hash,)
        ).fetchone():
            st.error("⚠️ Duplicate receipt detected")
            st.stop()

        if file.type == "application/pdf":
            image = convert_from_bytes(file_bytes)[0]
        else:
            image = Image.open(io.BytesIO(file_bytes))

        processed = preprocess_image(image)

        c1, c2 = st.columns(2)
        c1.image(image, caption="Original", width=350)
        c2.image(processed, caption="Processed", width=350)

        if st.button("🔍 Analyze & Save"):
            data = analyze_receipt(processed, api_key)

            merchant = data.get("merchant", "Unknown")
            category = classify_category(merchant)

            cursor.execute("""
            INSERT INTO receipts
            (merchant, date, total, currency, category, raw_json, file_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                merchant,
                data.get("date"),
                safe_float(data.get("total")),
                data.get("currency", ""),
                category,
                json.dumps(data),
                file_hash
            ))
            conn.commit()
            st.success("✅ Receipt saved successfully")

# ================= TAB 2: HISTORY =================
with tab2:
    st.subheader("🗂 Bill Register")

    df = pd.read_sql("""
        SELECT id, merchant, date, category, total, raw_json
        FROM receipts
        ORDER BY id DESC
    """, conn)

    if df.empty:
        st.info("No bills stored yet.")
        st.stop()

    st.dataframe(df[["id", "merchant", "date", "category", "total"]])

    selected_cat = st.selectbox(
        "Filter by Category",
        ["All"] + sorted(df["category"].unique()),
        key="history_category"
    )

    if selected_cat != "All":
        df = df[df["category"] == selected_cat]

    if df.empty:
        st.warning("No bills for selected category.")
        st.stop()

    bill_id = st.selectbox(
        "Select Bill ID",
        df["id"].tolist(),
        key="history_bill"
    )

    row = cursor.execute(
        "SELECT total, raw_json FROM receipts WHERE id=?",
        (bill_id,)
    ).fetchone()

    if row is None:
        st.error("Bill not found.")
        st.stop()

    bill_total, raw_json = row
    bill_total = safe_float(bill_total)
    raw = json.loads(raw_json) if raw_json else {}

    st.markdown("### 🧾 Line Items")
    items = raw.get("items", [])
    st.table(pd.DataFrame(items))

    subtotal = sum(safe_float(i.get("price")) for i in items)
    taxes = raw.get("taxes", {})
    total_tax = sum(safe_float(v) for v in taxes.values())
    discount = safe_float(raw.get("discount"))

    calculated_total = subtotal + total_tax - discount
    tolerance = max(2, 0.02 * bill_total)

    status = "PASSED" if abs(bill_total - calculated_total) <= tolerance else "FAILED"

    cursor.execute("""
    INSERT OR REPLACE INTO bill_validation
    VALUES (?, ?, ?, ?)
    """, (bill_id, bill_total, calculated_total, status))
    conn.commit()

    st.markdown("### ✅ Validation Summary")
    val_df = pd.read_sql("SELECT * FROM bill_validation", conn)
    def color_status(val):
        if val == "PASSED":
            return "color: green; font-weight: bold"
        elif val == "FAILED":
            return "color: red; font-weight: bold"
        return ""

    st.dataframe(
        val_df.style.applymap(color_status, subset=["status"]),
        use_container_width=True
)

# ================= TAB 3: ANALYTICS =================
with tab3:
    df = pd.read_sql(
        "SELECT date, total, category FROM receipts",
        conn
    )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna()

    summary = df.groupby("category")["total"].sum()
    st.bar_chart(summary)

    fig, ax = plt.subplots()
    summary.plot.pie(autopct="%1.1f%%", ax=ax)
    st.pyplot(fig)
    

# ================= TAB 4: INDEX PERFORMANCE =================
with tab4:
    df = pd.read_sql(
        "SELECT id, merchant, date FROM receipts",
        conn
    )

    if df.empty:
        st.info("No bills available.")
        st.stop()

    bill_id = st.selectbox(
        "Select Bill ID",
        df["id"].tolist(),
        key="index_bill"
    )

    bill = df[df["id"] == bill_id].iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Invoice #", index_status(bill["id"]))
    c2.metric("Date", index_status(bill["date"]))
    c3.metric("Vendor", index_status(bill["merchant"]))
