from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List

class UserBase(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: str
    phone_number: Optional[str] = None

class UserCreate(UserBase):
    password: str
    role: Optional[str] = "user"
    status: Optional[str] = "active"
    is_verified: Optional[bool] = False

class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    is_verified: Optional[bool] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class UserResponse(UserBase):
    id: int
    is_active: Optional[bool] = True
    status: Optional[str] = "active"
    is_verified: Optional[bool] = False
    role: Optional[str] = "user"
    profile_picture_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class PaginatedUserResponse(BaseModel):
    items: List[UserResponse]
    total: int
    page: int
    size: int
    pages: int

class UserLogin(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class ScrapeJobResponse(BaseModel):
    id: int
    user_id: int
    query_string: str
    csv_file_url: str
    json_file_url: str
    created_at: datetime
    
    class Config:
        from_attributes = True

PaginatedUserResponse.model_rebuild()
