
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
import pypdfium2 as pdfium
import io
import json

st.set_page_config(page_title="Bill Extractor", layout="wide")

# --- PASSWORD LOGIN ---
APP_PASSWORD = "raj123"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Login Required")
    pwd_input = st.text_input("Password dalein:", type="password")
    if st.button("Login"):
        if pwd_input == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Galat Password!")
    st.stop()

# --- MAIN APP ---
st.title("📄 Bill Extractor")

if st.sidebar.button("Logout"):
    st.session_state.authenticated = False
    st.rerun()

api_key = st.sidebar.text_input("Gemini API Key yahan dalein:", type="password")

# Samne hi chaaron modality tabs ke roop me
tab_xray, tab_ct, tab_mri, tab_opg = st.tabs(["🩻 X-Ray", "🧠 CT Scan", "🧲 MRI", "🦷 OPG"])

def process_modality_bills(modality_name):
    st.subheader(f"{modality_name} Bills Upload")
    uploaded_files = st.file_uploader(
        f"{modality_name} ki PDF files chunein (Ek saath 10 ya zyada PDF daal sakte hain):",
        type=["pdf"],
        accept_multiple_files=True,
        key=f"uploader_{modality_name}"
    )

    if uploaded_files and api_key:
        if st.button(f"🚀 Extract {modality_name} Bills Data", key=f"btn_{modality_name}"):
            client = genai.Client(api_key=api_key)
            extracted_records = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            prompt_instruction = f"""
            Extract details from this hospital bill specifically for category: '{modality_name}'.
            Fields required in exact order:
            1. Patient Name: Full name
            2. Age/Sex: e.g. 29 YR/FEMALE
            3. Bill Number: e.g. 999102260402562/1
            4. CR Number: e.g. 999102604754731
            5. Procedure Name: Standardize to '{modality_name}' with body region (e.g. '{modality_name} Chest PA' or '{modality_name} Cervical Spine').
            6. Amount: Billed amount in numbers (e.g. 2125.00)
            7. Date: Transaction date (e.g. 27-Oct-2026)

            Return ONLY valid JSON:
            {{
               "Patient Name": "",
               "Age/Sex": "",
               "Bill Number": "",
               "CR Number": "",
               "Procedure Name": "",
               "Amount": "",
               "Date": ""
            }}
            Do not include markdown or backticks.
            """

            total_files = len(uploaded_files)
            for file_idx, file in enumerate(uploaded_files):
                status_text.text(f"Processing File {file_idx+1} of {total_files}: {file.name}")
                pdf_bytes = file.read()
                pdf = pdfium.PdfDocument(pdf_bytes)

                for page_idx, page in enumerate(pdf):
                    image_pil = page.render(scale=2).to_pil_image()
                    img_byte_arr = io.BytesIO()
                    image_pil.save(img_byte_arr, format='JPEG')
                    image_bytes = img_byte_arr.getvalue()

                    try:
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=[
                                types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                                prompt_instruction
                            ]
                        )
                        clean_text = response.text.replace("```json", "").replace("```", "").strip()
                        record = json.loads(clean_text)
                        extracted_records.append(record)
                    except Exception as e:
                        extracted_records.append({
                            "Patient Name": f"{file.name} (P{page_idx+1}) Error",
                            "Age/Sex": "-",
                            "Bill Number": "-",
                            "CR Number": "-",
                            "Procedure Name": f"{modality_name} Error",
                            "Amount": "-",
                            "Date": "-"
                        })

                progress_bar.progress((file_idx + 1) / total_files)

            status_text.empty()
            st.success(f"✅ {len(uploaded_files)} PDF Files ka Extraction poora ho gaya!")

            columns_order = [
                "Patient Name", "Age/Sex", "Bill Number", 
                "CR Number", "Procedure Name", "Amount", "Date"
            ]
            df = pd.DataFrame(extracted_records)
            df = df.reindex(columns=columns_order)

            # Table display
            st.dataframe(df, use_container_width=True)

            # --- ALAG DOWNLOAD SECTION ---
            st.divider()
            st.markdown("### 📥 Download Section")
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name=modality_name)

            col1, col2 = st.columns([1, 2])
            with col1:
                st.download_button(
                    label=f"⬇️ Download {modality_name} Excel Sheet (.xlsx)",
                    data=excel_buffer.getvalue(),
                    file_name=f"{modality_name}_Bills_Summary.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
    elif not api_key and uploaded_files:
        st.warning("Left sidebar me Gemini API Key dalein.")

# Charo tabs ko function assign karna
with tab_xray:
    process_modality_bills("X-Ray")

with tab_ct:
    process_modality_bills("CT Scan")

with tab_mri:
    process_modality_bills("MRI")

with tab_opg:
    process_modality_bills("OPG")

