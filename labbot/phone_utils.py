import re
from typing import List


def extract_phone_numbers(text: str) -> List[str]:
    
    if not text:
        return []

    pattern = r'(?:\+91[-\s]*)?[6-9]\d{9}'
    matches = re.findall(pattern, text)

    seen = set()
    phones: List[str] = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            phones.append(m)

    return phones
