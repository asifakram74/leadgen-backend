from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import ScrapeJob
from app.db.database import DB_PATH
import os

def clean_scrapes():
    # Construct DB URL
    # Handle both absolute and relative paths
    if os.path.isabs(DB_PATH):
        SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
    else:
        # If relative, it's relative to the app's root
        SQLALCHEMY_DATABASE_URL = f"sqlite:///./{DB_PATH}"
        
    print(f"[*] Connecting to: {SQLALCHEMY_DATABASE_URL}")
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        print("[*] Cleaning Scrape History...")
        deleted_count = db.query(ScrapeJob).delete()
        db.commit()
        print(f"[OK] Deleted {deleted_count} scrape records.")
        
    except Exception as e:
        db.rollback()
        print(f"[!] Error cleaning database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    clean_scrapes()
