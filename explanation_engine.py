# explanation_engine.py
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple

TEST_CATEGORY_MAP: Dict[str, str] = {
    "fasting blood sugar": "blood sugar",
    "post prandial blood sugar": "blood sugar",
    "random blood sugar": "blood sugar",
    "hba1c": "blood sugar",
    "total cholesterol": "cholesterol",
    "ldl": "cholesterol",
    "hdl": "cholesterol",
    "triglycerides": "cholesterol",
    "creatinine": "kidney",
    "bun": "kidney",
    "sgpt": "liver",
    "sgot": "liver",
    # add more as you see reports
}


@dataclass
class LabTestResult:
    name: str
    value: float
    unit: str
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None
    category: Optional[str] = None  # e.g. "sugar", "lipids", "kidney"


@dataclass
class TestEvaluation:
    test: LabTestResult
    flag: str            # "normal", "low", "high", "critical_low", "critical_high"
    severity: str        # "normal", "borderline", "abnormal", "critical"
    summary_text: str    # patient-friendly explanation
    recommend_doctor: bool
    recommend_urgent: bool

TEST_CATEGORY_MAP: Dict[str, str] = {
    "fasting blood sugar": "blood sugar",
    "post prandial blood sugar": "blood sugar",
    "random blood sugar": "blood sugar",
    "hba1c": "blood sugar",
    "total cholesterol": "cholesterol",
    "ldl": "cholesterol",
    "hdl": "cholesterol",
    "triglycerides": "cholesterol",
    "creatinine": "kidney",
    "bun": "kidney",
    "sgpt": "liver",
    "sgot": "liver",
    # add more as you see reports
}

def _compute_flag_and_severity(test: LabTestResult) -> Tuple[str, str, bool, bool]:
    """
    Returns (flag, severity, recommend_doctor, recommend_urgent).
    """
    v = test.value
    if test.ref_low is None or test.ref_high is None:
        # no reference range, be conservative
        return "unknown", "unknown", True, False

    low = test.ref_low
    high = test.ref_high

    # normal
    if low <= v <= high:
        return "normal", "normal", False, False

    # below range
    if v < low:
        ratio = v / low if low > 0 else 0.0
        if ratio < 0.5:
            return "critical_low", "critical", True, True
        elif ratio < 0.9:
            return "low", "abnormal", True, False
        else:
            return "low", "borderline", True, False

    # above range
    if v > high:
        ratio = v / high if high > 0 else 0.0
        if ratio >= 2.0:
            return "critical_high", "critical", True, True
        elif ratio >= 1.2:
            return "high", "abnormal", True, False
        else:
            return "high", "borderline", True, False

    return "unknown", "unknown", True, False

def _fmt_num(x: Optional[float]) -> str:
    """
    Format numbers so they look nice in text:
      - 16.0 -> "16"
      - 7.5  -> "7.5"
    """
    if x is None:
        return ""
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return str(x)

    if xf.is_integer():
        return str(int(xf))
    # one decimal place is enough for lab ranges usually
    return f"{xf:.1f}"

def _make_test_summary(test: LabTestResult, flag: str, severity: str) -> str:
    name = test.name
    v = test.value
    unit = (test.unit or "").strip()
    low = test.ref_low
    high = test.ref_high

    v_str = _fmt_num(v)
    low_str = _fmt_num(low)
    high_str = _fmt_num(high)

    if low is not None and high is not None:
        if unit:
            range_str = f"{low_str}-{high_str} {unit}"
        else:
            range_str = f"{low_str}-{high_str}"
    else:
        range_str = "the usual healthy range"

    # ----- normal -----
    if severity == "normal":
        return (
            f"Your {name} is {v_str} {unit}. "
            f"This is within the usual healthy range ({range_str})."
        ).strip()

    # ----- borderline -----
    if severity == "borderline":
        direction = "slightly below" if "low" in flag else "slightly above"
        return (
            f"Your {name} is {v_str} {unit}, which is {direction} the usual healthy range "
            f"({range_str})."
        ).strip()

    # ----- abnormal -----
    if severity == "abnormal":
        direction = "lower" if "low" in flag else "higher"
        return (
            f"Your {name} is {v_str} {unit}, which is {direction} than the usual healthy range "
            f"({range_str})."
        ).strip()

    # ----- critical -----
    if severity == "critical":
        direction = "much lower" if "low" in flag else "much higher"
        return (
            f"Your {name} is {v_str} {unit}, which is {direction} than the usual healthy range "
            f"({range_str}). This can be serious."
        ).strip()

    # ----- fallback -----
    return (
        f"Your {name} result is {v_str} {unit}. "
        f"The usual healthy range is {range_str}."
    ).strip()


def evaluate_test(test: LabTestResult) -> TestEvaluation:
    # auto-fill category if missing
    if not test.category:
        key = test.name.strip().lower()
        test.category = TEST_CATEGORY_MAP.get(key)

    flag, severity, rec_doc, rec_urgent = _compute_flag_and_severity(test)
    summary = _make_test_summary(test, flag, severity)

    return TestEvaluation(
        test=test,
        flag=flag,
        severity=severity,
        summary_text=summary,
        recommend_doctor=rec_doc,
        recommend_urgent=rec_urgent,
    )


def evaluate_report(tests: List[LabTestResult]) -> Dict[str, object]:
    evaluations: List[TestEvaluation] = [evaluate_test(t) for t in tests]

    # Overall summary
    n = len(evaluations)
    n_normal = sum(1 for e in evaluations if e.severity == "normal")
    n_abnormal = sum(1 for e in evaluations if e.severity in ("borderline", "abnormal", "critical"))
    n_critical = sum(1 for e in evaluations if e.severity == "critical")

    if n_abnormal == 0:
        overall = (
            "Most of your test results are within the usual healthy range. "
            "This is generally a good sign, but always follow up with your doctor "
            "for complete interpretation."
        )
    else:
        parts = []
        parts.append(
            f"{n_abnormal} out of {n} test values are outside the usual healthy range."
        )
        if n_critical > 0:
            parts.append(
                f"{n_critical} value(s) are much higher or lower than normal and may need urgent attention."
            )
        else:
            parts.append(
                "These results are usually not an emergency but should be discussed with your doctor."
            )
        overall = " ".join(parts)

    # Categories summary (optional)
    categories = {}
    for e in evaluations:
        cat = e.test.category or "other"
        categories.setdefault(cat, []).append(e)

    category_summary_parts = []
    for cat, evs in categories.items():
        if cat == "other":
            continue
        num_abn = sum(1 for e in evs if e.severity != "normal")
        if num_abn > 0:
            category_summary_parts.append(
                f"There are some changes related to {cat}."
            )
    category_summary = " ".join(category_summary_parts).strip()

    # Safety notice
    needs_urgent = any(e.recommend_urgent for e in evaluations)
    if needs_urgent:
        safety_notice = (
            "This explanation is for information only and is not a diagnosis. "
            "Some values look very abnormal. If you feel unwell, have chest pain, "
            "severe breathlessness, confusion, or any worrying symptoms, "
            "please seek urgent medical care or contact your doctor immediately."
        )
    else:
        safety_notice = (
            "This explanation is for information only and is not a diagnosis. "
            "Do not start, stop, or change any medicines based on this report alone. "
            "Please discuss your results with your doctor."
        )

    return {
        "evaluations": evaluations,
        "overall_summary_en": overall,
        "category_summary_en": category_summary,
        "safety_notice_en": safety_notice,
    }

if __name__ == "__main__":
    tests = [
        LabTestResult(
            name="fasting blood sugar",
            value=134,
            unit="mg/dL",
            ref_low=70,
            ref_high=110,
        ),
        LabTestResult(
            name="total cholesterol",
            value=210,
            unit="mg/dL",
            ref_low=0,
            ref_high=200,
        ),
    ]

    result = evaluate_report(tests)

    print("--- Per-test explanations ---")
    for e in result["evaluations"]:
        print(e.summary_text)
        print()

    print("--- Overall summary ---")
    print(result["overall_summary_en"])
    print()

    print("--- Safety notice ---")
    print(result["safety_notice_en"])

