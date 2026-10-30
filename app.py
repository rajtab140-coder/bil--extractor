import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
import fitz # PyMuPDF
import json
import io

st.set_page_config(page_title="Bill Extractor Pro", layout="wide")

# --- AUTHENTICATION ---
APP_PASSWORD = "raj123"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Login Required")
    pwd_input = st.text_input("Enter Password:", type="password")
    if st.button("Login"):
        if pwd_input == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect Password! Please try again.")
    st.stop()

# --- MAIN APP ---
st.title("📄 Professional Bill Extractor & Editor")

if st.sidebar.button("Logout"):
    st.session_state.authenticated = False
    st.rerun()

api_key = st.sidebar.text_input("Enter Gemini API Key:", type="password")

# Modality Tabs
tab_xray, tab_ct, tab_mri, tab_opg = st.tabs(["🩻 X-Ray", "🧠 CT Scan", "🧲 MRI", "🦷 OPG"])

def process_modality_bills(modality_name):
    st.subheader(f"{modality_name} Bills Upload")
    uploaded_files = st.file_uploader(
        f"Select {modality_name} PDF Files (Upload multiple PDFs):",
        type=["pdf"],
        accept_multiple_files=True,
        key=f"uploader_{modality_name}"
    )

    state_key = f"data_{modality_name}"
    if state_key not in st.session_state:
        st.session_state[state_key] = None

    if uploaded_files and api_key:
        if st.button(f"🚀 Extract {modality_name} Bills Data", key=f"btn_{modality_name}"):
            try:
                client = genai.Client(api_key=api_key.strip())
            except Exception as e:
                st.error(f"API Key Setup Error: {str(e)}")
                return

            extracted_records = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            prompt_instruction = f"""
            You are an expert OCR receipt extractor for hospital billing OPD tickets.
            Carefully read this receipt image and extract these 7 fields:
            1. Patient Name: Full name of the patient (after 'NAME :')
            2. Age/Sex: Patient Age and Sex (after 'AGE/SEX :')
            3. Bill Number: Bill or Receipt Number (after 'BILL No. :')
            4. CR Number: Complete CR Number (after 'CR No. :')
            5. Procedure Name: Specifically focus on the investigation related to '{modality_name}'. Include the modality and body region (e.g. 'MRI Cervical Spine', 'X-Ray Chest PA', 'CT Brain', 'OPG'). Do not add noise like 'OPD NORMAL'.
            6. Amount: Total collected amount in numeric form (e.g. 2125.00).
            7. Date: Date printed on receipt (e.g. 27-Oct-2026).

            Return ONLY a raw JSON object with keys:
            "Patient Name", "Age/Sex", "Bill Number", "CR Number", "Procedure Name", "Amount", "Date"
            Do not include backticks, markdown formatting, or notes.
            """

            total_files = len(uploaded_files)
            for file_idx, file in enumerate(uploaded_files):
                file_bytes = file.read()
                try:
                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                except Exception as e:
                    st.error(f"Error reading file {file.name}: {str(e)}")
                    continue

                for page_idx in range(len(doc)):
                    status_text.text(f"Processing File {file_idx+1}/{total_files} - Page {page_idx+1}...")
                    page = doc.load_page(page_idx)
                    
                    pix = page.get_pixmap(dpi=200)
                    img_bytes = pix.tobytes("jpeg")

                    try:
                        # Model updated to gemini-3.8-flash
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
                            
                        record = json.loads(raw_txt)
                        extracted_records.append(record)
                    except Exception as err:
                        st.error(f"Error on {file.name} (Page {page_idx+1}): {str(err)}")
                        extracted_records.append({
                            "Patient Name": "Error Extracting",
                            "Age/Sex": "-",
                            "Bill Number": "-",
                            "CR Number": "-",
                            "Procedure Name": "-",
                            "Amount": "-",
                            "Date": "-"
                        })

                progress_bar.progress((file_idx + 1) / total_files)

            status_text.empty()

            if extracted_records:
                columns_order = [
                    "Patient Name", "Age/Sex", "Bill Number", 
                    "CR Number", "Procedure Name", "Amount", "Date"
                ]
                df = pd.DataFrame(extracted_records)
                for col in columns_order:
                    if col not in df.columns:
                        df[col] = "-"
                st.session_state[state_key] = df[columns_order]
                st.success(f"Done processing {len(uploaded_files)} file(s)!")

    # Table & Download
    if st.session_state[state_key] is not None:
        st.markdown("### ✏️ Verify & Edit Data:")
        edited_df = st.data_editor(
            st.session_state[state_key],
            use_container_width=True,
            num_rows="dynamic",
            key=f"editor_{modality_name}"
        )

        st.divider()
        st.markdown("### 📥 Download Section")
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            edited_df.to_excel(writer, index=False, sheet_name=modality_name)

        col1, col2 = st.columns([1, 2])
        with col1:
            st.download_button(
                label=f"⬇️ Download Verified {modality_name} Excel Sheet (.xlsx)",
                data=excel_buffer.getvalue(),
                file_name=f"{modality_name}_Verified_Bills.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
    elif not api_key and uploaded_files:
        st.warning("Please enter your Gemini API Key in the left sidebar.")

with tab_xray:
    process_modality_bills("X-Ray")

with tab_ct:
    process_modality_bills("CT Scan")

with tab_mri:
    process_modality_bills("MRI")

with tab_opg:
    process_modality_bills("OPG")

