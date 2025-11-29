import re
from dataclasses import dataclass
from typing import Dict, Tuple, List
# from googletrans import Translator 
import requests


# ---------- 1. Number & unit masking ----------

RANGE_PATTERN = re.compile(
    r"\b(\d+(\.\d+)?)\s*[-–]\s*(\d+(\.\d+)?)(\s*[a-zA-Z/%]+)?"
)
VALUE_PATTERN = re.compile(
    r"\b(\d+(\.\d+)?)(\s*[a-zA-Z/%]+)\b"
)


def mask_numbers_and_units(text: str) -> Tuple[str, Dict[str, str]]:
    """
    Replace numeric values and ranges (with units) with placeholders.
    Returns (masked_text, mask_dict).
    """
    masks: Dict[str, str] = {}

    def _repl(match: re.Match) -> str:
        key = f"__VAL_{len(masks)}__"
        masks[key] = match.group(0)
        return key

    # First mask ranges, then single values
    text = RANGE_PATTERN.sub(_repl, text)
    text = VALUE_PATTERN.sub(_repl, text)

    return text, masks


def unmask_numbers_and_units(text: str, masks: Dict[str, str]) -> str:
    """
    Replace placeholders back with original numeric strings.
    """
    for key, value in masks.items():
        text = text.replace(key, value)
    return text


# ---------- 2. Glossary & post-processing ----------

# for now hardcode; later load from JSON/YAML file.
GLOSSARY = {
    "fasting blood sugar": {
        "mr": "उपासाचा रक्तातील साखर",
        "hi": "उपवास के समय की रक्त शर्करा",
    },
    "slightly high": {
        "mr": "थोडी जास्त आहे",
        "hi": "थोड़ी अधिक है",
    },
    "normal": {
        "mr": "सामान्य आहे",
        "hi": "सामान्य है",
    },
    "please show this report to your doctor": {
        "mr": "कृपया ही चाचणी तुमच्या डॉक्टरांना दाखवा.",
        "hi": "कृपया यह जांच अपने डॉक्टर को दिखाएँ।",
    },
}


def apply_glossary(
    original_en: str,
    translated_text: str,
    target_lang: str = "mr",
) -> str:
    """
    Ensure key medical phrases follow our controlled translations.
    We look at the EN original to decide which phrases to enforce.
    """
    lang_key = target_lang

    # Very simple approach:
    # if an English phrase appears in the original,
    # force-insert the corresponding translation if we can locate a rough spot.
    for en_phrase, translations in GLOSSARY.items():
        if en_phrase.lower() in original_en.lower():
            desired = translations.get(lang_key)
            if not desired:
                continue

            # You can make this smarter later; for now just ensure the phrase appears.
            if desired not in translated_text:
                # Naively append; later you can replace approximate variants.
                translated_text += " " + desired

    return translated_text.strip()


# ---------- 3. Base translator interface ----------

class BaseTranslator:
    def translate(self, text: str, target_lang: str) -> str:
        raise NotImplementedError


class DummyEchoTranslator(BaseTranslator):
    """
    For testing our pipeline without real MT.
    Just returns the same text with a tag.
    """
    def translate(self, text: str, target_lang: str) -> str:
        return f"[{target_lang} MT HERE] {text}"

# ---------- 4. Smart medical translator ----------
@dataclass
class TranslationConfig:
    target_lang: str = "mr"
    max_sentence_len: int = 180  # for optional splitting later


class SmartMedicalTranslator:
    def __init__(self, base_translator: BaseTranslator, config: TranslationConfig):
        self.base_translator = base_translator
        self.config = config

    def translate_explanation(self, english_text: str) -> str:
        
        # 1. Mask numbers & units
        masked_text, masks = mask_numbers_and_units(english_text)

        # 2. Base translation
        raw_translated = self.base_translator.translate(
            masked_text,
            target_lang=self.config.target_lang,
        )

        # 3. Glossary post-processing
        glossed = apply_glossary(
            original_en=english_text,
            translated_text=raw_translated,
            target_lang=self.config.target_lang,
        )

        # 4. Unmask
        final_text = unmask_numbers_and_units(glossed, masks)

        # 5. Optional: enforce shorter sentences (you can refine later)
        final_text = self._shorten_sentences(final_text)

        return final_text

    def _shorten_sentences(self, text: str) -> str:
        """
        Very light heuristic: split very long sentences into 2.
        Keep it simple for now.
        """
        sentences = re.split(r"([.!?])", text)
        rebuilt = ""
        current = ""
        for part in sentences:
            current += part
            if part in [".", "?", "!"]:
                if len(current) > self.config.max_sentence_len:
                    # Split with a simple line break for TTS friendliness
                    rebuilt += current.strip() + "\n"
                else:
                    rebuilt += current.strip() + " "
                current = ""
        rebuilt += current
        return rebuilt.strip()
    
# ---------- 5. Google Translate backend (quick & dirty) ----------

LANG_CODE_MAP = {
    "mr": "mr",  # Marathi
    "hi": "hi",  # Hindi
}

class GoogleTranslateBackend(BaseTranslator):

    def __init__(self, timeout: int = 10, max_chars_per_chunk: int = 800):
        self.timeout = timeout
        self.max_chars_per_chunk = max_chars_per_chunk

    def _map_lang(self, target_lang: str) -> str:
        
        t = target_lang.lower()
        if t in ("mr", "marathi"):
            return "mr"
        if t in ("hi", "hindi"):
            return "hi"
        return t  # assume caller passed a valid code

    def _chunk_text(self, text: str) -> List[str]:
        """
        Split long text into smaller chunks at sentence boundaries,
        so the endpoint doesn't choke on very long strings.
        """
        text = text.strip()
        if not text:
            return [""]

        if len(text) <= self.max_chars_per_chunk:
            return [text]

        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: List[str] = []
        current = ""

        for s in sentences:
            if len(current) + len(s) + 1 > self.max_chars_per_chunk:
                if current:
                    chunks.append(current.strip())
                    current = ""
            current += s + " "

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def _translate_chunk(self, text: str, google_code: str) -> str:
        """
        Translate a single chunk using the unofficial Google Translate endpoint.
        """
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": google_code,
            "dt": "t",
            "q": text,
        }

        resp = requests.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        # data[0] is a list of [translated_text, original_text, ...] segments
        translated_parts: List[str] = []
        for seg in data[0]:
            if seg and seg[0]:
                translated_parts.append(seg[0])

        return "".join(translated_parts)

    def translate(self, text: str, target_lang: str) -> str:
        if not text:
            return ""

        google_code = self._map_lang(target_lang)
        chunks = self._chunk_text(text)

        out_chunks: List[str] = []
        for chunk in chunks:
            try:
                out_chunks.append(self._translate_chunk(chunk, google_code))
            except Exception as e:
                # this is what you see as "Technical details" in Streamlit
                raise RuntimeError(f"Translation failed for a chunk: {e}") from e

        return " ".join(out_chunks)