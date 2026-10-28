
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
import pypdfium2 as pdfium
import io
import json

st.set_page_config(page_title="AIIMS Bill Extractor", layout="wide")
st.title("🏥 Hospital Bill to Excel Extractor")

api_key = st.sidebar.text_input("Gemini API Key yahan dalein:", type="password")

st.subheader("1. Modality / Department Select Karein:")
selected_category = st.selectbox(
    "Aap kis category ka bill upload kar rahe hain?",
    ["X-Ray", "CT Scan", "MRI", "OPG"]
)

st.subheader("2. Bills ki PDF Upload Karein:")
uploaded_file = st.file_uploader(f"{selected_category} ki PDF File Upload Karein", type=["pdf"])

if uploaded_file and api_key:
    if st.button(f"📊 Process & Extract {selected_category} Bills"):
        client = genai.Client(api_key=api_key)
        
        with st.spinner(f"{selected_category} bills process ho rahe hain, kripya intezar karein..."):
            pdf_bytes = uploaded_file.read()
            pdf = pdfium.PdfDocument(pdf_bytes)
            total_pages = len(pdf)
            
            st.info(f"Total {total_pages} Pages mile. Extraction chalu hai...")
            extracted_records = []
            progress_bar = st.progress(0)
            
            prompt_instruction = f"""
            You are a hospital billing receipt data extractor. Analyze this receipt image carefully.
            The user is specifically processing bills for the category: '{selected_category}'.

            Extract the following details in this exact order:
            1. Patient Name: Full name of the patient.
            2. Age/Sex: Patient age and sex (e.g., 29 YR/FEMALE).
            3. Bill Number: The receipt/bill number.
            4. CR Number: Central Registration number.
            5. Procedure Name: Specifically focus on the investigation related to '{selected_category}'. Simplify and clean the procedure name to show '{selected_category}' with the body region examined (e.g. if category is MRI, return 'MRI Cervical Spine'; if X-Ray, return 'X-Ray Chest PA'; if OPG, return 'OPG Dental'; if CT Scan, return 'CT Brain Plain'). Do not include administrative text or item codes.
            6. Amount: The exact amount billed/collected for this procedure in numbers (e.g., 2125.00).
            7. Date: Date of transaction/bill.

            Return ONLY valid JSON with these exact keys:
            {{
               "Patient Name": "",
               "Age/Sex": "",
               "Bill Number": "",
               "CR Number": "",
               "Procedure Name": "",
               "Amount": "",
               "Date": ""
            }}
            Do not include backticks, markdown blocks, or any explanation. Return strictly raw JSON.
            """

            for index, page in enumerate(pdf):
                image_pil = page.render(scale=2).to_pil_image()
                img_byte_arr = io.BytesIO()
                image_pil.save(img_byte_arr, format='JPEG')
                image_bytes = img_byte_arr.getvalue()
                
                try:
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[
                            types.Part.from_bytes(
                                data=image_bytes,
                                mime_type='image/jpeg'
                            ),
                            prompt_instruction
                        ]
                    )
                    clean_text = response.text.replace("```json", "").replace("```", "").strip()
                    record = json.loads(clean_text)
                    extracted_records.append(record)
                except Exception as e:
                    extracted_records.append({
                        "Patient Name": f"Page {index+1} Error",
                        "Age/Sex": "-",
                        "Bill Number": "-",
                        "CR Number": "-",
                        "Procedure Name": f"{selected_category} Error",
                        "Amount": "-",
                        "Date": "-"
                    })
                
                progress_bar.progress((index + 1) / total_pages)
            
            columns_order = [
                "Patient Name", 
                "Age/Sex", 
                "Bill Number", 
                "CR Number", 
                "Procedure Name", 
                "Amount", 
                "Date"
            ]
            df = pd.DataFrame(extracted_records)
            df = df.reindex(columns=columns_order)
            
            st.success(f"✅ {selected_category} Data Extraction Poora Ho Gaya!")
            st.dataframe(df, use_container_width=True)
            
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name=selected_category)
            
            st.download_button(
                label=f"📥 Download {selected_category} Excel Sheet (.xlsx)",
                data=excel_buffer.getvalue(),
                file_name=f"{selected_category}_Bills_Summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

elif not api_key and uploaded_file:
    st.warning("Kripya baayein (left) sidebar me apni Gemini API Key dalein.")

