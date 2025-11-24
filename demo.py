# demo_pipeline.py
from explanation_engine import LabTestResult, evaluate_report
from translator import SmartMedicalTranslator, GoogleTranslateBackend, TranslationConfig
from tts_service import TTSService, TTSConfig


def build_english_text(tests):
    report = evaluate_report(tests)

    parts = []
    # per-test explanations
    for ev in report["evaluations"]:
        parts.append(ev.summary_text)

    # overall summary + safety notice
    if report["overall_summary_en"]:
        parts.append(report["overall_summary_en"])
    if report["category_summary_en"]:
        parts.append(report["category_summary_en"])
    if report["safety_notice_en"]:
        parts.append(report["safety_notice_en"])

    full_en = " ".join(parts)
    return full_en, report


def main():
    # ---- 1. Fake lab results (later this will come from parser.py) ----
    tests = [
        LabTestResult(
            name="fasting blood sugar",
            value=134.0,
            unit="mg/dL",
            ref_low=70.0,
            ref_high=110.0,
        ),
        LabTestResult(
            name="total cholesterol",
            value=210.0,
            unit="mg/dL",
            ref_low=0.0,
            ref_high=200.0,
        ),
    ]

    # ---- 2. English explanation using rule-based engine ----
    full_en_text, report = build_english_text(tests)
    print("=== English explanation ===")
    print(full_en_text)
    print()

    # ---- 3. Translate to Marathi/Hindi ----
    base = GoogleTranslateBackend()
    tr_cfg = TranslationConfig(target_lang="mr")  # "mr" for Marathi, "hi" for Hindi
    med_translator = SmartMedicalTranslator(base, tr_cfg)

    full_mr_text = med_translator.translate_explanation(full_en_text)
    print("=== Marathi/Hindi explanation ===")
    print(full_mr_text)
    print()

    # ---- 4. TTS: generate mp3(s) ----
    tts_cfg = TTSConfig(lang="mr", slow=False, output_dir="tts_outputs")
    tts = TTSService(tts_cfg)

    audio_paths = tts.text_to_speech_files(full_mr_text, filename_prefix="demo_report")
    print("=== Audio files created ===")
    for p in audio_paths:
        print(p)


if __name__ == "__main__":
    main()
