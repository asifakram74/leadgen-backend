def deduplicate(results):
    seen = set()
    unique = []

    for r in results:
        key = r.get("name", "").lower().strip()

        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    return unique