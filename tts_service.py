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


@dataclass
class TTSConfig:
    lang: str = "mr"
    slow: bool = False
    output_dir: str = "tts_outputs"
    max_chars_per_chunk: int = 220  # gTTS + WhatsApp friendly


class TTSFormatter:
    """
    Makes text more TTS-friendly:
    - ensures clear sentence boundaries
    - inserts line breaks between logical parts
    - optionally chunks long text
    """

    def split_sentences(self, text: str) -> List[str]:
        # Simple sentence splitter for Marathi/Hindi/English-ish text
        parts = re.split(r"([.!?])", text)
        sentences = []
        current = ""
        for part in parts:
            current += part
            if part in [".", "?", "!"]:
                sentences.append(current.strip())
                current = ""
        if current.strip():
            sentences.append(current.strip())
        return [s for s in sentences if s]

    def format_for_tts(self, text: str) -> str:
        """
        Return a formatted string where each sentence is on its own line.
        Newlines usually give nicer pauses.
        """
        sentences = self.split_sentences(text)
        return "\n".join(sentences)

    def chunk_for_tts(self, text: str, max_chars: int) -> List[str]:
        """
        In case text is too long, break into smaller chunks.
        """
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
        """
        Convert text to one or more MP3 files (if long).
        Returns list of file paths.
        """
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
