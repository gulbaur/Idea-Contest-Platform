"""Тексты писем на английском (D-065) — для получателей, выбравших английский язык.

Русские тексты — в app/jobs.py; функции здесь повторяют их смысл и подписи.
Темы конкурсов, названия идей и имена — данные, они не переводятся.
"""

from datetime import UTC, datetime


def when(moment: datetime) -> str:
    # Часовой пояс получателя серверу неизвестен — время в UTC с явной пометкой (D-044).
    return moment.astimezone(UTC).strftime("%d %b %Y, %H:%M UTC")


def votes(n: int) -> str:
    return f"{n} vote" if n == 1 else f"{n} votes"


def ideas(n: int) -> str:
    return f"{n} idea" if n == 1 else f"{n} ideas"


JOB_TITLES = {
    "remind_submission": "idea submission reminder",
    "open_voting": "start of voting",
    "remind_voting": "voting reminder",
    "finalize": "results and emails to participants",
}


def reminder(kind: str, topic: str, name: str, submission_deadline: datetime, voting_deadline: datetime) -> tuple[str, str]:
    hello = f"Hello, {name}!\n\n"
    if kind == "remind_submission":
        deadline = when(submission_deadline)
        return (
            f"Reminder: idea submission closes {deadline}",
            hello + f"In the contest “{topic}” idea submission closes {deadline}. "
            "You haven't submitted an idea yet — there is still time to suggest yours.",
        )
    deadline = when(voting_deadline)
    return (
        f"Reminder: voting closes {deadline}",
        hello + f"In the contest “{topic}” voting closes {deadline}. "
        "You haven't voted yet — choose the ideas you like.",
    )


def invitation(topic: str, name: str, submission_deadline: datetime, voting_deadline: datetime) -> tuple[str, str]:
    return (
        f"You're invited to the idea contest “{topic}”",
        f"Hello, {name}!\n\n"
        f"You have been added to the idea contest “{topic}”.\n\n"
        f"Idea submission — until {when(submission_deadline)}.\n"
        f"Voting — until {when(voting_deadline)}.\n\n"
        "Suggest your idea: until voting starts only you can see it, "
        "and authors are revealed only with the results.",
    )


def voting_open(topic: str, name: str, ideas_count: int, voting_deadline: datetime) -> tuple[str, str]:
    return (
        f"Voting is open: “{topic}”",
        f"Hello, {name}!\n\n"
        f"Idea submission in the contest “{topic}” is over: {ideas(ideas_count)} submitted. "
        f"Voting is open until {when(voting_deadline)}.\n\n"
        "You can vote for any ideas except your own — one vote per idea. Authors stay hidden until the results.",
    )


def organizer(kind: str, topic: str, name: str, facts: dict, submission_deadline: datetime, voting_deadline: datetime) -> tuple[str, str]:
    hello = f"Hello, {name}!\n\n"
    if kind == "org_submission_soon":
        return (
            f"Idea submission closes {when(submission_deadline)}: “{topic}”",
            hello + f"In the contest “{topic}” idea submission closes {when(submission_deadline)}.\n"
            f"Ideas so far: {facts['ideas']}; participants: {facts['participants']}.\n"
            f"Reminder sent to participants without ideas: {facts['reminded']}.",
        )
    if kind == "org_submission_closed":
        if not facts["ideas"]:
            return (
                f"No ideas submitted: “{topic}”",
                hello + f"Idea submission in the contest “{topic}” is over, but no ideas were submitted. "
                f"There is nothing to vote for: on {when(voting_deadline)} the contest will finish without a winner.",
            )
        return (
            f"Idea submission is over, voting is open: “{topic}”",
            hello + f"Idea submission in the contest “{topic}” is over: {ideas(facts['ideas'])} submitted.\n"
            f"Voting is open until {when(voting_deadline)}; participants have been emailed.",
        )
    if kind == "org_voting_soon":
        return (
            f"Voting closes {when(voting_deadline)}: “{topic}”",
            hello + f"In the contest “{topic}” voting closes {when(voting_deadline)}.\n"
            f"Voted so far: {facts['voters']} of {facts['participants']}. "
            f"Reminder sent to those who haven't voted yet: {facts['reminded']}.",
        )
    return (
        f"Mailing failure: “{topic}”",
        hello + f"In the contest “{topic}” the task “{JOB_TITLES[str(facts['job'])]}” failed after several attempts: "
        "participants may not have received their emails. See the schedule on the contest page for details.",
    )


def final(topic: str, name: str, ranking: list, *, is_organizer: bool, is_winner: bool) -> tuple[str, str]:
    hello = f"Hello, {name}!\n\n"
    if not ranking:
        return (
            f"Results of the contest “{topic}”",
            hello + f"The contest “{topic}” is finished. No ideas were submitted, so there is no winner.",
        )
    winner = ranking[0]
    lines = [
        f"{place}. {idea.title} — {votes(idea.votes)} — author: {idea.author_name}"
        for place, idea in enumerate(ranking, start=1)
    ]
    results = "Results:\n" + "\n".join(lines) + "\n\nIf votes are tied, the idea submitted earlier wins."
    if is_organizer:
        return (
            f"Contest finished: “{topic}”",
            hello + f"The contest “{topic}” is finished. The winning idea is “{winner.title}” "
            f"(author: {winner.author_name}, {votes(winner.votes)}). Participants have been sent their results.\n\n"
            + results,
        )
    if is_winner:
        return (
            f"Your idea won the contest “{topic}”",
            hello + f"Congratulations! Your idea “{winner.title}” won the contest “{topic}” "
            f"({votes(winner.votes)}).\n\n" + results,
        )
    return (
        f"Results of the contest “{topic}”",
        hello + f"The contest “{topic}” is finished. The winning idea is “{winner.title}” "
        f"(author: {winner.author_name}, {votes(winner.votes)}).\n\n" + results,
    )
