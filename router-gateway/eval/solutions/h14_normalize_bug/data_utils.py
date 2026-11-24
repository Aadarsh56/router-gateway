def normalize(values):
    if not values:
        return []
    min_val = min(values)
    max_val = max(values)
    if max_val == min_val:
        return [0.0] * len(values)
    return [(x - min_val) / (max_val - min_val) for x in values]
