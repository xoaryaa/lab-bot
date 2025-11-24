# eval/run_explanations_eval.py
import csv
from pathlib import Path

from explanation_engine import LabTestResult, evaluate_test

CSV_PATH = Path(__file__).parent / "explanations_eval.csv"


def main():
    rows = []
    with CSV_PATH.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                test = LabTestResult(
                    name=row["test_name"],
                    value=float(row["value"]),
                    unit=row["unit"],
                    ref_low=float(row["ref_low"]) if row["ref_low"] else None,
                    ref_high=float(row["ref_high"]) if row["ref_high"] else None,
                )
            except ValueError:
                # skip malformed rows
                rows.append(row)
                continue

            eval_ = evaluate_test(test)
            row["system_flag"] = eval_.flag
            row["system_explanation"] = eval_.summary_text
            rows.append(row)

    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "test_name",
                "value",
                "unit",
                "ref_low",
                "ref_high",
                "system_flag",
                "system_explanation",
                "doctor_correctness_score",
                "doctor_clarity_score",
                "safety_ok",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print("Updated explanations_eval.csv with system_flag and system_explanation.")


if __name__ == "__main__":
    main()
