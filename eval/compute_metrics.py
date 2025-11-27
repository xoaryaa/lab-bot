import pandas as pd

CSV_PATH = "eval/explanations_eval_labbot.csv"

def main():
    df = pd.read_csv(CSV_PATH)

    # Make sure scores are numeric
    for col in ["doctor_correctness_score", "doctor_clarity_score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Normalise safety_ok to boolean
    if df["safety_ok"].dtype == object:
        df["safety_ok"] = df["safety_ok"].str.strip().str.lower().map(
            {"yes": True, "y": True, "true": True, "1": True}
        )
    n = len(df)
    avg_correctness = df["doctor_correctness_score"].mean()
    avg_clarity = df["doctor_clarity_score"].mean()
    safety_rate = df["safety_ok"].mean()  # fraction of True

    # Strict “good explanation” rate:
    # correctness ≥ 4, clarity ≥ 4, and marked safe
    good_mask = (
        (df["doctor_correctness_score"] >= 4)
        & (df["doctor_clarity_score"] >= 4)
        & (df["safety_ok"] == True)
    )
    good_rate = good_mask.mean()

    print("=== Overall metrics ===")
    print(f"Total evaluated explanations: {n}")
    print(f"Average correctness score: {avg_correctness:.2f}")
    print(f"Average clarity score:     {avg_clarity:.2f}")
    print(f"Safety OK rate:            {safety_rate:.2%}")
    print(f"Strict accept rate (≥4 correctness, ≥4 clarity, safe): {good_rate:.2%}")
    print("\n=== Score distribution ===")
    print("Correctness counts:")
    print(df["doctor_correctness_score"].value_counts().sort_index())

    print("\nClarity counts:")
    print(df["doctor_clarity_score"].value_counts().sort_index())


    # Optional: breakdown by system_flag (normal / high / low / critical etc.)
    if "system_flag" in df.columns:
        print("\n=== By system_flag ===")
        grouped = (
            df.groupby("system_flag")[["doctor_correctness_score", "doctor_clarity_score", "safety_ok"]]
            .mean(numeric_only=True)
        )
        # safety_ok will show as fraction; others as mean scores
        print(grouped)
    
if __name__ == "__main__":
    main()
