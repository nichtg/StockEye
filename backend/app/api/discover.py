"""Discover: curated lists of lesser-known stocks (authenticated, read from the nightly cache)."""

from fastapi import APIRouter, Depends

from app.api.deps import UserDep
from app.api.limits import STOCK, limited
from app.services.container import ServicesDep
from app.services.discover import DiscoverOut

router = APIRouter(tags=["discover"])


@router.get("/discover", dependencies=[Depends(limited(STOCK))])
async def discover(_user: UserDep, services: ServicesDep) -> DiscoverOut:
    """Stored lists only: this never calls a vendor, so it cannot spend any quota."""
    return await services.discover.lists()
