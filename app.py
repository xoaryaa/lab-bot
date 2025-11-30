import io
import re
import pandas as pd
import streamlit as st
import os
# import requests
from pathlib import Path
from typing import List
from labbot.parser import extract_tests_from_pdf
from labbot.whatsapp_client import (
    send_lab_summary_template,
    upload_media_and_send_audio,
    format_phone_for_whatsapp,
)
from labbot.translator import SmartMedicalTranslator, GoogleTranslateBackend, TranslationConfig
from labbot.tts_service import TTSService, TTSConfig
from labbot.explanation_engine import LabTestResult, evaluate_report
from labbot.phone_utils import extract_phone_numbers
from labbot.config import DEFAULT_UNITS 

# ---- Global translation + TTS services ----

st.set_page_config(
    page_title="Lab Report Explainer",
    page_icon="🧪",
    layout="wide",
)


# Default units used when the parsed PDF does not contain a clean unit
DEFAULT_UNITS = {
    "Haemoglobin": "g/dL",
    "RBC Count": "millions/µL",
    "PCV": "%",
    "MCV": "fL",
    "MCH": "pg",
    "MCHC": "g/dL",
    "RDW-CV": "%",
    "Platelet Count": "cells/µL",
    "WBC Count": "cells/µL",
    "Neutrophils": "%",
    "Lymphocytes": "%",
    "Monocytes": "%",
    "Eosinophils": "%",
    "Basophils": "%",
    # add/update for your hospital as needed
}

SAMPLE_REPORT_DIR = Path("data/sample_reports")

base_translator = GoogleTranslateBackend()
translation_cfg = TranslationConfig(target_lang="mr")  # "hi" for Hindi if you switch later
smart_medical_translator = SmartMedicalTranslator(base_translator, translation_cfg)
tts_cfg = TTSConfig(
    lang="mr",
    slow=False,
    output_dir="tts_outputs",
    max_chars_per_chunk=3000,  # was 220 – make it big
)
tts_service = TTSService(tts_cfg)

def render_pixel_header():
    st.markdown(
        """
        <div style="
            max-width: 900px;
            margin: 0.75rem auto 1.75rem auto;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 1.75rem;
        ">
          <!-- Left tube -->
          <div style="width: 60px; image-rendering: pixelated;">
            <svg xmlns="http://www.w3.org/2000/svg"
                 viewBox="0 0 32 64"
                 shape-rendering="crispEdges">
              <rect x="10" y="4"  width="12" height="4"  fill="#222222" />
              <rect x="12" y="8"  width="8"  height="2"  fill="#222222" />
              <rect x="12" y="10" width="8"  height="40" fill="#222222" />
              <rect x="13" y="11" width="6" height="38" fill="#fdfdfd" />
              <rect x="13" y="31" width="6" height="18" fill="#FFB7D5">
                <animate attributeName="y"
                         values="35;31;35"
                         dur="2.2s"
                         repeatCount="indefinite" />
                <animate attributeName="height"
                         values="14;18;14"
                         dur="2.2s"
                         repeatCount="indefinite" />
              </rect>
              <rect x="15" y="28" width="2" height="2" fill="#FF7AC4" opacity="0">
                <animate attributeName="y"
                         values="28;18"
                         dur="1.6s"
                         repeatCount="indefinite" />
                <animate attributeName="opacity"
                         values="0;1;0"
                         dur="1.6s"
                         repeatCount="indefinite" />
              </rect>
              <rect x="16" y="26" width="2" height="2" fill="#FF7AC4" opacity="0">
                <animate attributeName="y"
                         values="26;17"
                         dur="1.9s"
                         repeatCount="indefinite" />
                <animate attributeName="opacity"
                         values="0;1;0"
                         dur="1.9s"
                         repeatCount="indefinite" />
              </rect>
              <rect x="12" y="50" width="8" height="2" fill="#e0e0e0" />
            </svg>
          </div>

          <!-- Center text -->
          <div style="text-align: center;">
            <h1 style="margin: 0; font-size: 1.75rem;"> Lab-bot</h1>
            <p style="
                margin: 0.25rem 0 0 0;
                font-size: 0.95rem;
                color: #666666;
                max-width: 540px;
            ">
              Upload your lab report and get explained test results in English &amp; Marathi.
              The bot can also send the summary + audio to patients on WhatsApp.
            </p>
          </div>

          <!-- Right tube -->
          <div style="width: 60px; image-rendering: pixelated;">
            <svg xmlns="http://www.w3.org/2000/svg"
                 viewBox="0 0 32 64"
                 shape-rendering="crispEdges">
              <rect x="10" y="4"  width="12" height="4"  fill="#222222" />
              <rect x="12" y="8"  width="8"  height="2"  fill="#222222" />
              <rect x="12" y="10" width="8"  height="40" fill="#222222" />
              <rect x="13" y="11" width="6" height="38" fill="#fdfdfd" />
              <rect x="13" y="31" width="6" height="18" fill="#FFB7D5">
                <animate attributeName="y"
                         values="35;31;35"
                         dur="2.2s"
                         repeatCount="indefinite" />
                <animate attributeName="height"
                         values="14;18;14"
                         dur="2.2s"
                         repeatCount="indefinite" />
              </rect>
              <rect x="15" y="28" width="2" height="2" fill="#FF7AC4" opacity="0">
                <animate attributeName="y"
                         values="28;18"
                         dur="1.6s"
                         repeatCount="indefinite" />
                <animate attributeName="opacity"
                         values="0;1;0"
                         dur="1.6s"
                         repeatCount="indefinite" />
              </rect>
              <rect x="16" y="26" width="2" height="2" fill="#FF7AC4" opacity="0">
                <animate attributeName="y"
                         values="26;17"
                         dur="1.9s"
                         repeatCount="indefinite" />
                <animate attributeName="opacity"
                         values="0;1;0"
                         dur="1.9s"
                         repeatCount="indefinite" />
              </rect>
              <rect x="12" y="50" width="8" height="2" fill="#e0e0e0" />
            </svg>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def get_explanation_in_marathi(english_explanation: str) -> str:
    return smart_medical_translator.translate_explanation(english_explanation)

def get_audio_for_explanation(english_text: str):
    # Step 1: translate
    mr_text = smart_medical_translator.translate_explanation(english_text)

    # Step 2: generate audio file(s)
    audio_paths = tts_service.text_to_speech_files(mr_text)

    return mr_text, audio_paths

def df_to_labtests(df: pd.DataFrame) -> List[LabTestResult]:
    """
    Convert the parsed tests DataFrame into a list of LabTestResult objects
    for the rule-based explanation engine.
    Cleans junk units like 'M:' / 'F:'.
    """
    tests: List[LabTestResult] = []

    def _safe_float(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    # Try to find the unit column by name (e.g., 'Unit')
    unit_col = None
    for col in df.columns:
        if "unit" in col.lower():
            unit_col = col
            break

    for _, row in df.iterrows():
        try:
            value = float(row["Value"])
        except (TypeError, ValueError):
            continue

        # ---- unit cleaning ----
        raw_unit = ""
        if unit_col is not None:
            raw_unit = str(row.get(unit_col, "")).strip()

        # Drop junk like "M:" / "F:" or just ":".
        if re.fullmatch(r"[A-Za-z]:", raw_unit) or raw_unit == ":":
            unit = ""
        else:
            unit = raw_unit

        tests.append(
            LabTestResult(
                name=str(row.get("Test Name", "")).strip(),
                value=value,
                unit=unit,
                ref_low=_safe_float(row.get("Ref Low")),
                ref_high=_safe_float(row.get("Ref High")),
            )
        )

    return tests

def fill_units_from_full_text(df: pd.DataFrame, full_text: str) -> pd.DataFrame:
    """
    If Unit column is empty, try to infer units from the raw PDF text using patterns like:
    'Haemoglobin (g/dL)'.
    """
    if "Unit" not in df.columns or "Test Name" not in df.columns:
        return df

    for idx, row in df.iterrows():
        current_unit = str(row.get("Unit", "")).strip()
        if current_unit:
            continue  # already has something (we may later clean it)

        test_name = str(row.get("Test Name", "")).strip()
        if not test_name:
            continue

        # Look for 'TestName (unit)' in the full_text
        pattern = rf"{re.escape(test_name)}\s*\(([^)]+)\)"
        m = re.search(pattern, full_text, flags=re.IGNORECASE)
        if m:
            df.at[idx, "Unit"] = m.group(1).strip()

    return df


# Utility functions



def extract_phone_numbers(text:str)->List[str]:
    """
    Extract possible Indian mobile numbers from text.
    Pattern: optional +91 and a 10-digit mobile starting with 6-9.
    """
    if not text:
        return[]
    pattern = r'(?:\+91[-\s]*)?[6-9]\d{9}'
    matches = re.findall(pattern, text)

    seen= set()
    phones=[]
    for m in matches:
        if m not in seen:
            seen.add(m)
            phones.append(m)
    return phones

def df_to_labtests(df: pd.DataFrame) -> List[LabTestResult]:
    """
    Convert the parsed tests DataFrame into a list of LabTestResult objects
    for the rule-based explanation engine.
    """
    tests: List[LabTestResult] = []

    def _safe_float(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    for _, row in df.iterrows():
        try:
            value = float(row["Value"])
        except (TypeError, ValueError):
            continue

        tests.append(
            LabTestResult(
                name=str(row.get("Test Name", "")).strip(),
                value=value,
                unit=str(row.get("Unit", "")).strip(),
                ref_low=_safe_float(row.get("Ref Low")),
                ref_high=_safe_float(row.get("Ref High")),
            )
        )

    return tests

def build_english_explanation_from_df(df: pd.DataFrame) -> str:
    
    tests = df_to_labtests(df)
    report = evaluate_report(tests)

    parts: List[str] = []

    evaluations = report["evaluations"]

    abnormal_evals = []
    normal_evals = []

    for ev in evaluations:
        # We expect TestEvaluation to have severity and/or flag.
        severity = getattr(ev, "severity", None)
        flag = getattr(ev, "flag", None)

        # Treat explicit "normal" as normal; everything else as abnormal-ish
        if severity == "normal" or flag == "normal":
            normal_evals.append(ev)
        else:
            abnormal_evals.append(ev)

    if abnormal_evals:
        for ev in abnormal_evals:
            parts.append(ev.summary_text)
    else:
            for ev in normal_evals:
                parts.append(ev.summary_text)

    # overall + category + safety
    if report["overall_summary_en"]:
        parts.append(report["overall_summary_en"])
    if report["category_summary_en"]:
        parts.append(report["category_summary_en"])
    if report["safety_notice_en"]:
        parts.append(report["safety_notice_en"])

    return " ".join(parts)


# WhatsApp Cloud API helpers 

# def send_whatsapp_hello_world_template(phone: str) -> tuple[bool, str, dict]:
#     """
#     Debug helper: send the built-in 'hello_world' template
#     exactly like the Meta cURL example, but using Python.
#     """
#     token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
#     phone_number_id = os.environ.get("PHONE_NUMBER_ID")
#     if not token or not phone_number_id:
#         return False, "WhatsApp credentials are not set in environment variables.", {}

#     api_version = "v22.0"
#     base_url = f"https://graph.facebook.com/{api_version}"
#     url = f"{base_url}/{phone_number_id}/messages"

#     to_number = re.sub(r"\D", "", phone or "")

#     headers = {
#         "Authorization": f"Bearer {token}",
#         "Content-Type": "application/json",
#     }

#     payload = {
#         "messaging_product": "whatsapp",
#         "to": to_number,
#         "type": "template",
#         "template": {
#             "name": "hello_world",
#             "language": {"code": "en_US"},
#         },
#     }

#     resp = requests.post(url, headers=headers, json=payload, timeout=15)
#     try:
#         data = resp.json()
#     except Exception:
#         data = {"raw": resp.text}

#     if 200 <= resp.status_code < 300 and "messages" in data:
#         return True, f"Status {resp.status_code}, template queued to {to_number}", data
#     return False, f"Status {resp.status_code}, API error", data


# Streamlit app UI



def main():
    # --- Hero header with pixel test tubes ---
    render_pixel_header()

    # --- Sidebar: WhatsApp status ---
    with st.sidebar:
        st.subheader("Configuration")
        wh_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
        wh_num_id = os.environ.get("PHONE_NUMBER_ID")
        if not wh_token or not wh_num_id:
            st.warning("WhatsApp env vars not set.\nSending will fail until you configure them.")
        else:
            st.success("WhatsApp Cloud API is configured.")

        st.markdown("---")
        # st.caption(
        #     "Tip: Add anonymised PDFs under `data/sample_reports/` so reviewers can test without uploading their own reports."
        # )

    # --- Choose input source: upload vs sample ---
    st.subheader("Choose a report")

    cols_src = st.columns([1, 2])
    with cols_src[0]:
        source = st.radio(
            "How do you want to test the app?",
            ["Upload your own PDF", "Use a sample report"],
            index=0,
        )

    uploaded_file = None
    selected_sample = None
    file_bytes = None

    with cols_src[1]:
        if source == "Upload your own PDF":
            uploaded_file = st.file_uploader("Upload lab report PDF", type=["pdf"])
            if uploaded_file is not None:
                file_bytes = uploaded_file.getvalue()
        else:
            # List available sample PDFs
            if SAMPLE_REPORT_DIR.exists():
                sample_files = [
                    f.name for f in SAMPLE_REPORT_DIR.iterdir()
                    if f.is_file() and f.suffix.lower() == ".pdf"
                ]
            else:
                sample_files = []

            if not sample_files:
                st.warning(
                    "No sample reports found in `data/sample_reports`. "
                    "Add a few anonymised PDF reports there to enable this option."
                )
            else:
                selected_sample = st.selectbox("Choose a sample report:", [""] + sample_files)
                if selected_sample:
                    sample_path = SAMPLE_REPORT_DIR / selected_sample
                    with open(sample_path, "rb") as f:
                        file_bytes = f.read()
                    st.info(f"Using sample report: `{selected_sample}`")

    if file_bytes is None:
        st.info("Upload a PDF or select a sample report to see the analysis.")
        return

    # --- Parse PDF ---
    with st.spinner("Reading and analysing the report..."):
        df, full_text = extract_tests_from_pdf(file_bytes)
        df = fill_units_from_full_text(df, full_text)

    if df.empty:
        st.error(
            "Could not find any test table with numeric values and reference ranges. "
            "You may need to adjust the parsing logic for your lab's report format."
        )
        return

    # Clean unit column for display + downstream logic
    display_df = df.copy()
    if "Unit" in display_df.columns and "Test Name" in display_df.columns:
        def _fix_unit_row(row):
            name = str(row.get("Test Name", "")).strip()
            raw_unit = str(row.get("Unit", "")).strip()
            if raw_unit in ("M:", "F:", ":"):
                raw_unit = ""
            if not raw_unit and name in DEFAULT_UNITS:
                return DEFAULT_UNITS[name]
            return raw_unit

        display_df["Unit"] = display_df.apply(_fix_unit_row, axis=1)

    # Use cleaned df everywhere
    df = display_df

    # --- Precompute everything once ---
    # Phone detection
    phones = extract_phone_numbers(full_text)

    # English explanation
    summary_en = build_english_explanation_from_df(df)

    # Marathi explanation + TTS
    with st.spinner("Translating explanation to Marathi and generating audio..."):
        try:
            marathi_summary = smart_medical_translator.translate_explanation(summary_en)
        except Exception as e:
            st.error(
                "Could not translate the explanation to Marathi right now. "
                "This is probably a network/Google Translate issue. "
                "Please try again in a minute."
            )
            st.caption(f"Technical details: {e}")
            marathi_summary = ""

    audio_bytes = io.BytesIO()
    if marathi_summary:
        audio_paths = tts_service.text_to_speech_files(
            marathi_summary,
            filename_prefix="ui_preview",
        )
        if audio_paths:
            first_path = audio_paths[0]
            with open(first_path, "rb") as f:
                audio_bytes = io.BytesIO(f.read())
                audio_bytes.seek(0)

    # --- Tabs for nicer navigation ---
    tab_report, tab_expl, tab_whatsapp = st.tabs(
        ["Report & Tests", "Explanations", "WhatsApp"]
    )

    # ========= TAB 1: REPORT & TESTS =========
    with tab_report:
        st.subheader("Parsed Test Results")
        st.caption("Values are compared against the reference ranges printed on the report.")
        st.dataframe(df, use_container_width=True)

    # ========= TAB 2: EXPLANATIONS =========
    with tab_expl:
        st.subheader("Explanations")

        col_en, col_mr = st.columns(2)

        with col_en:
            st.markdown("**English explanation**")
            st.text_area(
                label="",
                value=summary_en,
                height=260,
            )

        with col_mr:
            st.markdown("**मराठी स्पष्टीकरण**")
            st.text_area(
                label="",
                value=marathi_summary,
                height=260,
            )

        st.markdown("**Marathi Audio Preview**")
        if audio_bytes.getbuffer().nbytes > 0:
            st.audio(audio_bytes, format="audio/mp3")
        else:
            st.write("No audio available.")

        st.info(
            "The explanation only lists abnormal tests (high/low) plus a short overall summary "
            "and a safety disclaimer. It never gives a diagnosis or treatment advice."
        )

    # ========= TAB 3: WHATSAPP =========
    with tab_whatsapp:
        st.subheader("Send to patient on WhatsApp")

        selected_phone = ""
        if phones:
            st.markdown("**Detected phone numbers in the report**")
            selected_phone = st.selectbox(
                "Select the patient's WhatsApp number (or enter a different one):",
                options=[""] + phones,
                index=1 if len(phones) > 0 else 0,
            )
            manual_phone = st.text_input("Or enter a different mobile number (optional):")
            if manual_phone.strip():
                selected_phone = manual_phone.strip()
        else:
            st.write("No obvious mobile number could be detected in the text.")
            selected_phone = st.text_input("Enter the patient's WhatsApp number manually:")

        debug_to = format_phone_for_whatsapp(selected_phone) if selected_phone else "—"
        st.caption(f"Will send to WhatsApp number: **{debug_to}**")

        if not selected_phone:
            st.warning("Select or enter a WhatsApp number above to enable sending.")
        else:
            if st.button("Send Marathi text + audio on WhatsApp"):
                with st.spinner("Sending WhatsApp messages..."):
                    patient_name = "रुग्ण"  # or parse from PDF later
                    audio_bytes_value = (
                        audio_bytes.getvalue()
                        if audio_bytes.getbuffer().nbytes > 0
                        else None
                    )

                    # 1) Send template text
                    ok_text, msg_text = send_lab_summary_template(
                        selected_phone,
                        patient_name,
                        marathi_summary,
                    )

                    # 2) Send audio as separate WhatsApp media message
                    audio_ok = False
                    audio_msg = "No audio was generated."
                    if audio_bytes_value:
                        audio_ok, audio_msg = upload_media_and_send_audio(
                            selected_phone,
                            audio_bytes_value,
                        )

                # ---- UI messages ----
                if ok_text:
                    st.success(f"Text: {msg_text}")
                else:
                    st.error(f"Text: {msg_text}")

                if audio_bytes_value:
                    if audio_ok:
                        st.success(f"Audio: {audio_msg}")
                    else:
                        st.error(f"Audio: {audio_msg}")
                else:
                    st.info("No audio to send (Marathi summary was empty).")

        st.caption(
            "WhatsApp sending is currently configured for developer/test mode, "
            "so only approved test numbers will receive the message."
        )

if __name__ == "__main__":
    main()