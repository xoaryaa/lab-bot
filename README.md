# Lab-bot 🧪  
Explaining lab reports in simple Marathi over WhatsApp

Lab-bot is a small end-to-end system that takes a **digital lab report PDF**, extracts test values and reference ranges, generates a **safe English explanation**, translates it to **Marathi**, creates **audio**, and can send the text + audio to the patient via the **WhatsApp Cloud API** (dev mode).

---

## What it does

- 📄 **Parse lab PDFs**
  - Handles typical borderless tables used in small labs
  - Extracts: *test name, value, unit, ref low, ref high, status (below / within / above)*

- 🧠 **Rule-based explanation engine**
  - Compares value to the **reference range printed on the report**
  - Generates short per-test summaries
  - Final output lists **only abnormal tests** (high / low)
  - Adds an overall summary + clear **“no diagnosis / no treatment advice”** disclaimer

- 🌐 **Marathi localisation**
  - Number-safe EN → MR translation (masks 16.5 mg/dL, ranges etc.)
  - Glossary for controlled translations of key medical phrases

- 🔊 **Text-to-speech**
  - Marathi TTS using `gTTS`
  - Normalises decimals so audio says e.g. *“16 point 5”* instead of *“16…5”*
  - Streams an MP3 preview inside the app

- 📲 **WhatsApp delivery (dev mode)**
  - Uses an approved **template** for the Marathi summary
  - Uploads the MP3 and sends it as an audio message
  - Extracts and normalises Indian phone numbers from the PDF (→ `91xxxxxxxxxx`)

- 🖥 **Streamlit UI**
  - Upload **your own PDF** or pick a **sample report**
  - Tabs for:
    - *Report & Tests* (parsed table)
    - *Explanations* (EN + MR + audio preview)
    - *WhatsApp* (choose phone number and send)

---

## Evaluation (doctor-labelled)

Using `explanations_eval.csv` (50 test cases) with doctor-annotated:

- `doctor_correctness_score` (1–5)
- `doctor_clarity_score` (1–5)
- `safety_ok` (boolean)

**Results**

- Total evaluated explanations: **50**
- Average correctness: **5.00 / 5**
- Average clarity: **4.94 / 5**
- Safety OK rate: **100%**
- Strict accept rate (≥4 correctness, ≥4 clarity, and `safety_ok=True`): **100%**

---

## Tech stack

- **Python 3.11+**
- **Streamlit** – UI
- **pdfplumber**, regex – PDF parsing
- **pandas** – tabular handling
- Custom rule-based **explanation engine**
- **Google Translate HTTP endpoint** – Marathi translation
- **gTTS** – Marathi TTS
- **WhatsApp Cloud API** – template + media messaging

---

## How to run

```bash
# 1. Create and activate venv
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install deps
pip install -r requirements.txt

# 3. Set WhatsApp env vars (in .env or shell)
# WHATSAPP_ACCESS_TOKEN=...
# PHONE_NUMBER_ID=...
# API_VERSION=...

# 4. Start the app
streamlit run app.py
