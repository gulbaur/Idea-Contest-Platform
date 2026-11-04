"""Модели запросов и ответов API (Pydantic), общие для нескольких маршрутов."""

from datetime import datetime
from typing import Annotated

from fastapi import Path
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from app.domain import Phase

# Символ NUL PostgreSQL в тексте сохранить не может — без этой проверки запрос
# падал бы с 500 уже в БД; отклоняем его с 422 (D-038). Одиночные суррогаты
# Юникода отклоняет сама Pydantic при разборе JSON.


def _storable(value: str) -> str:
    if "\x00" in value:
        raise ValueError("Текст содержит недопустимый символ NUL")
    return value


StorableText = AfterValidator(_storable)

# Пробелы по краям обрезаются; строка из одних пробелов не проходит min_length (D-032).
Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200), StorableText
]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000), StorableText
]

# Номер конкурса или идеи в адресе: столбцы INTEGER, больший номер БД не примет (D-038).
IdPath = Annotated[int, Path(ge=1, le=2_147_483_647)]


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
    # Только у своих идей; у чужих — null (D-058).
    updated_at: datetime | None
    version: int | None
    # true только для идей текущего пользователя; не раскрывает авторов чужих идей.
    is_mine: bool
    # Автор раскрывается только после финала (D-005, F6); до этого — null.
    author: AuthorOut | None = None
    # Число голосов: организатору с начала голосования, всем — после финала; иначе null (D-035).
    votes_count: int | None = None
    # Голосовал ли текущий пользователь за эту идею. Чужие голоса не раскрываются (D-036).
    voted_by_me: bool = False
