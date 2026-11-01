# Nexus Bill Processor — improved Streamlit starter

## Included
- Multiple PDFs in one run; each PDF is limited to 50 pages.
- One bill per page assumption.
- Gemini JSON-structured extraction with retries for transient API errors.
- Required-field, amount and confidence checks; uncertain rows are marked Review.
- Editable saved job results.
- SQLite job history and one consolidated daily Excel workbook with All Bills, Extracted, Needs Review and Summary sheets.
- No hardcoded dashboard password or API key.

## Run locally
Use Python 3.10+:
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
Enter your Gemini API key in the sidebar, or set `GEMINI_API_KEY` as an environment variable.
The model defaults to `gemini-2.5-flash`; change `GEMINI_MODEL` or the sidebar model field if your account uses another supported model.

## Important
This is an improved pilot, not a certified hospital production system. Test using de-identified/sample bills first. Confirm the model is available in your Google AI account and check pricing/quota. For public hosting, configure persistent storage: the local SQLite file may not survive ephemeral deployments. Add proper user authentication, HTTPS, encryption, access controls, audit logs, backup and retention/deletion controls before real patient data. Never commit secrets or real patient PDFs to GitHub. Your organisation must approve sending patient billing data to any external AI provider.
