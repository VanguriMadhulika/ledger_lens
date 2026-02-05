# 🧾 LedgerLens AI  
**AI-Powered Receipt & Invoice Digitizer**

LedgerLens AI is an intelligent expense management system that digitizes receipts and invoices using AI. It extracts key financial details, stores them securely, and provides analytics to help users understand their spending patterns.

---

## 🚀 Project Overview
Managing receipts manually is time-consuming and error-prone. LedgerLens AI automates this process by:
- Extracting structured data from receipts/invoices
- Storing records persistently
- Providing insights through analytics dashboards

The project is developed in **milestones** to demonstrate progressive enhancement and feature expansion.

---

## 🧩 Tech Stack
- **Python**
- **Streamlit** – Frontend UI
- **Google Gemini API** – AI-based text extraction
- **SQLite** – Local database
- **OCR & Image Processing** (PIL / OpenCV)
- **Regex & NLP** – Data validation and parsing
- **Matplotlib / Pandas** – Analytics & visualization

---

## 📁 Repository Structure
ledger_lens/
│
├── milestone-1/
│ ├── app1.py
│ ├── README.md
│ ├── requirements.txt
│ └── project documents
│
├── milestone-2/
│ ├── app2.py
│ ├── README.md
│ ├── requirements.txt
│ └── enhanced features & analytics
│
├── .gitignore
└── requirements.txt


---

## 🏁 Milestones

### 🔹 Milestone 1 – Basic Receipt Digitization
- Upload receipt images (JPG, PNG, PDF)
- AI-based extraction of:
  - Merchant name
  - Date
  - Total amount
- Store extracted data in SQLite
- Simple Streamlit UI


---

### 🔹 Milestone 2 – Enhanced Parsing & Analytics
- Improved accuracy using Regex & NLP
- Multi-format and multi-page PDF support
- Expense history tracking
- Analytics dashboard:
  - Spending by merchant
  - Category-wise insights
- Secure API key handling



---

