from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import CreateMCPTokenRequest, MCPAccessTokenCreated, MCPAccessTokenRead
from app.security import require_roles
from app.services.mcp_token_service import create_token, list_tokens, revoke_token

router = APIRouter(prefix="/api/mcp-tokens", tags=["hosted-mcp"])


@router.get("", response_model=list[MCPAccessTokenRead])
def list_mcp_tokens(db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "adops_manager"))) -> list[MCPAccessTokenRead]:
    return [MCPAccessTokenRead.model_validate(token) for token in list_tokens(db)]


@router.post("", response_model=MCPAccessTokenCreated)
def create_mcp_token(
    payload: CreateMCPTokenRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "adops_manager"))
) -> MCPAccessTokenCreated:
    token, raw_token = create_token(
        db, name=payload.name, scope=payload.scope, rate_limit_per_minute=payload.rate_limit_per_minute, created_by=user.id,
    )
    return MCPAccessTokenCreated(**MCPAccessTokenRead.model_validate(token).model_dump(), token=raw_token)


@router.post("/{token_id}/revoke", response_model=MCPAccessTokenRead)
def revoke_mcp_token(
    token_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "adops_manager"))
) -> MCPAccessTokenRead:
    token = revoke_token(db, token_id)
    if token is None:
        raise HTTPException(status_code=404, detail="Token not found")
    return MCPAccessTokenRead.model_validate(token)
