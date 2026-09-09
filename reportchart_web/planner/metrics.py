"""Small, deterministic metric calculations used by Planner reports."""

from __future__ import annotations


def average(values):
    numbers = [float(value) for value in values if value is not None]
    return round(sum(numbers) / len(numbers), 2) if numbers else None


def percentage(numerator, denominator):
    try:
        denominator = float(denominator)
        if denominator <= 0:
            return None
        return round(float(numerator) / denominator * 100, 2)
    except (TypeError, ValueError):
        return None


def population_stddev(values):
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    mean = sum(numbers) / len(numbers)
    variance = sum((value - mean) ** 2 for value in numbers) / len(numbers)
    return round(variance ** 0.5, 2)


def flow_efficiency(active_time, total_time):
    if active_time is None or total_time is None:
        return None
    try:
        total_time = float(total_time)
        if total_time <= 0:
            return None
        return round(min(float(active_time) / total_time * 100, 100), 2)
    except (TypeError, ValueError):
        return None
