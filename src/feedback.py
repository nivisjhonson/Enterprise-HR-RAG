from __future__ import annotations

from typing import Any

from config.settings import Settings
from src import database
from src.authorization import require_active_user


def save_answer_feedback(
    settings: Settings,
    answer_id: str,
    rating: int,
    user: dict[str, Any],
) -> None:
    current_user = require_active_user(settings, user)
    if rating not in {-1, 1}:
        raise ValueError("Feedback rating must be either -1 or 1.")
    database.save_answer_feedback(
        settings,
        answer_id,
        current_user["username"],
        rating,
    )
