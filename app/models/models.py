from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, default="")
    last_name = Column(String, default="")
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user") # Can be 'admin', 'manager', 'user'
    status = Column(String, default="pending") # 'active', 'pending', 'blocked'
    is_verified = Column(Boolean, default=False)
    profile_picture_url = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    verification_token = Column(String, nullable=True)
    reset_token = Column(String, nullable=True)
    is_active = Column(Boolean, default=True) # Legacy toggle
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    verified_at = Column(DateTime(timezone=True), nullable=True)

class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    query_string = Column(String)
    csv_file_url = Column(String)
    json_file_url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
