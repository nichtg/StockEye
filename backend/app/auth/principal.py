"""The authenticated caller, as resolved from the database on every request."""

from dataclasses import dataclass
from datetime import datetime

from bson import ObjectId

from app.repositories.users import Role


@dataclass(frozen=True, slots=True)
class Principal:
    id: ObjectId
    email: str
    role: Role
    created_at: datetime
