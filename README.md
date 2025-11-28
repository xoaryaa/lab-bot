# Lab-bot 🧪

Lab-bot is a Streamlit web app that explains lab reports in simple language for patients at a small-town Indian hospital.

**What it does**

- Parses digital **PDF lab reports** (borderless tables, messy layouts)
- Extracts test name, value, unit, reference low/high, and flags **high/low** results
- Generates a **safe, non-diagnostic English summary** (only abnormal tests)
- Translates the summary to **Marathi** and creates **Marathi TTS audio**
- Sends text + audio to the patient via **WhatsApp Cloud API**

**Safety & evaluation**

- No diagnosis or treatment suggestions; always tells patients to consult a doctor  
- Evaluated on **50 explanations** by a practising doctor:  
  - Avg. correctness score: **5.0 / 5**  
  - Avg. clarity score: **4.94 / 5**  
  - **100%** safety-OK  
  - **100%** strict accept rate (≥4 correctness, ≥4 clarity, safe)

**Tech stack**

- Python, Streamlit, pandas  
- pdfplumber-based parser + custom heuristics  
- Rule-based explanation engine over `LabTestResult` objects  
- Custom Marathi translation wrapper (Google Translate backend)  
- gTTS for audio, WhatsApp Cloud API for delivery

> This tool is meant to **restate** lab report information in easier language,
> not to replace medical advice.
