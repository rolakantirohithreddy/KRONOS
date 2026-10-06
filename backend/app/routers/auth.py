import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User, get_db
from app.services.auth_service import (
    create_access_token,
    generate_otp,
    get_current_user,
    get_password_hash,
    verify_password,
)
from app.services.email_service import EmailDeliveryError, send_otp_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    confirm_password: str


class VerifyOTPRequest(BaseModel):
    email: str
    otp_code: str


class ResendOTPRequest(BaseModel):
    email: str


class RegistrationPasswordRequest(BaseModel):
    email: str
    otp_code: str
    password: str
    confirm_password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    otp_code: str
    new_password: str


class UserResponse(BaseModel):
    email: str
    is_verified: bool
    created_at: str


@router.post("/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    if request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    email = request.email.strip().lower()
    existing_user = db.query(User).filter(func.lower(User.email) == email).first()
    if existing_user and existing_user.is_verified:
        raise HTTPException(status_code=400, detail="Email already registered.")

    hashed_password = get_password_hash(request.password)
    otp = generate_otp()

    user = existing_user or User(email=email)
    user.email = email
    user.hashed_password = hashed_password
    user.is_verified = False
    user.otp_code = otp
    user.otp_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=10)
    try:
        send_otp_email(email, otp, "email")
    except EmailDeliveryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    db.add(user)
    db.commit()
    db.refresh(user)

    return {"message": "Registration successful. Please verify your email.", "email": email}


@router.post("/register/request-otp")
def request_registration_otp(request: ResendOTPRequest, db: Session = Depends(get_db)):
    email = request.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user and user.is_verified:
        raise HTTPException(status_code=400, detail="Email already registered.")

    otp = generate_otp()
    if user is None:
        user = User(
            email=email,
            hashed_password=get_password_hash(secrets.token_urlsafe(32)),
        )
    user.email = email
    user.is_verified = False
    user.otp_code = otp
    user.otp_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=10)
    try:
        send_otp_email(email, otp, "email")
    except EmailDeliveryError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.add(user)
    db.commit()
    return {"message": "Verification code sent.", "email": email}


@router.post("/register/check-otp")
def check_registration_otp(request: VerifyOTPRequest, db: Session = Depends(get_db)):
    email = request.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user or user.otp_code != request.otp_code or user.otp_expires_at is None or user.otp_expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
    return {"message": "Email verified. Set your password to finish registration."}


@router.post("/register/set-password")
def set_registration_password(request: RegistrationPasswordRequest, db: Session = Depends(get_db)):
    if request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    email = request.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user or user.otp_code != request.otp_code or user.otp_expires_at is None or user.otp_expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    user.hashed_password = get_password_hash(request.password)
    user.is_verified = True
    user.otp_code = None
    user.otp_expires_at = None
    db.commit()
    return {"message": "Registration completed successfully."}


@router.post("/verify-otp")
def verify_otp(request: VerifyOTPRequest, db: Session = Depends(get_db)):
    email = request.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid request.")

    if user.otp_code != request.otp_code or user.otp_expires_at is None or user.otp_expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    user.is_verified = True
    user.otp_code = None
    user.otp_expires_at = None
    db.commit()

    return {"message": "Email verified successfully."}


@router.post("/resend-otp")
def resend_otp(request: ResendOTPRequest, db: Session = Depends(get_db)):
    email = request.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user or user.is_verified:
        raise HTTPException(status_code=400, detail="Invalid request.")

    otp = generate_otp()
    user.otp_code = otp
    user.otp_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=10)
    try:
        send_otp_email(user.email, otp, "email")
    except EmailDeliveryError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.commit()

    return {"message": "Verification code sent."}


@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    email = request.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Please verify your email.")

    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = request.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user:
        otp = generate_otp()
        user.otp_code = otp
        user.otp_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=10)
        try:
            send_otp_email(user.email, otp, "password reset")
        except EmailDeliveryError as exc:
            db.rollback()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        db.commit()

    return {"message": "If that email is registered, a reset code has been sent."}


@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    email = request.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user or user.otp_code != request.otp_code or user.otp_expires_at is None or user.otp_expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    user.hashed_password = get_password_hash(request.new_password)
    user.otp_code = None
    user.otp_expires_at = None
    db.commit()

    return {"message": "Password reset successful."}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        email=current_user.email,
        is_verified=current_user.is_verified,
        created_at=str(current_user.created_at),
    )


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


@router.post("/change-password")
def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the authenticated user's password after verifying the current one."""
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")
    current_user.hashed_password = get_password_hash(request.new_password)
    db.commit()
    return {"message": "Password updated successfully."}
