"""Health probe. Always 200 so "app up, DB down" is distinguishable from "app down"."""

import asyncio
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import DbDep

router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    status: Literal["ok"]
    database: Literal["ok", "unavailable"]


@router.get("/health")
async def health(db: DbDep) -> HealthOut:
    try:
        await asyncio.wait_for(db.command("ping"), timeout=2)
    except Exception:
        return HealthOut(status="ok", database="unavailable")
    return HealthOut(status="ok", database="ok")
