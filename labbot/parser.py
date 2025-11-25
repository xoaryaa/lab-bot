import io
import re
from typing import List, Tuple, Optional

import pdfplumber
import pandas as pd


TABLE_SETTINGS_BORDERLESS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 3,
    "min_words_vertical": 2,
    "min_words_horizontal": 1,
}


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
    
def extract_tests_from_pdf(file_bytes: bytes) -> Tuple[pd.DataFrame, str]:
    """
    Open a PDF from bytes, extract:
    - tests table(s) with test_name, value, unit, ref_low, ref_high, status
    - full text (for phone extraction)
    Returns (dataframe, full_text).

    Strategy:
    1. Try pdfplumber table extraction (borderless settings).
    2. If that yields nothing, fall back to line-based parsing on full_text.
    """
    all_rows = []
    full_text_parts = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            full_text_parts.append(text)

            # Try to extract tables using text-based strategy
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

    # If table-based extraction failed, fall back to line-based parsing
    if not all_rows:
        df = extract_tests_from_text(full_text)
    else:
        df = pd.DataFrame(all_rows)

    return df, full_text

def extract_tests_from_text(full_text: str) -> pd.DataFrame:
    """
    Fallback parser when table extraction fails.

    Generic strategy:
    - For each line that contains numbers:
      - Test name = text before the first number
      - Value    = first number
      - Ref low  = second-last number
      - Ref high = last number

    Assumes a pattern like:
        Hemoglobin      9.4 g/dL      12 - 15
        Fasting Glucose 88 mg/dL      70 - 100
    or similar.
    """
    rows = []
    num_pattern = r'-?\d+(?:\.\d+)?'

    for line in full_text.splitlines():
        raw_line = line
        line = line.strip()
        if not line:
            continue

        # Skip obvious header lines
        lower = line.lower()
        if any(
            kw in lower
            for kw in ["test", "parameter", "investigation", "result", "value", "reference", "normal", "unit"]
        ):
            continue

        # Must contain at least 3 numbers (value + low + high)
        nums = re.findall(num_pattern, line)
        if len(nums) < 3:
            continue

        # Test name = text before the first number
        first_num_match = re.search(num_pattern, line)
        if not first_num_match:
            continue

        test_name = line[: first_num_match.start()].strip()
        if not test_name:
            continue

        try:
            value = float(nums[0])
            ref_low = float(nums[-2])
            ref_high = float(nums[-1])
        except ValueError:
            continue

        # Ensure we have a sane range; swap if clearly reversed
        if ref_low > ref_high:
            ref_low, ref_high = ref_high, ref_low

        # Heuristic: ignore if all three numbers are identical
        if value == ref_low == ref_high:
            continue

        # Unit = text between first and second numbers (best-effort)
        rest_after_value = line[first_num_match.end():]
        second_num_match = re.search(num_pattern, rest_after_value)
        unit = ""
        if second_num_match:
            unit = rest_after_value[: second_num_match.start()].strip()

        status = classify_status(value, ref_low, ref_high)

        rows.append(
            {
                "Test Name": test_name,
                "Value": value,
                "Unit": unit,
                "Ref Low": ref_low,
                "Ref High": ref_high,
                "Status": status,
            }
        )

    return pd.DataFrame(rows)