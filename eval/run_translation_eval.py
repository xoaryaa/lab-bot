# eval/run_translation_eval.py
import csv
from pathlib import Path

from labbot.translator import SmartMedicalTranslator, GoogleTranslateBackend, TranslationConfig


CSV_PATH = Path(__file__).parent / "translation_eval.csv"


def main():
    base = GoogleTranslateBackend()
    cfg = TranslationConfig(target_lang="mr")  # change to "hi" for Hindi
    translator = SmartMedicalTranslator(base, cfg)

    rows = []
    with CSV_PATH.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            en_text = row["english_text"]
            target_lang = row["target_lang"].strip() or "mr"

            # if you want per-row language:
            cfg.target_lang = target_lang

            system_out = translator.translate_explanation(en_text)
            row["system_output"] = system_out
            rows.append(row)

    # Write back to the same file (or a new file if you prefer)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "english_text",
                "target_lang",
                "reference_translation",
                "system_output",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print("Updated translation_eval.csv with system_output for all rows.")


if __name__ == "__main__":
    main()