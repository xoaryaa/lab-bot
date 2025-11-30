# tts_service.py
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List
from uuid import uuid4

from gtts import gTTS


LANG_CODE_TTS = {
    "mr": "mr",  # Marathi
    "hi": "hi",  # Hindi
}

DECIMAL_PATTERN = re.compile(r"\b(\d+)\s*\.\s*(\d+)\b")



def normalize_numbers_for_tts(text: str) -> str:
    
    def _repl(match: re.Match) -> str:
        int_part = match.group(1)
        frac_part = match.group(2)

        # drop trailing .0
        if set(frac_part) == {"0"}:
            return int_part

        # otherwise say "int point frac"
        return f"{int_part} point {frac_part}"

    return DECIMAL_PATTERN.sub(_repl, text)


@dataclass
class TTSConfig:
    lang: str = "mr"
    slow: bool = False
    output_dir: str = "tts_outputs"
    max_chars_per_chunk: int = 220  # gTTS + WhatsApp friendly


class TTSFormatter:
    
    def split_sentences(self, text: str) -> List[str]:

        # This regex only treats '.' as a sentence boundary if it is NOT between digits.
        # (?<!\d)\.(?!\d)  -> dot not preceded by digit and not followed by digit
        pattern = re.compile(r"([!?])|(?<!\d)\.(?!\d)")

        sentences = []
        start = 0

        for match in pattern.finditer(text):
            end = match.start()
            # The matched punctuation itself:
            punct = match.group(0)

            # Sentence text is from last start to this match
            segment = text[start:end].strip()
            if segment:
                sentences.append(segment + punct)
            start = match.end()

        # leftover
        tail = text[start:].strip()
        if tail:
            sentences.append(tail)

        return sentences


    def format_for_tts(self, text: str) -> str:
        
        # 1) normalize decimals so they read nicely
        text = normalize_numbers_for_tts(text)

        # 2) split into sentences using the improved splitter
        sentences = self.split_sentences(text)

        # 3) join each sentence on its own line to create natural pauses
        return "\n".join(s.strip() for s in sentences if s.strip())


    def chunk_for_tts(self, text: str, max_chars: int) -> List[str]:
        
        formatted = self.format_for_tts(text)
        lines = formatted.split("\n")
        chunks = []
        current = ""

        for line in lines:
            # +1 for newline
            if len(current) + len(line) + 1 > max_chars:
                if current:
                    chunks.append(current.strip())
                    current = ""
            current += line + "\n"

        if current.strip():
            chunks.append(current.strip())

        return chunks


class TTSService:
    def __init__(self, config: TTSConfig):
        self.config = config
        self.formatter = TTSFormatter()
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)

    def text_to_speech_files(self, text: str, filename_prefix: str = "lab_explanation") -> List[Path]:
        
        lang_code = LANG_CODE_TTS.get(self.config.lang, self.config.lang)
        chunks = self.formatter.chunk_for_tts(text, self.config.max_chars_per_chunk)

        paths: List[Path] = []
        for i, chunk in enumerate(chunks):
            tts = gTTS(chunk, lang=lang_code, slow=self.config.slow)
            unique_id = uuid4().hex[:8]
            name = f"{filename_prefix}_{i+1}_{unique_id}.mp3"
            out_path = Path(self.config.output_dir) / name
            tts.save(str(out_path))
            paths.append(out_path)

        return paths
