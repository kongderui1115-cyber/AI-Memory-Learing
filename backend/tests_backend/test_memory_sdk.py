"""Pin wrapper outputs to the official py-fsrs implementation."""

from datetime import datetime, timezone
import json
import unittest
from fsrs import Card, Scheduler
from app.domain import memory, scheduling


class MemorySDK(unittest.TestCase):
    def test_every_rating_matches_sdk(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for value, rating in memory.RATINGS.items():
            with self.subTest(rating=value):
                state = memory.initial_state("fsrs", now)
                scheduler = Scheduler(
                    desired_retention=0.9,
                    maximum_interval=365,
                    learning_steps=(),
                    relearning_steps=(),
                    enable_fuzzing=False,
                )
                card, log = scheduler.review_card(
                    Card(card_id=1, due=now), rating, review_datetime=now
                )
                result = memory.review(state, value, now)
                self.assertEqual(result.due_at, card.due)
                self.assertEqual(result.stability, card.stability)
                self.assertEqual(result.difficulty, card.difficulty)

    def test_serialized_state_survives_repeated_reviews(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = memory.initial_state("fsrs", now)
        for rating in ("good", "hard", "again", "easy", "good"):
            state = scheduling.from_mapping(json.loads(json.dumps(scheduling.to_dict(state))))
            state = memory.review(state, rating, state.due_at)
        self.assertEqual(state.review_count, 5)
        self.assertEqual(state.lapse_count, 1)
        self.assertEqual(state.algorithm_version, memory.VERSION)

    def test_legacy_scheduling_is_preserved(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        legacy = scheduling.initial_state("fsrs", now)
        self.assertEqual(memory.review(legacy, "good", now), scheduling.review(legacy, "good", now))

    def test_invalid_parameters_are_rejected(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for parameters in (
            {"target_retention": float("nan")},
            {"target_retention": 1.0},
            {"maximum_interval": 0},
        ):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                memory.initial_state("fsrs", now, parameters)
