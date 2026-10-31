import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
import fitz # PyMuPDF
import json
import io
import time
from datetime import datetime

st.set_page_config(
    page_title="Nexus Enterprise Billing Hub",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- MODERN ULTRA-CLEAN UI ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    * { font-family: 'Plus Jakarta Sans', sans-serif; }
    
    .stApp {
        background-color: #0b0f17;
        color: #f0f6fc;
    }
    
    /* Top Bar */
    .top-nav {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 14px 24px;
        background: #161b26;
        border: 1px solid #232c3d;
        border-radius: 12px;
        margin-bottom: 24px;
    }
    
    .logo-box {
        display: flex;
        align-items: center;
        gap: 10px;
        font-weight: 800;
        font-size: 1.25rem;
        color: #38bdf8;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        border-bottom: 1px solid #232c3d;
        padding-bottom: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 44px;
        border-radius: 8px;
        padding: 0 24px;
        background: #161b26;
        color: #94a3b8;
        border: 1px solid #232c3d;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background: #2563eb !important;
        color: #ffffff !important;
        border: 1px solid #3b82f6 !important;
    }

    /* Cards */
    .job-card {
        background: #141a24;
        border: 1px solid #232c3d;
        border-radius: 12px;
        padding: 18px 20px;
        margin-bottom: 14px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    .badge-completed {
        background: rgba(34, 197, 94, 0.15);
        color: #4ade80;
        border: 1px solid rgba(34, 197, 94, 0.3);
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 700;
    }
    
    .badge-processing {
        background: rgba(234, 179, 8, 0.15);
        color: #facc15;
        border: 1px solid rgba(234, 179, 8, 0.3);
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 700;
    }

    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# --- AUTHENTICATION ---
APP_PASSWORD = "raj123"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 1.8, 1])
    with col2:
        st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
        st.markdown("""
        <div style='background: #161b26; border: 1px solid #232c3d; border-radius: 16px; padding: 32px; text-align: center;'>
            <h2 style='color:#38bdf8; margin-bottom: 6px;'>⚡ Nexus Pro Engine</h2>
            <p style='color:#94a3b8; font-size: 0.9rem;'>Industrial Hospital Bill Batch Pipeline</p>
        </div>
        """, unsafe_allow_html=True)
        pwd = st.text_input("Enter Dashboard Passkey:", type="password")
        if st.button("Authenticate System", use_container_width=True):
            if pwd == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Access Denied: Invalid Security Passkey")
    st.stop()

# --- STATE STORAGE ---
if "jobs_list" not in st.session_state:
    st.session_state.jobs_list = []
if "inspect_job" not in st.session_state:
    st.session_state.inspect_job = None

# Top Nav
st.markdown("""
<div class='top-nav'>
    <div class='logo-box'>
        <span>⚡ Nexus OCR Engine</span>
        <span style='font-size: 0.75rem; background: #0284c7; color: white; padding: 2px 8px; border-radius: 4px;'>V3.8 BATCH</span>
    </div>
    <div style='display: flex; gap: 12px; font-size: 0.85rem; color: #94a3b8;'>
        <span>🟢 Engine: <b>gemini-3.8-flash</b></span>
        <span>🛡️ Quota Safety: <b>Active</b></span>
    </div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🔑 Engine Authentication")
    api_key = st.text_input("Gemini API Key:", type="password", help="Personal AI Studio API Key")
    st.markdown("---")
    st.caption("Auto-pacing: Active (Prevents API 429 block)")
    st.caption("Memory Guard: Dynamic Page Stream")
    if st.button("Logout"):
        st.session_state.authenticated = False
        st.rerun()

main_tab1, main_tab2 = st.tabs(["📤 Upload & Run Pipeline", "📥 Downloads & Batch Jobs"])

# Core Gemini Extraction with Rate Limiter
def extract_single_receipt(client, img_bytes, modality_type, label):
    prompt = f"""
    Extract data from this hospital OPD bill strictly for modality: '{modality_type}'.
    Return raw JSON with exactly these keys:
    {{
       "Patient Name": "Full Name",
       "Age/Sex": "e.g. 29 YR/FEMALE",
       "Bill Number": "Bill No",
       "CR Number": "CR No",
       "Procedure Name": "{modality_type} with examined body region",
       "Amount": "Total collected numeric amount",
       "Date": "Receipt Date"
    }}
    Do not include markdown blocks or extra text.
    """
    for attempt in range(4):
        try:
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type='image/jpeg'),
                    prompt
                ]
            )
            txt = response.text.strip()
            if "```json" in txt:
                txt = txt.split("```json")[1].split("```")[0].strip()
            elif "```" in txt:
                txt = txt.split("```")[1].split("```")[0].strip()
            return json.loads(txt)
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "quota" in err or "resource" in err:
                time.sleep(3 + attempt * 2)
                continue
            time.sleep(1)
            
    return {
        "Patient Name": f"Check: {label}",
        "Age/Sex": "-",
        "Bill Number": "-",
        "CR Number": "-",
        "Procedure Name": "-",
        "Amount": "-",
        "Date": "-"
    }

# ================= TAB 1: UPLOAD & PROCESS =================
with main_tab1:
    c_left, c_right = st.columns([1, 1], gap="large")
    with c_left:
        st.markdown("#### 1. Select Bill Modality")
        modality = st.radio(
            "Modality",
            ["X-Ray", "CT Scan", "MRI", "OPG", "USG"],
            horizontal=True,
            label_visibility="collapsed"
        )
        
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        st.markdown("#### 2. AI Model Execution")
        st.selectbox(
            "Model",
            ["Gemini 3.8 Flash (High-Throughput Batch Engine)"],
            label_visibility="collapsed"
        )
        
    with c_right:
        st.markdown("#### 3. Upload Hospital Bills (Bulk PDF)")
        uploaded_files = st.file_uploader(
            "Select PDFs (e.g. 50 bills / 20MB file)",
            type=["pdf"],
            accept_multiple_files=True
        )

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
    
    if uploaded_files:
        col_run1, col_run2 = st.columns([3, 1])
        with col_run1:
            st.info(f"📁 **{len(uploaded_files)} file(s)** ready for batch execution under **{modality}**")
        with col_run2:
            trigger = st.button("⚡ Start High-Volume Batch", use_container_width=True)

        if trigger:
            if not api_key:
                st.error("Pehle sidebar me Gemini API Key enter karein!")
            else:
                client = genai.Client(api_key=api_key.strip())
                start_time = time.time()
                
                # Pre-calculate total pages
                total_pages = 0
                for f in uploaded_files:
                    doc_temp = fitz.open(stream=f.read(), filetype="pdf")
                    total_pages += len(doc_temp)
                    f.seek(0)
                    doc_temp.close()

                progress_slot = st.empty()
                status_slot = st.empty()
                prog_bar = progress_slot.progress(0)
                
                extracted_data = []
                page_counter = 0

                # Single-page sequential stream (Zero memory leak, zero timeout crash)
                for f in uploaded_files:
                    doc = fitz.open(stream=f.read(), filetype="pdf")
                    for pno in range(len(doc)):
                        page_counter += 1
                        elapsed = int(time.time() - start_time)
                        status_slot.markdown(
                            f"⏳ **Processing Page {page_counter}/{total_pages}** ({f.name}) • Elapsed Time: `{elapsed}s`"
                        )
                        
                        page = doc.load_page(pno)
                        pix = page.get_pixmap(dpi=110)
                        img_bytes = pix.tobytes("jpeg")
                        pix = None # Free RAM
                        
                        rec = extract_single_receipt(client, img_bytes, modality, f"{f.name} P{pno+1}")
                        extracted_data.append(rec)
                        
                        prog_bar.progress(page_counter / total_pages)
                        time.sleep(0.4) # Google API standard rate window
                        
                    doc.close()

                prog_bar.empty()
                progress_slot.empty()
                status_slot.empty()
                
                duration_sec = int(time.time() - start_time)
                mins = duration_sec // 60
                secs = duration_sec % 60
                time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

                columns_order = ["Patient Name", "Age/Sex", "Bill Number", "CR Number", "Procedure Name", "Amount", "Date"]
                df_out = pd.DataFrame(extracted_data)
                for col in columns_order:
                    if col not in df_out.columns:
                        df_out[col] = "-"
                df_out = df_out[columns_order]

                # Store into Job History
                job_id = f"JOB-{len(st.session_state.jobs_list)+1:03d}"
                st.session_state.jobs_list.insert(0, {
                    "id": job_id,
                    "file_name": uploaded_files[0].name if len(uploaded_files) == 1 else f"{len(uploaded_files)} PDF Files",
                    "date": datetime.now().strftime("%d %b %H:%M"),
                    "modality": modality,
                    "pages": f"{total_pages}/{total_pages}",
                    "time_taken": time_str,
                    "data": df_out
                })
                st.success(f"✅ Batch {job_id} Completed: {total_pages} bills processed in {time_str}!")
                st.session_state.inspect_job = job_id

# ================= TAB 2: DOWNLOADS & JOBS REGISTRY =================
with main_tab2:
    st.markdown("### 📥 Completed Processing Jobs")
    
    if not st.session_state.jobs_list:
        st.info("No processing jobs found. Run a batch from the upload tab.")
    else:
        for job in st.session_state.jobs_list:
            c_info, c_action = st.columns([3, 2])
            
            with c_info:
                st.markdown(f"""
                <div style='padding: 8px 0;'>
                    <b style='color:#38bdf8; font-size:1.05rem;'>{job['id']}</b> • 
                    <span class='badge-completed'>Completed</span> • 
                    <b style='color:#f8fafc;'>{job['file_name']}</b>
                    <div style='color:#94a3b8; font-size:0.85rem; margin-top:4px;'>
                        Category: <b>{job['modality']}</b> | Progress: <b>{job['pages']} pages</b> | Duration: <b>{job['time_taken']}</b> | Time: {job['date']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
            with c_action:
                btn_col1, btn_col2 = st.columns([1, 1.2])
                with btn_col1:
                    if st.button("👁️ View / Edit", key=f"view_{job['id']}", use_container_width=True):
                        st.session_state.inspect_job = job['id']
                with btn_col2:
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        job['data'].to_excel(writer, index=False, sheet_name=job['modality'])
                    st.download_button(
                        label="⬇️ Excel (.xlsx)",
                        data=excel_buffer.getvalue(),
                        file_name=f"{job['id']}_{job['modality']}_Summary.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_{job['id']}",
                        use_container_width=True
                    )
            st.divider()

    # Active Inspector Grid
    if st.session_state.inspect_job:
        target_job = next((j for j in st.session_state.jobs_list if j['id'] == st.session_state.inspect_job), None)
        if target_job:
            st.markdown(f"#### ✏️ Live Inspection & Verification: `{target_job['id']}` ({target_job['modality']})")
            st.caption("You can click and edit any incorrect value directly below. Changes will be saved to Excel.")
            
            edited_data = st.data_editor(
                target_job['data'],
                use_container_width=True,
                num_rows="dynamic",
                key=f"editor_{target_job['id']}"
            )
            target_job['data'] = edited_data

