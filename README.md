# Lab Report Explainer 🧪📲

A Streamlit app that helps **lab assistants** send simple, safe explanations of lab reports to patients on WhatsApp.

Given a digital PDF report, the app:

- Parses the report into a **clean table of tests** (value + unit + reference range)
- Uses a **rule-based explanation engine** to describe only the **abnormal tests**
- Adds a short **overall summary** and a clear **“no diagnosis, ask your doctor”** notice
- Translates the English explanation to **Marathi** with a medical-aware translator
- Generates a single **Marathi audio clip** (TTS) with natural handling of numbers and decimals
- Sends the Marathi **text + audio** to the patient via **WhatsApp Cloud API** (dev mode / whitelisted numbers)

---

## Key Features

- **PDF → Structured Data**
  - pdfplumber-based parser tuned for this hospital’s report layout  
  - Heuristics to recover **units** (e.g. g/dL, mg/dL, mmol/L) even when not in the table  
  - Status flag per test: `below`, `within`, `above`

- **Explanation Engine**
  - `LabTestResult` dataclass + `evaluate_report()` rule engine  
  - Per-test explanations only for **out-of-range** values  
  - Overall “how many tests are abnormal” summary  
  - Single, prominent **safety notice** (no diagnosis, no treatment advice)

- **Smart Translation & TTS**
  - Custom `SmartMedicalTranslator` (glossary + number/unit masking)  
  - Backend uses the **Google Translate HTTP API via `requests`** (no `googletrans`)  
  - `TTSService` with:
    - decimal-aware text normalisation (`16.5` → “16 point 5”, `16.0` → “16”)
    - sentence splitting that doesn’t break on decimals
    - usually a **single MP3** per explanation

- **WhatsApp Delivery**
  - Formats patient phone numbers for WhatsApp
  - Sends Marathi summary via a **WhatsApp template message**
  - Uploads MP3 and sends as **voice/audio** message
  - Designed to be triggered by a **lab assistant**, not directly by patients

- **Evaluation Pipeline**
  - `eval/explanations_eval.csv`: rows for each test (value + range)  
  - App-generated `system_flag` + `system_explanation`  
  - Doctor fills:
    - correctness score
    - clarity score
    - safety_ok + notes  
  - Allows simple metrics like **avg correctness/clarity** and **% safe explanations**

---

## Tech Stack

- **Python** 3.11+  
- **Streamlit** for the UI  
- **pdfplumber**, **pandas** for parsing & data handling  
- **requests** for translation (Google endpoint) & WhatsApp Cloud API  
- **gTTS** for Marathi text-to-speech  

> ⚠️ **Safety note:**  
> This tool **does not diagnose or prescribe**. It only explains what is already printed on the lab report and repeatedly tells patients to consult their doctor for decisions.
