from pathlib import Path
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Calculation of absolute path to ensure connectivity regardless of launch directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_DIR = BASE_DIR / "database"
DB_PATH = DB_DIR / "leadstation_v2.db"

# Ensure directory exists
os.makedirs(DB_DIR, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
print(f"[*] Initializing Database Engine: {DB_PATH}")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to get a fresh database connection per request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
