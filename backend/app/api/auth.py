from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.rate_limit import check_rate_limit
from app.schemas import LoginRequest, TokenResponse, UserRead
from app.security import (
    authenticate_user,
    build_demo_viewer,
    create_access_token,
    create_demo_access_token,
    get_current_user,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])
DEMO_SESSION_RATE_LIMIT_PER_MINUTE = 20


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, request.email, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    token, expires_in = create_access_token(user)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(user)


@router.post("/demo-session", response_model=TokenResponse)
def demo_session(request: Request) -> TokenResponse:
    """Issue a read-only session for the public portfolio demo - no password.

    Scoped to the demo_viewer role, which require_roles() already excludes
    from every approval/mutation endpoint, and for which the agent layer
    skips audit-log and recommendation writes (see api/agent.py). Rate
    limited per client IP since this is the one unauthenticated surface that
    can trigger a real (if non-persisting) LLM/RAG diagnosis.
    """
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"demo-session:{client_ip}", DEMO_SESSION_RATE_LIMIT_PER_MINUTE):
        raise HTTPException(status_code=429, detail="Too many demo session requests. Try again shortly.")
    token, expires_in = create_demo_access_token()
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserRead.model_validate(build_demo_viewer()),
    )
