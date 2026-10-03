"""Admin view of data-provider health and quota usage."""

from fastapi import APIRouter

from app.api.deps import AdminDep, SettingsDep
from app.providers.registry import configured_providers
from app.providers.resilience import ProviderStatus
from app.services.container import ServicesDep

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/providers")
async def provider_statuses(
    _admin: AdminDep, settings: SettingsDep, services: ServicesDep
) -> list[ProviderStatus]:
    return await services.guard.statuses(configured_providers(settings))
