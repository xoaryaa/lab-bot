import io
import re
import pandas as pd
import streamlit as st
import os
import requests
from typing import List
from parser import extract_tests_from_pdf
from summary import generate_english_summary
from translation_tts import translate_to_marathi, marathi_tts
from whatsapp import send_lab_summary_template, upload_media_and_send_audio, format_phone_for_whatsapp
from dotenv import load_dotenv
from translator import SmartMedicalTranslator, GoogleTranslateBackend, TranslationConfig
from tts_service import TTSService, TTSConfig
from explanation_engine import LabTestResult, evaluate_report
load_dotenv()  

# ---- Global translation + TTS services ----

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
    """
    Use explanation_engine to generate a full English explanation:
    - per-test summaries
    - overall summary
    - safety notice
    """
    tests = df_to_labtests(df)

    # ---- FINAL SAFETY CLEANING FOR UNITS ----
    # Drop junk like "M:" / "F:" even if they slipped through df_to_labtests
    for t in tests:
        if t.unit is None:
            continue
        u = t.unit.strip()
        if u in ("M:", "F:", ":"):
            t.unit = ""

    report = evaluate_report(tests)

    parts: List[str] = []

    # per-test explanations
    for ev in report["evaluations"]:
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

    st.set_page_config(page_title="Lab Report Explainer", page_icon="🧪")
    st.title("🧪 Lab Report Explainer")
    wh_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    wh_num_id = os.environ.get("PHONE_NUMBER_ID")
    if not wh_token or not wh_num_id:
        st.warning("WhatsApp env vars not set. Sending will fail until you configure them.")

    st.write(
        "Upload a digital lab report PDF. The app will extract test values and compare them "
        "with the reference ranges printed on the report, then generate a simple summary "
        "without any diagnosis or medical advice."
    )

    uploaded_file = st.file_uploader("Upload lab report PDF", type=["pdf"])

    if uploaded_file is not None:
         # Use getvalue() so it works across reruns
        file_bytes = uploaded_file.getvalue()

        with st.spinner("Reading and analysing the report..."):
            df, full_text = extract_tests_from_pdf(file_bytes)
            # Try to enrich units from the raw PDF text
            df = fill_units_from_full_text(df, full_text)


        if df.empty:
            st.error(
                "Could not find any test table with numeric values and reference ranges. "
                "You may need to adjust the parsing logic for your lab's report format."
            )
        else:
                st.subheader("Parsed Test Results")
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

                st.dataframe(display_df)


                # ------ Phone detection + selection ------

                phones = extract_phone_numbers(full_text)
                st.subheader("Detected Phone Numbers in Report")
                selected_phone = ""

                if phones:
                    st.write("Possible patient contact numbers found in the report:")
                    selected_phone = st.selectbox(
                        "Select the patient's WhatsApp number (or type a different one):",
                        options=[""] + phones,
                        index=1 if len(phones) > 0 else 0,
                    )
                    manual_phone = st.text_input("Or enter a different mobile number (optional):")

                    if manual_phone.strip():
                        selected_phone = manual_phone.strip()
                else:
                    st.write("No obvious mobile number could be detected in the text.")
                    selected_phone = st.text_input("Enter the patient's WhatsApp number manually:")


                # Generate English explanation using rule-based engine (explanation_engine)
                st.subheader("English Explanation")
                summary_en = build_english_explanation_from_df(df)
                st.text_area("English explanation", value=summary_en, height=280)

                # ---------- Marathi translation + TTS (Step 2) ----------

                with st.spinner("Translating explanation to Marathi and generating audio..."):
                    marathi_summary = smart_medical_translator.translate_explanation(summary_en)

                st.subheader("Marathi Explanation")
                st.text_area("मराठी स्पष्टीकरण", value=marathi_summary, height=260)

                # Use TTSService to generate MP3, then wrap first one into BytesIO
                # already imported at top, so only needed if it’s not there

                audio_bytes = io.BytesIO()
                audio_paths = tts_service.text_to_speech_files(
                    marathi_summary,
                    filename_prefix="ui_preview",
                )

                if audio_paths:
                    first_path = audio_paths[0]
                    with open(first_path, "rb") as f:
                        audio_bytes = io.BytesIO(f.read())
                        audio_bytes.seek(0)

                st.subheader("Marathi Audio (Text-to-Speech)")
                if audio_bytes.getbuffer().nbytes > 0:
                    st.audio(audio_bytes, format="audio/mp3")
                else:
                    st.write("No audio available.")

                # ------ WhatsApp send button ------
                
                st.subheader("Send to Patient on WhatsApp")

                debug_to = format_phone_for_whatsapp(selected_phone)
                st.write("Will send to WhatsApp number:", debug_to)

                # col1, col2 = st.columns(2)

                # with col1:
                if not selected_phone:
                    st.warning("Select or enter a WhatsApp number above to enable sending.")
                else:
                    if st.button("Send Marathi text + audio on WhatsApp"):
                        with st.spinner("Sending WhatsApp messages..."):
                                # ok_text, msg_text= send_whatsapp_text(selected_phone, marathi_summary)
                            patient_name = "रुग्ण"  # or parse from PDF later
                                # ok_text, msg_text = send_whatsapp_text(selected_phone, patient_name, marathi_summary)
                                # patient_name = "Patient"  # or parse from PDF later
                            ok_text, msg_text = send_lab_summary_template(
                                selected_phone,
                                patient_name,
                                marathi_summary,
                            )

                            audio_ok = False
                            audio_msg = "Audio was not generated."
                            if audio_bytes.getbuffer().nbytes > 0:
                                audio_ok, audio_msg = upload_media_and_send_audio(
                                    selected_phone,
                                    audio_bytes.getvalue(),
                                )
                        if ok_text:
                            audio_ok, audio_msg = upload_media_and_send_audio(
                                selected_phone,
                                audio_bytes.getvalue(),
                            )

                        if ok_text:
                            st.success(f"Text: {msg_text}")
                        else:
                            st.error(f"Text: {msg_text}")
                        st.caption("WhatsApp API response for text:")
                            # st.json(resp_json)

                        if audio_ok:
                            st.success(f"Audio: {audio_msg}")
                        else:
                            st.error(f"Audio: {audio_msg}")

                # with col2:
                #     if st.button("Send hello_world template (debug)"):
                #         with st.spinner("Sending hello_world template via Python..."):
                #             ok_tpl, msg_tpl, tpl_json = send_whatsapp_hello_world_template(selected_phone)

                #         if ok_tpl:
                #             st.success(f"Template: {msg_tpl}")
                #         else:
                #             st.error(f"Template: {msg_tpl}")
                #         st.caption("WhatsApp API response for hello_world template:")
                #         st.json(tpl_json)

                st.info(
                    "This is Phase 2: English summary + Marathi translation and audio preview. "
                    "In the next step, we'll send this text and audio to the patient's WhatsApp number."
                )

if __name__ == "__main__":
    main()