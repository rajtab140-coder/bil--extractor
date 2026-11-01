import io
import os
import re
import json
import time
import random
import sqlite3
from datetime import datetime, date
from typing import Any

import fitz
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types

# -------------------- APP CONFIG --------------------
st.set_page_config(
    page_title="Nexus Bill Processor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
.stApp { background:#0b1020; color:#edf2ff; }
.block-container { padding-top:1.5rem; max-width:1500px; }
[data-testid="stSidebar"] { background:#111827; border-right:1px solid #263247; }
.hero {background:linear-gradient(120deg,#14233c,#111827);border:1px solid #2b3d5a;
       padding:22px 26px;border-radius:18px;margin-bottom:18px}
.hero h1 {margin:0;color:#eaf3ff;font-size:28px}
.hero p {color:#9fb0ca;margin:7px 0 0}
.metric {background:#141e30;border:1px solid #293850;padding:16px;border-radius:14px}
.metric small {color:#9fb0ca}
.metric h2 {margin:5px 0 0;color:#60c8ff}
div.stButton>button {border-radius:9px;font-weight:700;min-height:42px}
div[data-testid="stFileUploader"] {background:#121c2c;border:1px dashed #49617f;border-radius:12px;padding:12px}
.review-note {background:#382b14;border:1px solid #806124;padding:12px;border-radius:10px;color:#ffdfa0}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>⚡ Nexus Enterprise Billing Hub</h1>
  <p>50-page PDF batches · AI bill extraction · Manual verification · Daily Excel</p>
</div>
""", unsafe_allow_html=True)

# -------------------- CONSTANTS --------------------
FIELDS = [
    "Patient Name", "Age/Sex", "Bill Number", "CR Number",
    "Procedure Name", "Amount", "Date"
]
CATEGORIES = ["X-Ray", "CT Scan", "MRI", "OPG", "USG"]
DB_PATH = os.getenv("NEXUS_DB_PATH", "nexus_jobs.sqlite3")
MODEL_DEFAULT = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
MAX_PDF_MB = int(os.getenv("MAX_PDF_MB", "40"))
MAX_PAGES_PER_PDF = 50

# -------------------- STORAGE --------------------
def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            filename TEXT NOT NULL,
            category TEXT NOT NULL,
            page_count INTEGER NOT NULL,
            rows_json TEXT NOT NULL
        )
        """)
        con.commit()

def save_job(job):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?)",
            (job["job_id"], job["created_at"], job["filename"],
             job["category"], job["page_count"],
             json.dumps(job["rows"], ensure_ascii=False))
        )
        con.commit()

def load_jobs():
    with sqlite3.connect(DB_PATH) as con:
        records = con.execute(
            "SELECT job_id,created_at,filename,category,page_count,rows_json "
            "FROM jobs ORDER BY created_at DESC"
        ).fetchall()
    jobs = []
    for r in records:
        jobs.append({
            "job_id":r[0], "created_at":r[1], "filename":r[2],
            "category":r[3], "page_count":r[4], "rows":json.loads(r[5])
        })
    return jobs

init_db()
if "jobs" not in st.session_state:
    st.session_state.jobs = load_jobs()
if "daily_date" not in st.session_state:
    st.session_state.daily_date = date.today().isoformat()

# -------------------- AI EXTRACTION --------------------
JSON_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "patient_name": {"type":"STRING"},
        "age_sex": {"type":"STRING"},
        "bill_number": {"type":"STRING"},
        "cr_number": {"type":"STRING"},
        "procedure_name": {"type":"STRING"},
        "amount": {"type":"STRING"},
        "date": {"type":"STRING"},
        "confidence": {"type":"NUMBER"},
        "review_reason": {"type":"STRING"}
    },
    "required": [
        "patient_name","age_sex","bill_number","cr_number",
        "procedure_name","amount","date","confidence","review_reason"
    ]
}

def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()

def parse_json_response(txt: str) -> dict:
    txt = txt.strip()
    txt = re.sub(r"^```(?:json)?\s*", "", txt)
    txt = re.sub(r"\s*```$", "", txt)
    return json.loads(txt)

def validate_record(data: dict, page_no: int, filename: str, selected_category: str):
    mapping = {
        "Patient Name":"patient_name",
        "Age/Sex":"age_sex",
        "Bill Number":"bill_number",
        "CR Number":"cr_number",
        "Procedure Name":"procedure_name",
        "Amount":"amount",
        "Date":"date",
    }
    row = {label: normalize_text(data.get(key, "")) for label,key in mapping.items()}
    row["PDF File"] = filename
    row["Page"] = page_no
    row["Selected Category"] = selected_category
    row["AI Confidence"] = data.get("confidence", 0)
    reasons = []
    for field in FIELDS:
        if not row[field]:
            reasons.append(f"{field} missing")
    if row["Amount"]:
        amount_clean = row["Amount"].replace(",", "").replace("₹","").strip()
        try:
            float(amount_clean)
        except Exception:
            reasons.append("Amount needs checking")
    try:
        confidence = float(row["AI Confidence"])
        if confidence < 0 or confidence > 1:
            reasons.append("Confidence value invalid")
        elif confidence < 0.85:
            reasons.append("Low AI confidence")
    except Exception:
        reasons.append("Confidence unavailable")
    if data.get("review_reason"):
        reasons.append(normalize_text(data.get("review_reason")))
    row["Review Reason"] = "; ".join(dict.fromkeys(reasons))
    row["Status"] = "Review" if reasons else "Extracted"
    return row

def extract_page(client, image_bytes, category, filename, page_no, model, max_attempts=5):
    prompt = f"""
You are extracting fields from ONE scanned hospital billing receipt.
The operator selected this bill category: {category}.
Read only what is visibly printed. Do not guess, invent, autocorrect names,
or swap Bill Number with CR Number. Preserve IDs exactly, including leading
zeroes, slashes and hyphens. Amount must be the final total collected, not
a line-item rate. Date should be copied as printed. Procedure Name should
contain the actual printed procedure/body region. If a field is unreadable,
return an empty string and explain in review_reason.
Return confidence from 0 to 1 for the overall extraction. Use 0.5 or lower
if any important field is uncertain.
The PDF page should represent one bill. Do not combine information from
different receipts.
"""
    for attempt in range(max_attempts):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    prompt
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=JSON_SCHEMA,
                    temperature=0
                )
            )
            return parse_json_response(response.text or "{}")
        except Exception as exc:
            msg = str(exc).lower()
            transient = any(x in msg for x in ["429","quota","resource_exhausted",
                                                "503","unavailable","timeout","500"])
            if not transient or attempt == max_attempts - 1:
                raise
            time.sleep(min(30, (2 ** attempt) + random.random() * 2))
    raise RuntimeError("AI extraction failed after retries")

# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.markdown("## ⚙️ Processing settings")
    api_key = st.text_input(
        "Gemini API key", type="password",
        value=os.getenv("GEMINI_API_KEY",""),
        help="Prefer setting GEMINI_API_KEY as a server secret. Do not share this key."
    )
    model = st.text_input("Gemini model", value=MODEL_DEFAULT)
    category = st.selectbox("Bill category in this PDF", CATEGORIES, index=2)
    dpi = st.select_slider("Scan quality", options=[100,110,130,150], value=130)
    delay = st.slider("Delay between AI requests (seconds)", 0.0, 3.0, 0.7, 0.1)
    st.caption("Higher DPI may improve small text but increases processing time and API usage.")
    st.divider()
    st.caption("Database: local SQLite job history. On cloud hosting, use persistent storage or managed database.")

# -------------------- TABS --------------------
tab_upload, tab_jobs, tab_help = st.tabs(["📤 Upload & Process", "📥 Jobs & Daily Excel", "ℹ️ How to use"])

with tab_upload:
    left, right = st.columns([1.2,1])
    with left:
        st.subheader("1. Upload PDF batch")
        st.write("One PDF should contain up to 50 pages, with one bill on each page.")
        uploads = st.file_uploader(
            "Choose one or more PDFs", type=["pdf"],
            accept_multiple_files=True, key="pdf_uploads"
        )
        if uploads:
            st.info(f"{len(uploads)} PDF file(s) selected.")
            for f in uploads:
                st.write(f"• {f.name} — {f.size/1024/1024:.1f} MB")
    with right:
        st.subheader("2. Batch rules")
        st.markdown("""
        - One page = one bill
        - Maximum 50 pages per PDF
        - Choose the matching category
        - Unclear values are marked for review
        - Jobs are added to the daily Excel
        """)
        st.warning("AI can make reading mistakes. Check flagged rows and verify all bill IDs and amounts before official use.")

    can_run = bool(uploads) and bool(api_key.strip())
    start = st.button("⚡ Start batch processing", type="primary", disabled=not can_run, use_container_width=True)

    if start:
        client = genai.Client(api_key=api_key.strip())
        total_pages = 0
        validated_docs = []
        for f in uploads:
            raw = f.getvalue()
            if len(raw) > MAX_PDF_MB * 1024 * 1024:
                st.error(f"{f.name}: exceeds {MAX_PDF_MB} MB limit.")
                continue
            try:
                doc = fitz.open(stream=raw, filetype="pdf")
                if len(doc) == 0:
                    st.error(f"{f.name}: PDF has no pages.")
                    doc.close()
                    continue
                if len(doc) > MAX_PAGES_PER_PDF:
                    st.error(f"{f.name}: {len(doc)} pages found. Split into PDFs of 50 pages or fewer.")
                    doc.close()
                    continue
                validated_docs.append((f.name, raw, len(doc)))
                total_pages += len(doc)
                doc.close()
            except Exception as exc:
                st.error(f"{f.name}: cannot open PDF ({exc}).")

        if not validated_docs:
            st.stop()

        progress = st.progress(0)
        status = st.empty()
        all_rows = []
        done = 0
        started = time.time()
        for filename, raw, page_count in validated_docs:
            try:
                doc = fitz.open(stream=raw, filetype="pdf")
                for idx in range(page_count):
                    done += 1
                    status.info(f"Processing {filename} — page {idx+1}/{page_count} | Overall {done}/{total_pages}")
                    page = doc.load_page(idx)
                    pix = page.get_pixmap(dpi=dpi, alpha=False)
                    img = pix.tobytes("jpeg")
                    del pix
                    try:
                        extracted = extract_page(client, img, category, filename, idx+1, model)
                        row = validate_record(extracted, idx+1, filename, category)
                    except Exception as exc:
                        row = {k:"" for k in FIELDS}
                        row.update({
                            "PDF File":filename, "Page":idx+1,
                            "Selected Category":category,
                            "AI Confidence":0,
                            "Review Reason":f"Extraction/API error: {str(exc)[:250]}",
                            "Status":"Error"
                        })
                    all_rows.append(row)
                    progress.progress(done/total_pages)
                    if delay:
                        time.sleep(delay)
                doc.close()
            except Exception as exc:
                st.error(f"Could not complete {filename}: {exc}")

        if all_rows:
            job_id = "NX-" + datetime.now().strftime("%Y%m%d-%H%M%S")
            job = {
                "job_id":job_id,
                "created_at":datetime.now().isoformat(timespec="seconds"),
                "filename":", ".join(x[0] for x in validated_docs),
                "category":category,
                "page_count":len(all_rows),
                "rows":all_rows
            }
            save_job(job)
            st.session_state.jobs.insert(0,job)
            elapsed = int(time.time()-started)
            st.success(f"Batch saved: {len(all_rows)} pages processed in {elapsed//60}m {elapsed%60}s. Review flagged rows before use.")
            st.dataframe(pd.DataFrame(all_rows), use_container_width=True, hide_index=True)
        status.empty()
        progress.empty()

with tab_jobs:
    st.subheader("Completed jobs")
    jobs = load_jobs()
    st.session_state.jobs = jobs
    if not jobs:
        st.info("No jobs yet. Upload a PDF batch to begin.")
    else:
        for job in jobs:
            review_count = sum(1 for r in job["rows"] if r.get("Status") != "Extracted")
            with st.expander(f"{job['job_id']} · {job['filename']} · {job['page_count']} pages · {job['category']}"):
                st.caption(f"Created: {job['created_at']} | Rows needing review/error: {review_count}")
                edited = st.data_editor(
                    pd.DataFrame(job["rows"]),
                    use_container_width=True,
                    num_rows="fixed",
                    key=f"editor_{job['job_id']}"
                )
                if st.button("Save corrections", key=f"save_{job['job_id']}"):
                    job["rows"] = edited.fillna("").to_dict(orient="records")
                    save_job(job)
                    st.success("Corrections saved.")
                    st.rerun()

    # Daily consolidated export from persisted jobs
    st.divider()
    st.subheader("Daily consolidated Excel")
    selected_day = st.date_input("Select processing date", value=date.today())
    day_jobs = [j for j in jobs if j["created_at"][:10] == selected_day.isoformat()]
    day_rows = [r for j in day_jobs for r in j["rows"]]
    if day_rows:
        df = pd.DataFrame(day_rows)
        review_df = df[df["Status"].isin(["Review","Error"])]
        extracted_df = df[df["Status"] == "Extracted"]
        eligible = df[df["Selected Category"].isin(CATEGORIES)]
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            eligible[FIELDS + ["PDF File","Page","Selected Category","Status","Review Reason"]].to_excel(
                writer, index=False, sheet_name="All Bills"
            )
            extracted_df.to_excel(writer, index=False, sheet_name="Extracted")
            review_df.to_excel(writer, index=False, sheet_name="Needs Review")
            pd.DataFrame([{
                "Date":selected_day.isoformat(),
                "PDF batches":len(day_jobs),
                "Total pages/bills":len(day_rows),
                "Needs review":len(review_df),
                "Extracted":len(extracted_df)
            }]).to_excel(writer,index=False,sheet_name="Summary")
        st.write(f"**{len(day_jobs)} batches · {len(day_rows)} bills · {len(review_df)} need review**")
        st.download_button(
            "⬇️ Download daily Excel workbook",
            data=out.getvalue(),
            file_name=f"Nexus_Daily_Bills_{selected_day.isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
    else:
        st.info("No saved bills for this date.")

with tab_help:
    st.subheader("Daily workflow")
    st.markdown("""
    1. Select the category printed on the bills.
    2. Upload a PDF with up to 50 pages (one receipt per page).
    3. Start processing and wait for the batch to finish.
    4. Open Jobs & Daily Excel and correct rows marked Review or Error.
    5. Download one combined Excel file for the selected date.

    **Important limitations of this starter**
    - It processes pages sequentially. 700 pages can take a while and consume Gemini API quota/cost.
    - SQLite history is suitable for a local pilot. For a public multi-user deployment, move jobs and files to managed persistent storage/database and add user authentication.
    - The API key is entered in the sidebar or supplied as a server environment secret. Never hardcode it in source code or publish it on GitHub.
    - Do not upload identifiable patient bills to a third-party AI service unless your organisation has approved the service, data processing, retention, and access arrangements.
    - OCR/AI is not guaranteed accurate. Independently verify patient identifiers, bill number, CR number, date, and amount before submitting the Excel officially.
    """)
