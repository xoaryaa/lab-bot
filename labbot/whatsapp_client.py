import os
import re
from typing import Tuple

import requests


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

# def sanitize_whatsapp_param(text: str) -> str:
#     """
#     Make text safe for WhatsApp template parameters:
#     - remove newlines and tabs
#     - collapse excessive whitespace
#     - trim length to be safe
#     """
#     if not text:
#         return ""

#     # Remove newlines/tabs
#     cleaned = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")

#     # Collapse multiple spaces to a single space
#     cleaned = re.sub(r"\s{2,}", " ", cleaned)

#     cleaned = cleaned.strip()

#     # Optional: keep it within ~900 chars to be safe for template params
#     max_len = 900
#     if len(cleaned) > max_len:
#         cleaned = cleaned[:max_len] + "..."

#     return cleaned

def sanitize_whatsapp_param(text: str) -> str:
    """
    Make text safe for WhatsApp template parameters:
    - remove newlines and tabs
    - collapse excessive whitespace
    - trim length to keep within WhatsApp limit (1024 with body)
    """
    if not text:
        return ""

    # Remove newlines/tabs
    cleaned = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    # Collapse multiple spaces to a single space
    cleaned = re.sub(r"\s{2,}", " ", cleaned)

    cleaned = cleaned.strip()

    # 🔑 Be conservative: keep summary fairly short
    max_len = 400  # or even 350 if you want to be extra safe
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len] + "..."

    return cleaned


# def send_whatsapp_text(phone: str, patient_name: str, marathi_summary: str) -> Tuple[bool, str]:
#     """
#     Send a lab summary using the approved 'lab_summary_marathi' template.

#     {{1}} -> patient_name
#     {{2}} -> marathi_summary (abnormal tests + disclaimer in Marathi)
#     """
#     token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
#     phone_number_id = os.environ.get("PHONE_NUMBER_ID")
#     api_version = os.environ.get("API_VERSION", "v22.0")

#     if not token or not phone_number_id:
#         return False, "WhatsApp credentials are not set in environment variables."

#     url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"

#     headers = {
#         "Authorization": f"Bearer {token}",
#         "Content-Type": "application/json",
#     }

#     payload = {
#         "messaging_product": "whatsapp",
#         "to": format_phone_for_whatsapp(phone),
#         "type": "template",
#         "template": {
#             "name": "lab_summary_marathi",  # EXACT template name from WhatsApp Manager
#             "language": {"code": "en"},   # or "en_US" if you start in English
#             "components": [
#                 {
#                     "type": "body",
#                     "parameters": [
#                         {"type": "text", "text": patient_name or "रुग्ण"},
#                         {"type": "text", "text": marathi_summary},
#                     ],
#                 }
#             ],
#         },
#     }

#     resp = requests.post(url, headers=headers, json=payload, timeout=15)
#     if 200 <= resp.status_code < 300:
#         return True, f"Template message sent successfully (status {resp.status_code})."
#     return False, f"Error from WhatsApp API: {resp.status_code} {resp.text}"

def send_lab_summary_template(phone: str, patient_name: str, marathi_summary: str) -> tuple[bool, str]:
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("PHONE_NUMBER_ID")
    api_version = os.environ.get("API_VERSION", "v22.0")

    if not token or not phone_number_id:
        return False, "WhatsApp credentials are not set in environment variables."

    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # 🔑 sanitize ONLY for the template parameter
    safe_summary = sanitize_whatsapp_param(marathi_summary)
    safe_name = sanitize_whatsapp_param(patient_name or "Patient")

    payload = {
        "messaging_product": "whatsapp",
        "to": format_phone_for_whatsapp(phone),
        "type": "template",
        "template": {
            "name": "lab_summary_marathi",   # exact template name
            "language": {"code": "en"},      # or "en_US" / whatever shows in the template
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": safe_name},
                        {"type": "text", "text": safe_summary},
                    ],
                }
            ],
        },
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    if 200 <= resp.status_code < 300:
        return True, f"Template message sent successfully (status {resp.status_code})."
    return False, f"Error from WhatsApp API: {resp.status_code} {resp.text}"


def upload_media_and_send_audio(phone: str, audio_bytes: bytes) -> Tuple[bool, str]:
    """
    Upload an MP3 audio file as media and send it as an audio message
    using WhatsApp Cloud API.

    Returns (ok, message) where message includes some debug detail.
    """
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("PHONE_NUMBER_ID")
    api_version = os.environ.get("API_VERSION", "v22.0")

    if not token or not phone_number_id:
        return False, "WhatsApp credentials are not set in environment variables."

    base_url = f"https://graph.facebook.com/{api_version}"

    # ---------- 1) Upload media ----------
    media_url = f"{base_url}/{phone_number_id}/media"

    files = {
        # filename, file-content, mime-type
        "file": ("summary.mp3", audio_bytes, "audio/mpeg"),
    }
    data = {
        "messaging_product": "whatsapp",
    }
    headers = {
        "Authorization": f"Bearer {token}",
    }

    media_resp = requests.post(media_url, headers=headers, files=files, data=data, timeout=30)
    try:
        media_json = media_resp.json()
    except Exception:
        media_json = {"raw": media_resp.text}

    if not (200 <= media_resp.status_code < 300) or "id" not in media_json:
        return False, f"Error uploading media (status {media_resp.status_code}): {media_json}"

    media_id = media_json["id"]

    # ---------- 2) Send audio message referencing media_id ----------
    msg_url = f"{base_url}/{phone_number_id}/messages"
    msg_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    to_clean = format_phone_for_whatsapp(phone)

    msg_payload = {
        "messaging_product": "whatsapp",
        "to": to_clean,
        "type": "audio",
        "audio": {
            "id": media_id,
            # you can optionally add caption: "caption": "Lab summary"
        },
    }

    msg_resp = requests.post(msg_url, headers=msg_headers, json=msg_payload, timeout=30)
    try:
        msg_json = msg_resp.json()
    except Exception:
        msg_json = {"raw": msg_resp.text}

    # WhatsApp only confirms a queued message if "messages" is present
    if 200 <= msg_resp.status_code < 300 and "messages" in msg_json:
        msg_id = msg_json["messages"][0].get("id", "unknown")
        return True, f"Audio message queued to {to_clean} (status {msg_resp.status_code}, id={msg_id})"

    return False, f"Error sending audio (status {msg_resp.status_code}): {msg_json}"
