"""Правило порядка результатов без БД (D-008, D-035)."""

from datetime import timedelta

from app.domain import ranking_key
from tests.helpers import T0


def rank(ideas):
    return [i[0] for i in sorted(ideas, key=lambda i: ranking_key(i[1], i[2], i[0]))]


def test_more_votes_first():
    assert rank([(1, 1, T0), (2, 3, T0 + timedelta(hours=1))]) == [2, 1]


def test_tie_earlier_submission_first():
    assert rank([(5, 2, T0 + timedelta(seconds=1)), (9, 2, T0)]) == [9, 5]


def test_tie_same_time_lower_id_first():
    assert rank([(7, 0, T0), (3, 0, T0), (5, 0, T0)]) == [3, 5, 7]
