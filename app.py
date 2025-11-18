import io
import re
import os
import requests
from typing import List, Tuple, Optional
import pdfplumber
import pandas as pd
import streamlit as st
from googletrans import Translator
from gtts import gTTS


# Utility functions

TABLE_SETTINGS_BORDERLESS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 3,
    "min_words_vertical": 2,
    "min_words_horizontal": 1,
}


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

def parse_range(cell:str)-> Tuple[Optional[float], Optional[float]]:
    """
    Parse a reference range like '12-15 g/dL' or '3.5 - 5.5 mmol/L'
    into (low, high). Returns (None, None) if parsing fails.
    """
    if cell is None:
        return None, None
    text= str(cell)
    text= text.replace("–", "-").replace("—", "-").replace("−", "-")
    nums = re.findall(r'\d+(?:\.\d+)?', text)
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    return None, None

def parse_value(cell:str)-> Optional[float]:
    """
    Parse a numeric value from a cell like '9.4 g/dL' or '<200 mg/dL'.
    Returns None if no number is found.
    """
    if cell is None:
        return None
    text = str(cell)
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    m = re.search(r'-?\d+(?:\.\d+)?', text)
    if m:
        try:
            return float(m.group())
        except ValueError:
            return None
    return None

def map_headers(headers: List[str]) -> dict:
    """
    Try to map raw table headers to canonical columns:
    test_name, value, unit, ref_range
    """
    canonical = {"test_name": None, "value": None, "unit": None, "ref_range": None}
    for idx, h in enumerate(headers):
        if not h:
            continue
        h_low = str(h).strip().lower()
        if any(k in h_low for k in ["test", "parameter", "investigation", "name"]):
            if canonical["test_name"] is None:
                canonical["test_name"] = idx
        elif any(k in h_low for k in ["result", "value", "observed"]):
            if canonical["value"] is None:
                canonical["value"] = idx
        elif any(k in h_low for k in ["unit", "units"]):
            if canonical["unit"] is None:
                canonical["unit"] = idx
        elif any(k in h_low for k in ["ref", "range", "normal"]):
            if canonical["ref_range"] is None:
                canonical["ref_range"] = idx
    return canonical

def classify_status(value: float,
                    low: Optional[float],
                    high: Optional[float]) -> str:
    """
    Compare value against (low, high) and return status string.
    """
    if value is None or low is None or high is None:
        return "unknown"
    if value < low:
        return "below"
    elif value > high:
        return "above"
    else:
        return "within"
    
def generate_english_summary(df: pd.DataFrame) -> str:
    """
    Generate a simple English explanation based purely on:
    - observed values
    - reference ranges present on the report

    Only includes tests where the value is BELOW or ABOVE
    the reference range. Normal tests are not listed.
    """
    # Filter to abnormal results only
    abnormal = df[df["Status"].isin(["below", "above"])]

    lines = []

    if abnormal.empty:
        lines.append(
            "All the test values in your report are within the reference ranges "
            "printed on the lab report."
        )
    else:
        lines.append(
            "Here is a summary of the test results that are outside the "
            "reference ranges shown on your lab report:\n"
        )

        for _, row in abnormal.iterrows():
            test_name = row.get("Test Name", "")
            value = row.get("Value", "")
            unit = row.get("Unit", "")
            ref_low = row.get("Ref Low", "")
            ref_high = row.get("Ref High", "")
            status = row.get("Status", "unknown")

            if status == "below":
                status_text = "This is below the reference range."
            elif status == "above":
                status_text = "This is above the reference range."
            else:
                # We shouldn't hit this because of the filter, but just in case
                continue

            line = (
                f"- {test_name}: your value is {value} {unit}. "
                f"The reference range on your report is {ref_low}–{ref_high} {unit}. "
                f"{status_text}"
            )
            lines.append(line)

    lines.append(
        "\nThis summary is based only on the values and reference ranges printed on your "
        "lab report. It does not provide any medical advice. Please consult your doctor "
        "at Sanjivani Hospital to understand your results and any next steps."
    )

    return "\n".join(lines)


# Core pdf parsing logic

def extract_tests_from_pdf(file_bytes: bytes) -> Tuple[pd.DataFrame, str]:
    """
    Open a PDF from bytes, extract:
    - tests table(s) with test_name, value, unit, ref_low, ref_high, status
    - full text (for phone extraction)
    Returns (dataframe, full_text).

    Strategy:
    1. Try pdfplumber table extraction (borderless settings).
    2. If that yields nothing, fall back to line-based parsing on full_text.
    """
    all_rows = []
    full_text_parts = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            full_text_parts.append(text)

            # Try to extract tables using text-based strategy
            tables = page.extract_tables(table_settings=TABLE_SETTINGS_BORDERLESS)

            for raw_table in tables:
                if not raw_table or len(raw_table) < 2:
                    continue

                headers = raw_table[0]
                mapping = map_headers(headers)

                # We need at least test_name, value, and ref_range columns to be useful
                if not (mapping["test_name"] is not None and
                        mapping["value"] is not None and
                        mapping["ref_range"] is not None):
                    continue

                for row in raw_table[1:]:
                    if not any(row):
                        continue

                    try:
                        test_name = row[mapping["test_name"]]
                        value_raw = row[mapping["value"]]
                        unit = row[mapping["unit"]] if mapping["unit"] is not None else ""
                        ref_raw = row[mapping["ref_range"]]
                    except IndexError:
                        continue

                    value = parse_value(value_raw)
                    ref_low, ref_high = parse_range(ref_raw)

                    if value is None or ref_low is None or ref_high is None:
                        continue

                    status = classify_status(value, ref_low, ref_high)

                    all_rows.append(
                        {
                            "Test Name": str(test_name).strip(),
                            "Value": value,
                            "Unit": str(unit).strip(),
                            "Ref Low": ref_low,
                            "Ref High": ref_high,
                            "Status": status,
                        }
                    )

    full_text = "\n".join(full_text_parts)

    # If table-based extraction failed, fall back to line-based parsing
    if not all_rows:
        df = extract_tests_from_text(full_text)
    else:
        df = pd.DataFrame(all_rows)

    return df, full_text

def extract_tests_from_text(full_text: str) -> pd.DataFrame:
    """
    Fallback parser when table extraction fails.

    Generic strategy:
    - For each line that contains numbers:
      - Test name = text before the first number
      - Value    = first number
      - Ref low  = second-last number
      - Ref high = last number

    Assumes a pattern like:
        Hemoglobin      9.4 g/dL      12 - 15
        Fasting Glucose 88 mg/dL      70 - 100
    or similar.
    """
    rows = []
    num_pattern = r'-?\d+(?:\.\d+)?'

    for line in full_text.splitlines():
        raw_line = line
        line = line.strip()
        if not line:
            continue

        # Skip obvious header lines
        lower = line.lower()
        if any(
            kw in lower
            for kw in ["test", "parameter", "investigation", "result", "value", "reference", "normal", "unit"]
        ):
            continue

        # Must contain at least 3 numbers (value + low + high)
        nums = re.findall(num_pattern, line)
        if len(nums) < 3:
            continue

        # Test name = text before the first number
        first_num_match = re.search(num_pattern, line)
        if not first_num_match:
            continue

        test_name = line[: first_num_match.start()].strip()
        if not test_name:
            continue

        try:
            value = float(nums[0])
            ref_low = float(nums[-2])
            ref_high = float(nums[-1])
        except ValueError:
            continue

        # Ensure we have a sane range; swap if clearly reversed
        if ref_low > ref_high:
            ref_low, ref_high = ref_high, ref_low

        # Heuristic: ignore if all three numbers are identical
        if value == ref_low == ref_high:
            continue

        # Unit = text between first and second numbers (best-effort)
        rest_after_value = line[first_num_match.end():]
        second_num_match = re.search(num_pattern, rest_after_value)
        unit = ""
        if second_num_match:
            unit = rest_after_value[: second_num_match.start()].strip()

        status = classify_status(value, ref_low, ref_high)

        rows.append(
            {
                "Test Name": test_name,
                "Value": value,
                "Unit": unit,
                "Ref Low": ref_low,
                "Ref High": ref_high,
                "Status": status,
            }
        )

    return pd.DataFrame(rows)

# Translation + TTS

translator = Translator()


def translate_to_marathi(text: str) -> str:
    """
    Translate English text to Marathi using googletrans.
    You can later swap this out for a local model or official API.
    """
    text = (text or "").strip()
    if not text:
        return ""
    try:
        result = translator.translate(text, src="en", dest="mr")
        return result.text
    except Exception as exc:  # pragma: no cover
        # Fallback: return original text with a note
        return f"[Translation error: {exc}] {text}"


def marathi_tts(text: str) -> io.BytesIO:
    """
    Convert Marathi text to speech (MP3) using gTTS.
    Returns a BytesIO object that Streamlit can play.
    """
    buf = io.BytesIO()
    if not text.strip():
        return buf
    tts = gTTS(text=text, lang="mr")
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf

# WhatsApp Cloud API helpers 

def format_phone_for_whatsapp(phone: str) -> str:
    """
    Convert a detected Indian number into WhatsApp E.164 format.
    Examples:
      '9876543210' -> '919876543210'
      '+91 9876543210' -> '919876543210'
    """
    digits = re.sub(r"\D", "", phone)
    # If it starts with 0 and length 11, strip leading 0
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    # If already starts with '91' and total length 12, assume it's ok
    if digits.startswith("91") and len(digits) == 12:
        return digits
    # If length 10 (local), prepend '91'
    if len(digits) == 10:
        return "91" + digits
    # Fallback: return as-is
    return digits


def send_whatsapp_text(phone: str, text: str) -> Tuple[bool, str]:
    """
    Send a simple text message via WhatsApp Cloud API.
    Returns (success, message_or_error).
    """
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("PHONE_NUMBER_ID")

    if not token or not phone_number_id:
        return False, "WhatsApp credentials are not set in environment variables."

    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": format_phone_for_whatsapp(phone),
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text,
        },
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    if resp.status_code >= 200 and resp.status_code < 300:
        return True, "Text message sent successfully."
    return False, f"Error from WhatsApp API: {resp.status_code} {resp.text}"


def upload_media_and_send_audio(phone: str, audio_bytes: bytes) -> Tuple[bool, str]:
    """
    Upload an MP3 audio file as media and send it as an audio message.
    Uses WhatsApp Cloud API /media + /messages.
    """
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    if not token or not phone_number_id:
        return False, "WhatsApp credentials are not set in environment variables."

    # 1) Upload media
    media_url = "https://graph.facebook.com/v20.0/" + phone_number_id + "/media"

    files = {
        "file": ("summary.mp3", audio_bytes, "audio/mpeg"),
    }
    data = {
        "messaging_product": "whatsapp",
    }
    headers = {
        "Authorization": f"Bearer {token}",
    }

    media_resp = requests.post(media_url, headers=headers, files=files, data=data, timeout=30)
    if media_resp.status_code < 200 or media_resp.status_code >= 300:
        return False, f"Error uploading media: {media_resp.status_code} {media_resp.text}"

    media_id = media_resp.json().get("id")
    if not media_id:
        return False, "No media ID returned from WhatsApp API."

    # 2) Send audio message referencing media_id
    msg_url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    msg_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    msg_payload = {
        "messaging_product": "whatsapp",
        "to": format_phone_for_whatsapp(phone),
        "type": "audio",
        "audio": {
            "id": media_id,
        },
    }

    msg_resp = requests.post(msg_url, headers=msg_headers, json=msg_payload, timeout=15)
    if msg_resp.status_code >= 200 and msg_resp.status_code < 300:
        return True, "Audio message sent successfully."
    return False, f"Error sending audio message: {msg_resp.status_code} {msg_resp.text}"


# Streamlit app UI

def main():
    st.set_page_config(page_title="Lab Report Explainer", page_icon="🧪")
    st.title("🧪 Lab Report Explainer")
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
                st.text_area("मराठी सारांश", value=marathi_summary, height=280)

                audio_bytes = marathi_tts(marathi_summary)
                st.subheader("Marathi Audio (Text-to-Speech)")
                if audio_bytes.getbuffer().nbytes > 0:
                    st.audio(audio_bytes, format="audio/mp3")
                else:
                    st.write("No audio available.")

                st.subheader("Send to Patient on WhatsApp")

                if not selected_phone:
                    st.warning("Select or enter a WhatsApp number above to enable sending.")
                else:
                    if st.button("Send Marathi text + audio on WhatsApp"):
                        with st.spinner("Sending WhatsApp messages..."):
                            # 1) Send text
                            ok_text, msg_text = send_whatsapp_text(selected_phone, marathi_summary)

                            # 2) Send audio, only if TTS produced something
                            audio_ok = False
                            audio_msg = "Audio was not generated."
                            if audio_bytes.getbuffer().nbytes > 0:
                                audio_ok, audio_msg = upload_media_and_send_audio(
                                    selected_phone,
                                    audio_bytes.getvalue(),
                                )

                        # Show results
                        if ok_text:
                            st.success(f"Text: {msg_text}")
                        else:
                            st.error(f"Text: {msg_text}")

                        if audio_ok:
                            st.success(f"Audio: {audio_msg}")
                        else:
                            st.error(f"Audio: {audio_msg}")

                st.info(
                    "This is Phase 2: English summary + Marathi translation and audio preview. "
                    "In the next step, we'll send this text and audio to the patient's WhatsApp number."
                )



if __name__ == "__main__":
    main()