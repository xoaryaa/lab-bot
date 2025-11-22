import pandas as pd


def generate_english_summary(df: pd.DataFrame) -> str:
    """
    Generate a simple English explanation based purely on:
    - observed values
    - reference ranges present on the report

    Only includes tests where the value is BELOW or ABOVE
    the reference range. Normal tests are not listed.
    """
    # Filter to abnormal results only
    abnormal = df[df["Status"].isin(["below", "above"])]

    lines = []

    if abnormal.empty:
        lines.append(
            "All the test values in your report are within the reference ranges "
            "printed on the lab report."
        )
    else:
        lines.append(
            "Here is a summary of the test results that are outside the "
            "reference ranges shown on your lab report:\n"
        )

        for _, row in abnormal.iterrows():
            test_name = row.get("Test Name", "")
            value = row.get("Value", "")
            unit = row.get("Unit", "")
            ref_low = row.get("Ref Low", "")
            ref_high = row.get("Ref High", "")
            status = row.get("Status", "unknown")

            if status == "below":
                status_text = "This is below the reference range."
            elif status == "above":
                status_text = "This is above the reference range."
            else:
                # We shouldn't hit this because of the filter, but just in case
                continue

            line = (
                f"- {test_name}: your value is {value} {unit}. "
                f"The reference range on your report is {ref_low}–{ref_high} {unit}. "
                f"{status_text}"
            )
            lines.append(line)

    lines.append(
        "\nThis summary is based only on the values and reference ranges printed on your "
        "lab report. It does not provide any medical advice. Please consult your doctor "
        "at Sanjivani Hospital to understand your results and any next steps."
    )

    return "\n".join(lines)

