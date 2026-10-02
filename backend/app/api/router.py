from fastapi import APIRouter, Depends

from app.api.routes import admin, ai, auth, catalog, customer, meta, owner, search
from app.core.deps import csrf_guard

api_router = APIRouter(prefix="/api", dependencies=[Depends(csrf_guard)])
for module in (meta, auth, search, catalog, customer, owner, admin, ai):
    api_router.include_router(module.router)
