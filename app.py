# DataFrame generate karna specific sequence me
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
            
            st.success("✅ Data Extraction Poora Ho Gaya!")
            st.dataframe(df, use_container_width=True)
            
            # Excel export
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name="Hospital_Bills")
            
            st.download_button(
                label="📥 Download Excel Sheet (.xlsx)",
                data=excel_buffer.getvalue(),
                file_name="AIIMS_Bills_Summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

elif not api_key and uploaded_file:
    st.warning("Kripya baayein (left) sidebar me apni Gemini API Key dalein.")
