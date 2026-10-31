import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
import fitz # PyMuPDF
import json
import io
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(
    page_title="Nexus Billing AI | Enterprise",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- MODERN ENTERPRISE CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    * { font-family: 'Plus Jakarta Sans', sans-serif; }
    
    .stApp {
        background-color: #0d1117;
        color: #e6edf3;
    }
    
    .top-nav {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 24px;
        background: rgba(22, 27, 34, 0.8);
        backdrop-filter: blur(12px);
        border-bottom: 1px solid #30363d;
        border-radius: 12px;
        margin-bottom: 24px;
    }
    
    .logo-container {
        display: flex;
        align-items: center;
        gap: 12px;
        font-weight: 700;
        font-size: 1.2rem;
        color: #58a6ff;
    }
    
    .glass-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        margin-bottom: 20px;
    }
    
    .metric-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        background: #1f6feb22;
        color: #58a6ff;
        border: 1px solid #1f6feb44;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        border-radius: 10px;
        padding: 0 20px;
        background: #21262d;
        color: #8b949e;
        border: 1px solid #30363d;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background: #1f6feb !important;
        color: #ffffff !important;
        border: 1px solid #388bfd !important;
    }

    .stButton>button {
        background: linear-gradient(135deg, #238636, #2ea043);
        color: white;
        border: 1px solid #3fb950;
        border-radius: 10px;
        font-weight: 600;
        padding: 10px 24px;
        box-shadow: 0 4px 12px rgba(46, 160, 67, 0.25);
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 18px rgba(46, 160, 67, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# --- AUTHENTICATION ---
APP_PASSWORD = "raj123"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
        st.markdown("""
        <div class='glass-card' style='text-align: center;'>
            <h2 style='color:#58a6ff; margin-bottom: 8px;'>⚡ Nexus Intelligence</h2>
            <p style='color:#8b949e; font-size: 0.9rem;'>Enterprise Hospital Bill OCR & Pipeline Processor</p>
        </div>
        """, unsafe_allow_html=True)
        pwd = st.text_input("Security Access Key / Password", type="password")
        if st.button("Unlock Dashboard", use_container_width=True):
            if pwd == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Access Denied: Invalid Security Key")
    st.stop()

# --- SESSION STATE INITIALIZATION ---
if "jobs_history" not in st.session_state:
    st.session_state.jobs_history = []
if "active_data" not in st.session_state:
    st.session_state.active_data = None

# --- TOP NAVIGATION BAR ---
st.markdown("""
<div class='top-nav'>
    <div class='logo-container'>
        <span style='font-size: 1.5rem;'>⚡</span>
        <span>Nexus Billing <span style='font-size: 0.8rem; background: #238636; padding: 2px 8px; border-radius: 6px; color: white;'>PRO 3.8</span></span>
    </div>
    <div style='display:flex; gap:16px; align-items:center;'>
        <span class='metric-badge'>🟢 Gemini Engine: 3.8 Flash</span>
        <span class='metric-badge'>🛡️ Rate-Limit Shield: Active</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Sidebar Settings
with st.sidebar:
    st.markdown("### ⚙️ Engine Parameters")
    api_key = st.text_input("Gemini API Key", type="password", help="Personal AI Studio API Key")
    st.markdown("---")
    st.markdown("**Processing Metrics**")
    st.caption("Paced Concurrency: 2 Parallel Threads")
    st.caption("Buffer Resolution: 120 DPI")
    st.caption("Engine: gemini-3.8-flash")
    if st.button("Logout Session"):
        st.session_state.authenticated = False
        st.rerun()

# --- MAIN DASHBOARD TABS ---
nav_tab1, nav_tab2 = st.tabs(["🚀 Ingestion & Processing Hub", "📦 Downloads & Job History"])

# Parallel Worker with Automatic Rate-Limit Retry
def process_single_page(client, img_bytes, prompt, label):
    for attempt in range(4):
        try:
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type='image/jpeg'),
                    prompt
                ]
            )
            raw = response.text.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            return json.loads(raw)
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "resource" in err_str:
                time.sleep(2 + (attempt * 2.5))
                continue
            time.sleep(1)
            
    return {
        "Patient Name": f"Verification Required: {label}",
        "Age/Sex": "-",
        "Bill Number": "-",
        "CR Number": "-",
        "Procedure Name": "-",
        "Amount": "-",
        "Date": "-"
    }

# ================= TAB 1: UPLOAD & PROCESS =================
with nav_tab1:
    col_left, col_right = st.columns([1, 1], gap="large")
    
    with col_left:
        st.markdown("#### 1. Select Modality")
        modality = st.radio(
            "Modality Category",
            ["X-Ray", "CT Scan", "MRI", "OPG", "USG"],
            horizontal=True,
            label_visibility="collapsed"
        )
        
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        st.markdown("#### 2. AI Processing Engine")
        ai_engine = st.selectbox(
            "AI Engine Selection",
            ["Gemini 3.8 Flash (Auto-Rate Protected & High Speed)", "Precision OCR Engine"],
            label_visibility="collapsed"
        )
        
    with col_right:
        st.markdown("#### 3. Upload Hospital PDF Bills")
        uploaded_files = st.file_uploader(
            "Drop PDF Bills here",
            type=["pdf"],
            accept_multiple_files=True,
            help="Upload single or multiple batch PDFs (e.g. 50 pages)"
        )

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
    
    if uploaded_files:
        c1, c2 = st.columns([3, 1])
        with c1:
            st.info(f"📁 {len(uploaded_files)} PDF File(s) ready for extraction under **{modality}**")
        with c2:
            start_process = st.button("⚡ Start Safe Processing", use_container_width=True)
            
        if start_process:
            if not api_key:
                st.error("Sidebar me apni Gemini API Key enter karein pehle.")
            else:
                client = genai.Client(api_key=api_key.strip())
                all_tasks = []
                
                with st.spinner("Extracting PDF Pages..."):
                    for file in uploaded_files:
                        pdf_data = file.read()
                        try:
                            doc = fitz.open(stream=pdf_data, filetype="pdf")
                            for pno in range(len(doc)):
                                pix = doc.load_page(pno).get_pixmap(dpi=120)
                                all_tasks.append((pix.tobytes("jpeg"), f"{file.name} (P{pno+1})"))
                        except Exception as e:
                            st.error(f"Cannot read {file.name}: {e}")

                total_bills = len(all_tasks)
                prompt = f"""
                You are a hospital OPD billing receipt extractor for '{modality}'.
                Extract strictly the following JSON object:
                {{
                   "Patient Name": "Full Name",
                   "Age/Sex": "Age and Sex (e.g. 29 YR/FEMALE)",
                   "Bill Number": "Bill number",
                   "CR Number": "CR number",
                   "Procedure Name": "Standardize to '{modality}' with region examined (e.g. '{modality} Chest PA')",
                   "Amount": "Total amount in numbers (e.g. 2125.00)",
                   "Date": "Date of transaction"
                }}
                Return ONLY valid JSON without markdown tags.
                """

                progress_bar = st.progress(0)
                status = st.empty()
                status.info(f"Processing {total_bills} bills via Gemini 3.8 (Smooth Protected Execution)...")

                records = []
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [
                        executor.submit(process_single_page, client, task[0], prompt, task[1])
                        for task in all_tasks
                    ]
                    for idx, future in enumerate(futures):
                        records.append(future.result())
                        progress_bar.progress((idx + 1) / total_bills)
                        time.sleep(0.3)

                status.empty()
                progress_bar.empty()

                columns = ["Patient Name", "Age/Sex", "Bill Number", "CR Number", "Procedure Name", "Amount", "Date"]
                df_result = pd.DataFrame(records)
                for c in columns:
                    if c not in df_result.columns:
                        df_result[c] = "-"
                df_result = df_result[columns]
                
                st.session_state.active_data = df_result
                
                job_id = f"JOB-{len(st.session_state.jobs_history)+1:03d}"
                st.session_state.jobs_history.insert(0, {
                    "id": job_id,
                    "date": datetime.now().strftime("%d-%b %H:%M"),
                    "type": modality,
                    "count": total_bills,
                    "data": df_result
                })
                st.success(f"Successfully processed {total_bills} bills!")

    # Live Verifier Table
    if st.session_state.active_data is not None:
        st.markdown("---")
        st.markdown("### ✏️ Interactive Data Verification Grid")
        st.caption("Double-click any box to correct errors before final download.")
        
        edited_df = st.data_editor(
            st.session_state.active_data,
            use_container_width=True,
            num_rows="dynamic"
        )
        
        col_d1, col_d2 = st.columns([1, 3])
        with col_d1:
            excel_buf = io.BytesIO()
            with pd.ExcelWriter(excel_buf, engine='openpyxl') as writer:
                edited_df.to_excel(writer, index=False, sheet_name=modality)
                
            st.download_button(
                label=f"📥 Download {modality} Excel Sheet (.xlsx)",
                data=excel_buf.getvalue(),
                file_name=f"{modality}_Verified_Summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

# ================= TAB 2: DOWNLOADS & JOB HISTORY =================
with nav_tab2:
    st.markdown("### 📦 Processing Jobs & Export Registry")
    
    if not st.session_state.jobs_history:
        st.info("No processing jobs in this session yet. Upload and extract bills to see records here.")
    else:
        for job in st.session_state.jobs_history:
            st.markdown(f"""
            <div style='background:#161b22; border:1px solid #30363d; border-radius:10px; padding:16px; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center;'>
                <div>
                    <span style='color:#58a6ff; font-weight:700; margin-right:12px;'>{job['id']}</span>
                    <span style='background:#23863622; color:#3fb950; border:1px solid #238636; padding:2px 8px; border-radius:4px; font-size:0.8rem; margin-right:12px;'>Completed</span>
                    <span style='color:#e6edf3; font-weight:600;'>{job['type']} Bills</span>
                    <span style='color:#8b949e; font-size:0.85rem; margin-left:12px;'>({job['count']} pages extracted • {job['date']})</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            c_btn1, c_btn2 = st.columns([1, 5])
            with c_btn1:
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                    job['data'].to_excel(writer, index=False, sheet_name=job['type'])
                st.download_button(
                    label=f"⬇️ Download Excel",
                    data=buf.getvalue(),
                    file_name=f"{job['id']}_{job['type']}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_{job['id']}"
                )

