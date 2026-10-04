"""The authenticated caller, as resolved from the database on every request."""

from dataclasses import dataclass
from typing import Literal

from bson import ObjectId


@dataclass(frozen=True, slots=True)
class Principal:
    id: ObjectId
    email: str
    role: Literal["user", "admin"]
