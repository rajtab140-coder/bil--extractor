import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
import fitz # PyMuPDF
import json
import io
from concurrent.futures import ThreadPoolExecutor

# Page Configuration
st.set_page_config(page_title="Bill Processor", layout="wide", initial_sidebar_state="collapsed")

# --- Custom Styling for Modern Clean UI ---
st.markdown("""
<style>
    /* Global background */
    .stApp {
        background-color: #f1f5f9;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Top Navbar */
    .top-navbar {
        background-color: #0f172a;
        padding: 12px 24px;
        display: flex;
        align-items: center;
        gap: 25px;
        color: #94a3b8;
        font-size: 14px;
        font-weight: 500;
        margin: -6rem -6rem 2rem -6rem;
    }
    .top-navbar span.brand {
        color: #ffffff;
        font-weight: 700;
        font-size: 16px;
        margin-right: 15px;
    }
    .top-navbar span.active {
        color: #38bdf8;
    }

    /* Main Container Card */
    .main-card {
        background-color: #ffffff;
        border-radius: 14px;
        padding: 30px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
        max-width: 850px;
        margin: 0 auto;
        border: 1px solid #e2e8f0;
    }

    /* Primary Process Button */
    div.stButton > button {
        background-color: #1d4ed8 !important;
        color: white !important;
        font-weight: 600 !important;
        font-size: 16px !important;
        padding: 12px 24px !important;
        border-radius: 8px !important;
        border: none !important;
        width: 100% !important;
        transition: 0.2s;
    }
    div.stButton > button:hover {
        background-color: #1e40af !important;
    }
</style>

<!-- Top bar -->
<div class="top-navbar">
    <span class="brand">📑 Bill Processor</span>
    <span class="active">Upload</span>
    <span>Downloads</span>
</div>
""", unsafe_allow_html=True)

# --- Authentication ---
APP_PASSWORD = "raj123"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
    st.subheader("🔒 Login Required")
    pwd_input = st.text_input("Enter Password:", type="password")
    if st.button("Login"):
        if pwd_input == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect Password!")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# API Key Sidebar Configuration
api_key = st.sidebar.text_input("Gemini API Key:", type="password")
if st.sidebar.button("Logout"):
    st.session_state.authenticated = False
    st.rerun()

# --- Main Upload Card Container ---
st.markdown("<div class='main-card'>", unsafe_allow_html=True)

st.markdown("<h2 style='color: #0f172a; margin-top: 0;'>📑 Upload Bills</h2>", unsafe_allow_html=True)

# 1. Bill Type Selector (Radio horizontal)
st.markdown("<p style='font-weight:600; color: #475569; margin-bottom: 5px;'>Bill Type</p>", unsafe_allow_html=True)
selected_bill_type = st.radio(
    "Bill Type",
    ["CT", "MRI", "X-Ray", "OPG", "USG"],
    horizontal=True,
    label_visibility="collapsed"
)

# 2. AI Engine Selection
st.markdown("<p style='font-weight:600; color: #475569; margin-top: 15px; margin-bottom: 5px;'>AI Engine</p>", unsafe_allow_html=True)
selected_engine = st.radio(
    "AI Engine",
    [
        "⚡ Gemini 3.8 Flash (High Speed & Precise Extraction)",
        "🧠 Claude Opus (Simulated)",
        "🚀 Grok (Simulated)"
    ],
    index=0,
    label_visibility="collapsed"
)

# 3. Drag & Drop PDF Upload Area
st.markdown("<p style='font-weight:600; color: #475569; margin-top: 15px; margin-bottom: 5px;'>Upload Files</p>", unsafe_allow_html=True)
uploaded_files = st.file_uploader(
    "Drag & drop PDFs here or browse (Select multiple PDFs at once)",
    type=["pdf"],
    accept_multiple_files=True,
    label_visibility="collapsed"
)

# Process Button
process_btn = st.button("🚀 Upload & Process", use_container_width=True)

st.markdown("</div>", unsafe_allow_html=True)

# --- Parallel Processing Logic ---
def process_single_page(client, img_bytes, prompt_instruction, label):
    try:
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type='image/jpeg'),
                prompt_instruction
            ]
        )
        raw_txt = response.text.strip()
        if "```json" in raw_txt:
            raw_txt = raw_txt.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_txt:
            raw_txt = raw_txt.split("```")[1].split("```")[0].strip()
        return json.loads(raw_txt)
    except Exception as err:
        return {
            "Patient Name": f"{label} Error",
            "Age/Sex": "-",
            "Bill Number": "-",
            "CR Number": "-",
            "Procedure Name": "-",
            "Amount": "-",
            "Date": "-"
        }

if process_btn:
    if not api_key:
        st.warning("⚠️ Please provide your Gemini API Key in the left sidebar to start processing.")
    elif not uploaded_files:
        st.warning("⚠️ Please select at least one PDF bill file.")
    else:
        try:
            client = genai.Client(api_key=api_key.strip())
        except Exception as e:
            st.error(f"API Client Init Error: {str(e)}")
            st.stop()

        prompt_instruction = f"""
        Extract details from this hospital bill specifically for category: '{selected_bill_type}'.
        Strict fields order:
        1. Patient Name: Full name (after 'NAME :')
        2. Age/Sex: Patient Age and Sex (after 'AGE/SEX :')
        3. Bill Number: Bill Number (after 'BILL No. :')
        4. CR Number: CR Number (after 'CR No. :')
        5. Procedure Name: Standardize to '{selected_bill_type}' with body region (e.g. '{selected_bill_type} Cervical Spine').
        6. Amount: Total collected numeric amount (e.g. 2125.00).
        7. Date: Date printed (e.g. 27-Oct-2026).

        Return ONLY raw JSON with keys:
        "Patient Name", "Age/Sex", "Bill Number", "CR Number", "Procedure Name", "Amount", "Date"
        """

        all_page_tasks = []
        with st.spinner("Extracting pages..."):
            for file in uploaded_files:
                file_bytes = file.read()
                try:
                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                    for page_idx in range(len(doc)):
                        page = doc.load_page(page_idx)
                        pix = page.get_pixmap(dpi=120)
                        img_bytes = pix.tobytes("jpeg")
                        all_page_tasks.append((img_bytes, f"{file.name} (P{page_idx+1})"))
                except Exception as e:
                    st.error(f"Error opening {file.name}: {str(e)}")

        total_pages = len(all_page_tasks)
        st.info(f"⚡ Processing {total_pages} bill pages in parallel...")

        extracted_records = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(process_single_page, client, item[0], prompt_instruction, item[1])
                for item in all_page_tasks
            ]
            for future in futures:
                extracted_records.append(future.result())

        columns_order = [
            "Patient Name", "Age/Sex", "Bill Number", 
            "CR Number", "Procedure Name", "Amount", "Date"
        ]
        df = pd.DataFrame(extracted_records)
        for col in columns_order:
            if col not in df.columns:
                df[col] = "-"
        st.session_state["extracted_data"] = df[columns_order]
        st.success(f"✅ Successfully processed {total_pages} bills!")

# --- Editable Data Table & Excel Export ---
if "extracted_data" in st.session_state and st.session_state["extracted_data"] is not None:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
    st.subheader("✏️ Review & Edit Data")
    st.caption("Double-click any cell to make manual corrections.")

    edited_df = st.data_editor(
        st.session_state["extracted_data"],
        use_container_width=True,
        num_rows="dynamic"
    )

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        edited_df.to_excel(writer, index=False, sheet_name=selected_bill_type)

    st.download_button(
        label=f"⬇️ Download {selected_bill_type} Excel File (.xlsx)",
        data=excel_buffer.getvalue(),
        file_name=f"{selected_bill_type}_Bills_Summary.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    st.markdown("</div>", unsafe_allow_html=True)

