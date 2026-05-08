from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from jose import JWTError, jwt
import os
import secrets
import shutil
from pydantic import BaseModel
from typing import List

from app.db.database import get_db
from app.models.models import User
from app.schemas.schemas import UserCreate, UserResponse, UserUpdate, PasswordChange, Token, TokenData, UserLogin, PaginatedUserResponse
from app.core.security import verify_password, get_password_hash, create_access_token, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.services.mailer import send_welcome_verification_email, send_forgot_password_email

router = APIRouter(tags=["User & Auth"])

# Change tokenUrl to match our endpoint exactly
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
        
    # Super Admin Auto-Promotion
    if user.email == "zarminazia94@gmail.com" and user.role != "super_admin":
        user.role = "super_admin"
        db.commit()
        db.refresh(user)
        
    return user

# ----------------------------------------------------
# 1. Authentication Routes
# ----------------------------------------------------
@router.post("/auth/register", response_model=UserResponse)
async def register_user(user: UserCreate, db: Session = Depends(get_db)):
    try:
        db_user = db.query(User).filter(User.email == user.email).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed_password = get_password_hash(user.password)
        # The very first user registering automatically gets 'super_admin' role, otherwise 'user'
        is_first = db.query(User).count() == 0
        role = "super_admin" if is_first else "user"
        
        # New users start as 'pending' and 'unverified'
        verification_token = secrets.token_urlsafe(32)
        
        new_user = User(
            email=user.email, 
            first_name=user.first_name, 
            last_name=user.last_name, 
            hashed_password=hashed_password, 
            role=role,
            status="pending",
            is_verified=False,
            verification_token=verification_token
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Send Welcome & Verification Email
        await send_welcome_verification_email(new_user.email, new_user.first_name, verification_token)
        
        return new_user
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        import traceback
        print(f"CRASH: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Registration failed externally.")

@router.post("/auth/login")
async def login_for_access_token(login_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user.status == "blocked":
        raise HTTPException(status_code=403, detail="Your account has been blocked by an administrator.")
    
    # Optional: Block login if not verified
    # if not user.is_verified:
    #     raise HTTPException(status_code=403, detail="Please verify your email address first.")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    # Return full user response in login
    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "user": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "status": user.status,
            "is_verified": user.is_verified,
            "profile_picture_url": user.profile_picture_url,
            "phone_number": user.phone_number,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "verified_at": user.verified_at
        }
    }

@router.get("/auth/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    
    user.is_verified = True
    user.status = "active"
    user.verified_at = datetime.now()
    user.verification_token = None
    db.commit()
    
    return {"status": "success", "message": "Email verified successfully. Your account is now active."}

class ForgotPasswordRequest(BaseModel):
    email: str

@router.post("/auth/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        db.commit()
        await send_forgot_password_email(user.email, token)
        
    return {"status": "success", "message": "If the email is registered, a reset link has been dispatched."}

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

@router.post("/auth/reset-password")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.reset_token == req.token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    user.hashed_password = get_password_hash(req.new_password)
    user.reset_token = None
    db.commit()
    return {"status": "success", "message": "Password reset successfully"}


# ----------------------------------------------------
# 2. User Profile CRUD Routes
# ----------------------------------------------------
@router.get("/profile", response_model=UserResponse)
def read_profile(current_user: User = Depends(get_current_user)):
    return current_user

@router.put("/profile", response_model=UserResponse)
def update_profile(payload: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.first_name is not None:
        current_user.first_name = payload.first_name
    if payload.last_name is not None:
        current_user.last_name = payload.last_name
    if payload.email is not None:
        # Check uniqueness if email changing
        if payload.email != current_user.email:
            existing = db.query(User).filter(User.email == payload.email).first()
            if existing:
                raise HTTPException(status_code=400, detail="Email already in use")
            current_user.email = payload.email
    if payload.phone_number is not None:
        current_user.phone_number = payload.phone_number
        
    db.commit()
    db.refresh(current_user)
    return current_user

@router.put("/profile/password")
def update_own_password(payload: PasswordChange, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid current password")
    
    current_user.hashed_password = get_password_hash(payload.new_password)
    db.commit()
    return {"status": "success"}

@router.get("/users", response_model=PaginatedUserResponse)
def read_all_users(
    q: str = "",
    role: str = None,
    status: str = None,
    page: int = 1,
    size: int = 10,
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    if current_user.role not in ["super_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Administrator access required")
    
    query = db.query(User)
    
    if q:
        search_filter = f"%{q}%"
        query = query.filter(
            (User.first_name.ilike(search_filter)) | 
            (User.last_name.ilike(search_filter)) | 
            (User.email.ilike(search_filter))
        )
        
    if role and role != "all":
        query = query.filter(User.role == role)
        
    if status and status != "all":
        query = query.filter(User.status == status)
        
    total = query.count()
    pages = (total + size - 1) // size if total > 0 else 0
    
    users = query.offset((page - 1) * size).limit(size).all()
    
    return {
        "items": users,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages
    }

@router.post("/users", response_model=UserResponse)
def admin_create_user(user: UserCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in ["super_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Administrator access required")
    
    # Nobody can create a super_admin account via the API
    if (user.role or "") == "super_admin":
        raise HTTPException(status_code=403, detail="Cannot create Super Admin accounts via the panel.")
        
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    hashed_password = get_password_hash(user.password)
    new_user = User(
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        hashed_password=hashed_password,
        role=user.role or "user",
        status=user.status or "active",
        is_verified=user.is_verified if user.is_verified is not None else True,
        verified_at=datetime.now() if (user.is_verified or user.is_verified is None) else None
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.put("/users/{user_id}", response_model=UserResponse)
def update_user_fields(user_id: int, payload: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in ["super_admin", "admin"] and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Super Admin accounts are immutable — nobody can edit them
    if target_user.role == "super_admin" and current_user.id != target_user.id:
        raise HTTPException(status_code=403, detail="Super Admin accounts cannot be modified.")
        
    if payload.first_name is not None:
        target_user.first_name = payload.first_name
    if payload.last_name is not None:
        target_user.last_name = payload.last_name
    if payload.email is not None:
        coll = db.query(User).filter(User.email == payload.email).first()
        if coll and coll.id != user_id:
            raise HTTPException(status_code=400, detail="Email already in use")
        target_user.email = payload.email
        
    if payload.role is not None and current_user.role in ["super_admin", "admin"]:
        # Nobody can assign or change a role to super_admin
        if payload.role == "super_admin":
            raise HTTPException(status_code=403, detail="Cannot assign Super Admin role.")
        target_user.role = payload.role
        
    if payload.status is not None and current_user.role in ["super_admin", "admin"]:
        target_user.status = payload.status

    if payload.is_verified is not None and current_user.role in ["super_admin", "admin"]:
        target_user.is_verified = payload.is_verified
        if payload.is_verified:
            target_user.verified_at = datetime.now()
        else:
            target_user.verified_at = None
        
    db.commit()
    db.refresh(target_user)
    return target_user

@router.get("/users/{user_id}", response_model=UserResponse)
def read_user_by_id(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in ["super_admin", "admin"] and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return user

@router.post("/profile/picture")
async def upload_profile_picture(file: UploadFile = File(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        raise HTTPException(status_code=400, detail="File must be an image type")
        
    file_extension = file.filename.split('.')[-1]
    filename = f"user_{current_user.id}.{file_extension}"
    file_path = os.path.join("storage", "profiles", filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    url_path = f"/storage/profiles/{filename}"
    current_user.profile_picture_url = url_path
    db.commit()
    
    return {"status": "success", "profile_picture_url": url_path}

@router.delete("/users/{user_id}")
def delete_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.id != user_id and current_user.role not in ["super_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Administrator access required")
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Super Admin accounts can never be deleted
    if user.role == "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin accounts cannot be deleted.")
        
    db.delete(user)
    db.commit()
    return {"status": "success", "message": "User deleted successfully"}
