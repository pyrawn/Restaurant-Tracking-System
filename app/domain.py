def table_state(people_count: int, confidence: float, threshold: float = 0.5) -> str:
    if people_count < 0:
        raise ValueError("people_count cannot be negative")
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if confidence < threshold:
        return "review"
    return "occupied" if people_count > 0 else "free"
