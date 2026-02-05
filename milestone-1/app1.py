import streamlit as st
import sqlite3
import json
import io
import hashlib
from PIL import Image, ImageOps
import pandas as pd
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from pdf2image import convert_from_bytes
from datetime import datetime
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
conn.commit()

# ================= CATEGORY CLASSIFIER =================
def classify_category(merchant):
    if not merchant:
        return "Other"

    m = merchant.lower()

    if any(x in m for x in ["grocery", "mart", "supermarket", "basket"]):
        return "Groceries"
    if any(x in m for x in ["hospital", "medical", "pharmacy", "clinic"]):
        return "Medical"
    if any(x in m for x in ["hotel", "restaurant", "cafe", "food"]):
        return "Restaurant"
    if any(x in m for x in ["uber", "ola", "flight", "rail", "travel"]):
        return "Travel"
    if any(x in m for x in ["electricity", "water", "gas", "bill"]):
        return "Utilities"

    return "Other"

# ================= IMAGE PREPROCESSING =================
def preprocess_image(img):
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img)
    return img

# ================= SAFE JSON =================
def safe_json(text):
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except:
        return None

# ================= AI EXTRACTION =================
def analyze_receipt(image, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = """
You are an invoice parsing system.

Return ONLY valid JSON. No explanation.

Extract:
- merchant
- date (YYYY-MM-DD)
- total (number)
- currency
- items (name, price)
- taxes (gst, cgst, sgst, igst, other)
- discount

Rules:
- If a value is not found, return 0
- Prices must be numbers only

JSON FORMAT:
{
  "merchant": "",
  "date": "",
  "total": 0.0,
  "currency": "",
  "items": [
    { "name": "", "price": 0.0 }
  ],
  "taxes": {
    "gst": 0.0,
    "cgst": 0.0,
    "sgst": 0.0,
    "igst": 0.0,
    "other": 0.0
  },
  "discount": 0.0
}
"""


    try:
        response = model.generate_content(
            [prompt, image],
            generation_config={"temperature": 0}
        )
        return safe_json(response.text)
    except ResourceExhausted:
        return None
    except:
        return None

# ================= UI =================
st.title("🧾 LedgerLens AI – Receipt & Invoice Digitizer")
st.caption("AI-powered Expense Categorization & Analytics")

# ================= SIDEBAR =================
st.sidebar.header("🔐 API Access")
api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")

if not api_key:
    st.warning("Please enter Gemini API Key")
    st.stop()

# ================= TABS =================
tab1, tab2, tab3 = st.tabs(["📤 Upload", "🗂 History", "📊 Analytics"])

# ================= TAB 1: UPLOAD =================
with tab1:
    file = st.file_uploader(
        "Upload Receipt / Invoice (JPG, PNG, PDF)",
        type=["jpg", "jpeg", "png", "pdf"]
    )

    if file:
        file_bytes = file.read()
        file_hash = hashlib.md5(file_bytes).hexdigest()

        cursor.execute("SELECT 1 FROM receipts WHERE file_hash=?", (file_hash,))
        if cursor.fetchone():
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
            with st.spinner("Extracting receipt details..."):
                data = analyze_receipt(processed, api_key)

                if not data:
                    st.error("AI extraction failed")
                    st.stop()

                try:
                    total = float(data.get("total", 0))
                except:
                    total = 0.0

                try:
                    date = datetime.fromisoformat(data.get("date")).date().isoformat()
                except:
                    date = None

                merchant = data.get("merchant", "Unknown")
                category = classify_category(merchant)

                cursor.execute("""
                INSERT INTO receipts
                (merchant, date, total, currency, category, raw_json, file_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    merchant,
                    date,
                    total,
                    data.get("currency", ""),
                    category,
                    json.dumps(data),
                    file_hash
                ))
                conn.commit()

                st.success("✅ Receipt saved successfully")

# ================= TAB 2: HISTORY / BILL REGISTER =================
with tab2:
    st.subheader("🗂 Bill Register")

    # Load data
    df = pd.read_sql("""
        SELECT id, merchant, date, category, total, raw_json
        FROM receipts
        ORDER BY id DESC
    """, conn)

    if df.empty:
        st.info("No bills stored yet.")
        st.stop()

    # ---------- DISPLAY TABLE ----------
    table_df = df.copy()
    table_df.insert(0, "S.No", range(1, len(table_df) + 1))

    table_df = table_df.rename(columns={
        "id": "Bill ID",
        "merchant": "Merchant",
        "date": "Date",
        "category": "Category",
        "total": "Total Amount"
    })

    st.dataframe(
        table_df[
            ["S.No", "Bill ID", "Merchant", "Date", "Category", "Total Amount"]
        ],
        use_container_width=True,
        hide_index=True
    )

    # ---------- SELECT BILL ----------
    st.markdown("### 🔍 Bill-wise Amount Validation")

    bill_id = st.selectbox(
        "Select Bill ID",
        table_df["Bill ID"].tolist()
    )

    record = cursor.execute(
        "SELECT merchant, total, raw_json FROM receipts WHERE id=?",
        (bill_id,)
    ).fetchone()

    merchant, bill_total, raw_json = record
    raw = json.loads(raw_json)

    st.markdown(f"**Merchant:** {merchant}")
    st.markdown(f"**Bill Total:** ₹{bill_total:.2f}")

    # ---------- ITEMS ----------
    items = raw.get("items", [])
    if items:
        items_df = pd.DataFrame(items)
        st.markdown("#### 🧾 Line Items")
        st.table(items_df)
        subtotal = sum(float(i.get("price", 0)) for i in items)
    else:
        st.warning("No line items extracted")
        subtotal = 0.0

    # ---------- TAXES ----------
    taxes = raw.get("taxes", {})

    gst = float(taxes.get("gst", 0))
    cgst = float(taxes.get("cgst", 0))
    sgst = float(taxes.get("sgst", 0))
    igst = float(taxes.get("igst", 0))
    other = float(taxes.get("other", 0))

    total_tax = gst + cgst + sgst + igst + other

    # ---------- FALLBACK TAX INFERENCE ----------
    if total_tax == 0 and subtotal > 0:
        inferred_tax = bill_total - subtotal
        if inferred_tax > 0:
            total_tax = inferred_tax
            st.info("ℹ️ Tax inferred from bill total (tax not itemised)")

    # ---------- DISCOUNT ----------
    discount = float(raw.get("discount", 0))

    # ---------- CALCULATION ----------
    calculated_total = subtotal + total_tax - discount

    # ---------- DISPLAY BREAKDOWN ----------
    st.markdown("### 🧮 Amount Breakdown")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Items Subtotal", f"₹{subtotal:.2f}")
        st.metric("Total Tax", f"₹{total_tax:.2f}")
        st.metric("Discount", f"₹{discount:.2f}")

    with col2:
        st.metric("Calculated Total", f"₹{calculated_total:.2f}")
        st.metric("Actual Bill Total", f"₹{bill_total:.2f}")

    # ---------- VALIDATION RESULT ----------
    tolerance = max(2, 0.02 * bill_total)

    if abs(bill_total - calculated_total) <= tolerance:
        st.success("✅ Amount validation PASSED")
    else:
        st.error("❌ Amount validation FAILED")

    # ---------- CLEAR OPTION ----------
    st.divider()
    if st.button("🗑 Clear All Bills"):
        cursor.execute("DELETE FROM receipts")
        conn.commit()
        st.rerun()


# ================= TAB 3: ANALYTICS =================
with tab3:
    df = pd.read_sql(
        "SELECT merchant, date, total, category FROM receipts",
        conn
    )

    if df.empty:
        st.info("No data available yet")
        st.stop()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna()

    # ===== CATEGORY SUMMARY =====
    summary = (
        df.groupby("category")["total"]
        .sum()
        .sort_values(ascending=False)
    )

    st.subheader("📊 Category-wise Spending")
    st.bar_chart(summary)

    st.subheader("🥧 Expense Distribution by Category")
    fig, ax = plt.subplots(figsize=(6, 6))
    summary.plot.pie(
        autopct="%1.1f%%",
        startangle=90,
        ax=ax
    )
    ax.set_ylabel("")
    ax.axis("equal")
    st.pyplot(fig)

    st.subheader("📂 Bills Under Selected Category")
    selected_cat = st.selectbox(
        "Select Category",
        sorted(df["category"].unique())
    )

    filtered = df[df["category"] == selected_cat]
    st.dataframe(
        filtered[["merchant", "date", "total"]],
        use_container_width=True
    )