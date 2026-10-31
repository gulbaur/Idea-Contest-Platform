"""Модели запросов и ответов API (Pydantic), общие для нескольких маршрутов."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.domain import Phase

# Пробелы по краям обрезаются; строка из одних пробелов не проходит min_length (D-032).
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]


class ContestSummary(BaseModel):
    id: int
    topic: str
    submission_deadline: datetime
    voting_deadline: datetime
    created_at: datetime
    phase: Phase


class AuthorOut(BaseModel):
    id: int
    display_name: str


class IdeaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    submitted_at: datetime
    updated_at: datetime
    version: int
    # true только для идей текущего пользователя; не раскрывает авторов чужих идей.
    is_mine: bool
    # Автор раскрывается только после финала (D-005, F6); до этого — null.
    author: AuthorOut | None = None
    # Число голосов: организатору с начала голосования, всем — после финала; иначе null (D-035).
    votes_count: int | None = None
    # Голосовал ли текущий пользователь за эту идею. Чужие голоса не раскрываются (D-036).
    voted_by_me: bool = False
