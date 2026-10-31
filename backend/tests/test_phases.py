"""Границы фаз ровно в моменты сроков (D-007) — без БД."""

from datetime import timedelta

import pytest

from app.domain import Phase, phase_at
from tests.helpers import SUBMISSION_END, VOTING_END

TICK = timedelta(microseconds=1)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (SUBMISSION_END - timedelta(hours=1), Phase.SUBMISSION),
        (SUBMISSION_END - TICK, Phase.SUBMISSION),
        (SUBMISSION_END, Phase.VOTING),  # ровно в момент срока подача уже закрыта
        (VOTING_END - TICK, Phase.VOTING),
        (VOTING_END, Phase.FINISHED),  # ровно в момент срока голосование уже закрыто
        (VOTING_END + timedelta(days=30), Phase.FINISHED),
    ],
    ids=["early", "last-microsecond", "at-submission-end", "voting-last", "at-voting-end", "later"],
)
def test_phase_boundaries(now, expected):
    assert phase_at(SUBMISSION_END, VOTING_END, now) == expected
