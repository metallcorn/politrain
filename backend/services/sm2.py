from datetime import date, timedelta


def calculate_next_review(ease_factor: float, interval_days: int, repetitions: int, quality: int):
    """
    SM-2 algorithm.
    quality: 0 = don't know, 3 = hard, 5 = know
    Returns (new_ease_factor, new_interval, new_repetitions, next_review_date)
    """
    if quality < 3:
        new_repetitions = 0
        new_interval = 1
        new_ease_factor = max(1.3, ease_factor - 0.2)
    else:
        new_repetitions = repetitions + 1
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval_days * ease_factor)

        new_ease_factor = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_ease_factor = max(1.3, new_ease_factor)

    next_review = date.today() + timedelta(days=new_interval)
    return new_ease_factor, new_interval, new_repetitions, next_review
