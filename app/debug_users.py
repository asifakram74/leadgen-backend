from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import User
from app.db.database import DB_PATH

def debug_query():
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        print("[*] Debugging User Query...")
        count = db.query(User).count()
        print(f"[*] Total Users: {count}")
        
        users = db.query(User).limit(10).all()
        for u in users:
            print(f"[*] User: {u.email}, Role: {u.role}, Status: {u.status}, Active: {u.is_active}")
            
    except Exception as e:
        print(f"[!] Error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    debug_query()
