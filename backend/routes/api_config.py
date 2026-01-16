from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/powerbi")
def powerbi_embed_config():
    url = (os.getenv("POWERBI_EMBED_URL") or "").strip()
    return {"embed_url": url}
