from sqlalchemy.orm import Session
from app.models.models import User
from app.core.security import get_password_hash
from datetime import datetime

def seed_db(db: Session):
    # Check if admin user already exists
    admin_email = "zarminazia94@gmail.com"
    admin = db.query(User).filter(User.email == admin_email).first()
    
    if not admin:
        print(f"[*] Seeding administrative user: {admin_email}")
        hashed_password = get_password_hash("Zarmina@94")
        new_admin = User(
            email=admin_email,
            first_name="Zarmina",
            last_name="Zia",
            hashed_password=hashed_password,
            role="admin",
            status="active",
            is_verified=True,
            verified_at=datetime.now(),
            is_active=True
        )
        db.add(new_admin)
        db.commit()
        db.refresh(new_admin)
        print("[+] Admin user seeded successfully.")
    else:
        print("[*] Admin user already exists. Skipping seed.")
