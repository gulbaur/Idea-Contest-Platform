"""Правила предметной области, не зависящие от БД и HTTP."""

from datetime import datetime
from enum import StrEnum


class Phase(StrEnum):
    SUBMISSION = "submission"
    VOTING = "voting"
    FINISHED = "finished"


def phase_at(submission_deadline: datetime, voting_deadline: datetime, now: datetime) -> Phase:
    """Фаза конкурса в момент `now` (D-007).

    Ровно в момент срока раунд уже закрыт: в `submission_deadline` начинается
    голосование, в `voting_deadline` — финал.
    """
    if now < submission_deadline:
        return Phase.SUBMISSION
    if now < voting_deadline:
        return Phase.VOTING
    return Phase.FINISHED


def ranking_key(votes: int, submitted_at: datetime, idea_id: int) -> tuple:
    """Ключ сортировки результатов (D-008, D-035).

    Больше голосов — выше; при равенстве выше идея, поданная раньше; при одинаковом
    времени подачи — меньший id (устойчивый порядок).
    """
    return (-votes, submitted_at, idea_id)
