import os
import shutil
from app.db.database import engine, Base, SessionLocal

def hard_reset():
    print("[*] Starting System Hard Reset...")

    # 1. Clear Storage Directories
    storage_dirs = ["storage/leads", "storage/exports", "storage/meta", "storage/results", "storage/profiles"]
    for d in storage_dirs:
        if os.path.exists(d):
            print(f" [*] Cleaning {d}...")
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)

    # 2. Reset Database
    print(" [*] Wiping Database Tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # 3. Re-seed (Optional, but usually you want the admin user back)
    from app.db.seeder import seed_db
    db = SessionLocal()
    try:
        seed_db(db)
        print("[*] System Reset Complete. Database re-seeded.")
    finally:
        db.close()

if __name__ == "__main__":
    confirm = input("!!! WARNING: This will delete ALL leads and jobs. Type 'RESET' to confirm: ")
    if confirm == "RESET":
        hard_reset()
    else:
        print("Reset cancelled.")
