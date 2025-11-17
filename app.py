import io
import re
from typing import List, Tuple, Optional
import pdfplumber
import pandas as pd
import streamlit as st

# Utility functions

TABLE_SETTINGS_BORDERLESS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    # we can tweak these if needed later:
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 3,
    "min_words_vertical": 2,
    "min_words_horizontal": 1,
}


def extract_phone_numbers(text:str)->List[str]:
    """
    Extract possible Indian mobile numbers from text.
    Pattern: optional +91 and a 10-digit mobile starting with 6-9.
    """
    if not text:
        return[]
    pattern = r'(?:\+91[-\s]*)?[6-9]\d{9}'
    matches = re.findall(pattern, text)

    seen= set()
    phones=[]
    for m in matches:
        if m not in seen:
            seen.add(m)
            phones.append(m)
    return phones

def parse_range(cell:str)-> Tuple[Optional[float], Optional[float]]:
    """
    Parse a reference range like '12-15 g/dL' or '3.5 - 5.5 mmol/L'
    into (low, high). Returns (None, None) if parsing fails.
    """
    if cell is None:
        return None, None
    text= str(cell)
    text= text.replace("–", "-").replace("—", "-").replace("−", "-")
    nums = re.findall(r'\d+(?:\.\d+)?', text)
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    return None, None

def parse_value(cell:str)-> Optional[float]:
    """
    Parse a numeric value from a cell like '9.4 g/dL' or '<200 mg/dL'.
    Returns None if no number is found.
    """
    if cell is None:
        return None
    text = str(cell)
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    m = re.search(r'-?\d+(?:\.\d+)?', text)
    if m:
        try:
            return float(m.group())
        except ValueError:
            return None
    return None

def map_headers(headers: List[str]) -> dict:
    """
    Try to map raw table headers to canonical columns:
    test_name, value, unit, ref_range
    """
    canonical = {"test_name": None, "value": None, "unit": None, "ref_range": None}
    for idx, h in enumerate(headers):
        if not h:
            continue
        h_low = str(h).strip().lower()
        if any(k in h_low for k in ["test", "parameter", "investigation", "name"]):
            if canonical["test_name"] is None:
                canonical["test_name"] = idx
        elif any(k in h_low for k in ["result", "value", "observed"]):
            if canonical["value"] is None:
                canonical["value"] = idx
        elif any(k in h_low for k in ["unit", "units"]):
            if canonical["unit"] is None:
                canonical["unit"] = idx
        elif any(k in h_low for k in ["ref", "range", "normal"]):
            if canonical["ref_range"] is None:
                canonical["ref_range"] = idx
    return canonical

def classify_status(value: float,
                    low: Optional[float],
                    high: Optional[float]) -> str:
    """
    Compare value against (low, high) and return status string.
    """
    if value is None or low is None or high is None:
        return "unknown"
    if value < low:
        return "below"
    elif value > high:
        return "above"
    else:
        return "within"
    
def generate_english_summary(df: pd.DataFrame) -> str:
    """
    Generate a simple English explanation based purely on:
    - observed values
    - reference ranges present on the report
    No diagnosis, no causes or suggestions.
    """
    lines = []
    lines.append(
        "Here is a summary of the test results based on the reference ranges shown on your lab report:\n"
    )

    for _, row in df.iterrows():
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
        elif status == "within":
            status_text = "This is within the reference range."
        else:
            status_text = "The status could not be determined from the report."

        line = (
            f"- {test_name}: your value is {value} {unit}. "
            f"The reference range on your report is {ref_low}–{ref_high} {unit}. "
            f"{status_text}"
        )
        lines.append(line)

    lines.append(
        "\nThis summary is based only on the values and reference ranges printed on your lab report. "
        "It does not provide any medical advice. Please consult your doctor at Sanjivani Hospital "
        "to understand your results and any next steps."
    )

    return "\n".join(lines)

# Core pdf parsing logic

def extract_tests_from_pdf(file_bytes: bytes) -> Tuple[pd.DataFrame, str]:
    """
    Open a PDF from bytes, extract:
    - tests table(s) with test_name, value, unit, ref_low, ref_high, status
    - full text (for phone extraction)
    Returns (dataframe, full_text).
    """
    all_rows = []
    full_text_parts = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            # Accumulate page text
            text = page.extract_text() or ""
            full_text_parts.append(text)

            # Extract tables from page
            tables = page.extract_tables(table_settings=TABLE_SETTINGS_BORDERLESS)
            for raw_table in tables:
                if not raw_table or len(raw_table) < 2:
                    continue

                headers = raw_table[0]
                mapping = map_headers(headers)

                # We need at least test_name, value, and ref_range columns to be useful
                if not (mapping["test_name"] is not None and
                        mapping["value"] is not None and
                        mapping["ref_range"] is not None):
                    continue

                for row in raw_table[1:]:
                    # Skip empty / malformed rows
                    if not any(row):
                        continue

                    try:
                        test_name = row[mapping["test_name"]]
                        value_raw = row[mapping["value"]]
                        unit = row[mapping["unit"]] if mapping["unit"] is not None else ""
                        ref_raw = row[mapping["ref_range"]]
                    except IndexError:
                        continue

                    value = parse_value(value_raw)
                    ref_low, ref_high = parse_range(ref_raw)

                    # Only keep rows where we have a numeric value and a usable range
                    if value is None or ref_low is None or ref_high is None:
                        continue

                    status = classify_status(value, ref_low, ref_high)

                    all_rows.append(
                        {
                            "Test Name": str(test_name).strip(),
                            "Value": value,
                            "Unit": str(unit).strip(),
                            "Ref Low": ref_low,
                            "Ref High": ref_high,
                            "Status": status,
                        }
                    )

    full_text = "\n".join(full_text_parts)
    df = pd.DataFrame(all_rows)
    return df, full_text

# Streamlit app UI

def main():
    st.set_page_config(page_title="Lab Report Explainer", page_icon="🧪")
    st.title("🧪 Lab Report Explainer")
    st.write(
        "Upload a digital lab report PDF. The app will extract test values and compare them "
        "with the reference ranges printed on the report, then generate a simple summary "
        "without any diagnosis or medical advice."
    )

    uploaded_file = st.file_uploader("Upload lab report PDF", type=["pdf"])

    if uploaded_file is not None:
        st.subheader("Debug: Raw PDF text (for parser tuning)")
        with st.expander("Show raw text"):
            st.text(full_text[:4000])  # show first 4000 chars

        if st.button("Process report"):
            with st.spinner("Reading and analysing the report..."):
                file_bytes = uploaded_file.read()
                df, full_text = extract_tests_from_pdf(file_bytes)

                if df.empty:
                    st.error(
                        "Could not find any test table with numeric values and reference ranges. "
                        "You may need to adjust the parsing logic for your lab's report format."
                    )
                    return

                st.subheader("Parsed Test Results")
                st.dataframe(df)

                # Try to extract phone numbers
                phones = extract_phone_numbers(full_text)
                st.subheader("Detected Phone Numbers in Report")
                if phones:
                    st.write("Possible patient contact numbers found in the report:")
                    for p in phones:
                        st.write(f"- {p}")
                    st.caption(
                        "Later, we will let you select the correct number and send the summary "
                        "to the patient via WhatsApp automatically."
                    )
                else:
                    st.write("No obvious mobile number could be detected in the text.")

                # Generate English summary
                st.subheader("English Summary (for translation in later phases)")
                summary_en = generate_english_summary(df)
                st.text_area("Summary", value=summary_en, height=300)

                st.info(
                    "Parsing + English Summary"
                )


if __name__ == "__main__":
    main()