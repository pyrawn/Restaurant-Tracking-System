def _point_on_segment(point: tuple[float, float], start, end) -> bool:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    if abs(cross) > 1e-9:
        return False
    return min(x1, x2) <= px <= max(x1, x2) and min(y1, y2) <= py <= max(y1, y2)


def point_in_polygon(point: tuple[float, float], polygon) -> bool:
    if len(polygon) < 3:
        return False

    inside = False
    for index, start in enumerate(polygon):
        end = polygon[index - 1]
        if _point_on_segment(point, start, end):
            return True

        x, y = point
        x1, y1 = start
        x2, y2 = end
        if (y1 > y) != (y2 > y):
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing_x:
                inside = not inside
    return inside


def build_table_observations(detections, tables, model_version: str) -> list[dict]:
    matches = {table["id"]: [] for table in tables}

    for detection in detections:
        x1, y1, x2, y2 = detection["box"]
        anchor = ((float(x1) + float(x2)) / 2, float(y2))
        confidence = float(detection["confidence"])
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

        for table in tables:
            if point_in_polygon(anchor, table["polygon"]):
                matches[table["id"]].append(detection)
                break

    observations = []
    for table in tables:
        table_detections = matches[table["id"]]
        confidence = (
            sum(float(item["confidence"]) for item in table_detections)
            / len(table_detections)
            if table_detections
            else 1.0
        )
        count = len(table_detections)
        observations.append({
            "table_id": table["id"],
            "people_count": count,
            "occupied": count > 0,
            "confidence": round(confidence, 4),
            "detected_waiter_id": None,
            "model_version": model_version,
        })
    return observations
