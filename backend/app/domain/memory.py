"""Versioned scheduling with py-fsrs and legacy state compatibility."""

from dataclasses import replace
from datetime import timezone
import json
import math

from fsrs import Card, Rating, Scheduler, State

from . import scheduling

VERSION = "fsrs-6-sdk-6.3.3"
RATINGS = {"again": Rating.Again, "hard": Rating.Hard, "good": Rating.Good, "easy": Rating.Easy}


def initial_state(strategy, now, parameters=None, *, card_id=1):
    if strategy != "fsrs":
        return scheduling.initial_state(strategy, now, parameters)
    parameters = parameters or {}
    retention = float(parameters.get("target_retention", 0.9))
    maximum = int(parameters.get("maximum_interval", 365))
    if not math.isfinite(retention) or not 0 < retention < 1 or not 1 <= maximum <= 36500:
        raise ValueError("Invalid FSRS retention or maximum interval")
    if now.utcoffset() is None:
        raise ValueError("Timezone required")
    now = now.astimezone(timezone.utc)
    scheduler = Scheduler(
        desired_retention=retention,
        maximum_interval=maximum,
        learning_steps=(),
        relearning_steps=(),
        enable_fuzzing=False,
    )
    card = Card(card_id=card_id, due=now)
    return scheduling.ScheduleState(
        strategy="fsrs",
        due_at=now,
        last_reviewed_at=None,
        review_count=0,
        lapse_count=0,
        interval_index=0,
        interval_days=None,
        stability=None,
        difficulty=None,
        retrievability=None,
        target_retention=retention,
        algorithm_version=VERSION,
        parameters={
            "target_retention": retention,
            "maximum_interval": maximum,
            "scheduler": json.loads(scheduler.to_json()),
        },
        last_calculation={"card": json.loads(card.to_json()), "reason": "Initial FSRS review"},
        strategy_changed_at=now,
    )


def review(state, rating, reviewed_at):
    if state.algorithm_version != VERSION:
        return scheduling.review(state, rating, reviewed_at)
    if reviewed_at.utcoffset() is None or rating not in RATINGS:
        raise ValueError("Invalid review input")
    reviewed_at = reviewed_at.astimezone(timezone.utc)
    scheduler = Scheduler.from_json(json.dumps(state.parameters["scheduler"]))
    card = Card.from_json(json.dumps(state.last_calculation["card"]))
    lapse = card.state == State.Review and rating == "again"
    card, log = scheduler.review_card(card, RATINGS[rating], review_datetime=reviewed_at)
    return replace(
        state,
        due_at=card.due,
        last_reviewed_at=reviewed_at,
        review_count=state.review_count + 1,
        lapse_count=state.lapse_count + int(lapse),
        interval_days=(card.due - reviewed_at).total_seconds() / 86400,
        stability=card.stability,
        difficulty=card.difficulty,
        retrievability=scheduler.get_card_retrievability(card, current_datetime=reviewed_at),
        last_calculation={
            "card": json.loads(card.to_json()),
            "review_log": json.loads(log.to_json()),
        },
    )


def switch(state, strategy, now, parameters=None, *, card_id=1):
    new = initial_state(strategy, now, parameters, card_id=card_id)
    return replace(new, review_count=state.review_count, lapse_count=state.lapse_count)


def retrievability_at(state, at):
    """Reconstruct the prediction at a review instant with its saved algorithm."""
    if state.strategy != "fsrs" or not state.last_reviewed_at or not state.stability:
        return None
    if state.last_reviewed_at > at or not math.isfinite(state.stability) or state.stability <= 0:
        return None
    if state.algorithm_version == VERSION:
        card = Card.from_json(json.dumps(state.last_calculation["card"]))
        if card.last_review is None or not card.stability or card.last_review > at:
            return None
        scheduler = Scheduler.from_json(json.dumps(state.parameters["scheduler"]))
        result = scheduler.get_card_retrievability(card, current_datetime=at.astimezone(timezone.utc))
    elif state.algorithm_version == scheduling.FSRS_ALGORITHM_VERSION:
        result = scheduling.retrievability_at(state, at)
    else:
        return None
    return result if result is not None and math.isfinite(result) and 0 <= result <= 1 else None
