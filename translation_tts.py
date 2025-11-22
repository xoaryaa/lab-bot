import io

from googletrans import Translator
from gtts import gTTS


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
