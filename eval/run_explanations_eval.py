import pandas as pd
from labbot.explanation_engine import LabTestResult, evaluate_report

INPUT_CSV = "eval/explanations_eval_clean.csv"
OUTPUT_CSV = "eval/explanations_eval_labbot.csv"

def make_explanation_row(row: pd.Series) -> tuple[str, str]:
    test = LabTestResult(
        name=str(row["test_name"]),
        value=float(row["value"]),
        unit=str(row["unit"]),
        ref_low=float(row["ref_low"]) if pd.notna(row["ref_low"]) else None,
        ref_high=float(row["ref_high"]) if pd.notna(row["ref_high"]) else None,
    )
    report = evaluate_report([test])
    ev = report["evaluations"][0]

    # your engine should already set severity/flag + summary_text
    labbot_flag = getattr(ev, "flag", getattr(ev, "severity", "unknown"))
    labbot_explanation = ev.summary_text
    return labbot_flag, labbot_explanation

def main():
    df = pd.read_csv(INPUT_CSV)

    flags = []
    explanations = []

    for _, row in df.iterrows():
        flag, expl = make_explanation_row(row)
        flags.append(flag)
        explanations.append(expl)

    df["labbot_flag"] = flags
    df["labbot_explanation"] = explanations

    # leave doctor_* and safety_ok as-is (blank) for your dad to fill
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Wrote {len(df)} rows to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
