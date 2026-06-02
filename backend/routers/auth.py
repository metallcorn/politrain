import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from auth import hash_password, verify_password, create_access_token, get_current_user
import models
import schemas

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenResponse)
def register(body: schemas.RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == body.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    user = models.User(
        username=body.username,
        password_hash=hash_password(body.password),
        native_language=body.native_language,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create default content preferences
    prefs = models.UserContentPreferences(user_id=user.id)
    db.add(prefs)
    db.commit()

    token = create_access_token({"sub": str(user.id)})
    return schemas.TokenResponse(access_token=token)


@router.post("/login", response_model=schemas.TokenResponse)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": str(user.id)})
    return schemas.TokenResponse(access_token=token)


@router.post("/logout")
def logout():
    return {"message": "Logged out"}


@router.get("/me", response_model=schemas.UserResponse)
def me(current_user: models.User = Depends(get_current_user)):
    data = schemas.UserResponse.model_validate(current_user)
    data.is_admin = (current_user.username == ADMIN_USERNAME)
    return data
