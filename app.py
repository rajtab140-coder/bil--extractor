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
            
            # Excel export
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
