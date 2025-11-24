import io
import re
# import List
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

load_dotenv()  

# Initialize once at app startup
base = GoogleTranslateBackend()
cfg = TranslationConfig(target_lang="mr")  # or "hi"
med_translator = SmartMedicalTranslator(base, cfg)


def get_explanation_in_marathi(english_explanation: str) -> str:
    return med_translator.translate_explanation(english_explanation)

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

        if df.empty:
            st.error(
                "Could not find any test table with numeric values and reference ranges. "
                "You may need to adjust the parsing logic for your lab's report format."
            )
        else:
                st.subheader("Parsed Test Results")
                st.dataframe(df)

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


                # Generate English summary
                st.subheader("English Summary")
                summary_en = generate_english_summary(df)
                st.text_area("English summary", value=summary_en, height=280)

                # ---------- Marathi translation + TTS (Step 2) ----------

                with st.spinner("Translating summary to Marathi and generating audio..."):
                    marathi_summary = translate_to_marathi(summary_en)

                st.subheader("Marathi Summary")
                st.text_area("मराठी सारांश", value=marathi_summary, height=260)

                audio_bytes = marathi_tts(marathi_summary)
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