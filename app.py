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
uploaded_file = st.file_uploader("PDF Bill File Upload Karein", type=["pdf"])

if uploaded_file and api_key:
    if st.button("📊 Extract Data to Excel"):
        client = genai.Client(api_key=api_key)
        
        with st.spinner("PDF process ho rahi hai, intezar karein..."):
            pdf_bytes = uploaded_file.read()
            pdf = pdfium.PdfDocument(pdf_bytes)
            total_pages = len(pdf)
            
            st.info(f"Total Pages: {total_pages}. Processing chalu hai...")
            extracted_records = []
            progress_bar = st.progress(0)
            
            prompt_instruction = """
            Extract the following details from this hospital bill receipt into strict JSON:
            - Name
            - Age_Sex
            - CR_No
            - Bill_No
            - Date
            - Amount
            - Procedure_Name

            Return ONLY valid JSON format:
            {
               "Name": "",
               "Age_Sex": "",
               "CR_No": "",
               "Bill_No": "",
               "Date": "",
               "Amount": "",
               "Procedure_Name": ""
            }
            Do not include backticks or markdown.
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
                    clean_text = response.text.replace("`json", "").replace("```", "").strip()
                    record = json.loads(clean_text)
                    extracted_records.append(record)
                except Exception as e:
                    extracted_records.append({
                        "Name": "Error",
                        "Age_Sex": "-",
                        "CR_No": "-",
                        "Bill_No": "-",
                        "Date": "-",
                        "Amount": "-",
                        "Procedure_Name": f"Page {index+1} Error"
                    })
                
                progress_bar.progress((index + 1) / total_pages)
            
            df = pd.DataFrame(extracted_records)
            st.success("✅ Extraction poora ho gaya!")
            st.dataframe(df, use_container_width=True)
            
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name="Bills_Data")
            
            st.download_button(
                label="📥 Download Excel Sheet (.xlsx)",
                data=excel_buffer.getvalue(),
                file_name="Hospital_Bills_Summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

elif not api_key and uploaded_file:
    st.warning("Kripya baayein (left) sidebar me apni Gemini API Key daalein.")
