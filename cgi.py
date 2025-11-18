# only for python 3.13


from typing import Dict, Tuple


def parse_header(line: str) -> Tuple[str, Dict[str, str]]:
    """
    Very small implementation of parse_header.

    Example:
        'text/html; charset="utf-8"' ->
            ('text/html', {'charset': 'utf-8'})
    """
    if not line:
        return "", {}

    parts = [p.strip() for p in line.split(";") if p.strip()]
    main_value = parts[0] if parts else ""
    params: Dict[str, str] = {}

    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip().lower()
            v = v.strip().strip('"').strip("'")
            params[k] = v

    return main_value, params
