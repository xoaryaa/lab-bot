# Lab Report Explainer 🧪

A Streamlit-based web app that helps patients understand their lab reports in
simple language. It:

- Parses **digital PDF** lab reports (even with borderless tables)
- Extracts test values and the **reference ranges printed on the report**
- Flags only the tests that are **below or above** the reference range
- Generates a **safe, non-diagnostic English summary**
- Translates the summary to **Marathi**
- Produces a **Marathi audio** version via TTS
- Sends the text + audio to the patient via **WhatsApp Cloud API** (dev mode)

> ⚠️ Medical safety: The app **does not diagnose** or suggest treatments. It
> only restates what is already printed on the lab report and clearly asks
> patients to consult a doctor.

---

## Features

- **PDF parsing** (pdfplumber + fallback text parser) for typical lab report layouts  
- Robust extraction of:
  - Test name
  - Observed value
  - Unit
  - Reference low / high
  - Status: `below`, `within`, `above`
- **Summary generation**:
  - Only includes abnormal tests (below/above range)
  - Adds a clear disclaimer
- **Marathi localisation**:
  - English → Marathi translation
  - Marathi text-to-speech (MP3)
- **WhatsApp integration**:
  - Sends summary text and audio via WhatsApp Cloud API
  - Currently configured for **developer/test mode** (only whitelisted numbers)

---

## Tech Stack

- **Language**: Python 3.11+ (tested on 3.13 with a small `cgi.py` shim)
- **Frontend**: [Streamlit](https://streamlit.io/)
- **PDF parsing**: [pdfplumber](https://github.com/jsvine/pdfplumber)
- **Data**: pandas
- **Translation**: `googletrans` 
- **TTS**: `gTTS` (Marathi)
- **Messaging**: WhatsApp Cloud API (`requests`)

---


