from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from ..models import AdminLoginIn, AdminLoginOut


router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login", response_model=AdminLoginOut)
def admin_login(req: AdminLoginIn) -> AdminLoginOut:
    expected_user = os.getenv("ADMIN_USER", "admin")
    expected_password = os.getenv("ADMIN_PASSWORD", "admin")

    if req.username != expected_user or req.password != expected_password:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    return AdminLoginOut(admin_key=os.getenv("ADMIN_KEY", "admin"))
