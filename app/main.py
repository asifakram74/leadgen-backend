from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from app.db.database import engine, Base, SessionLocal
from app.db.seeder import seed_db
from app.api.endpoints import users, scraper, builder
from fastapi import Request

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ─── Startup Procedures ───
    print("[*] Performing System Startup Procedures...")
    
    # Create storage directories natively
    os.makedirs("storage/profiles", exist_ok=True)
    os.makedirs("storage/exports", exist_ok=True)
    os.makedirs("storage/sites", exist_ok=True)
    
    # Initialize DB (native create_all)
    Base.metadata.create_all(bind=engine)
    
    # Run seeder
    db = SessionLocal()
    try:
        seed_db(db)
        print("[*] Database Schema Verified and Seeded.")
    finally:
        db.close()
    
    print("[*] LeadStation Core System fully operational.")
    
    yield
    
    # ─── Shutdown Procedures ───
    print("[*] LeadStation Core Engine shutting down safely...")

app = FastAPI(
    title="LeadStation API", 
    description="Commercial Core for Maps Data",
    lifespan=lifespan
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"[*] Incoming Request: {request.method} {request.url}")
    response = await call_next(request)
    print(f"[*] Response Status: {response.status_code}")
    return response

# Mount static files
app.mount("/storage", StaticFiles(directory="storage"), name="storage")

# Include Routers
app.include_router(users.router)
app.include_router(scraper.router)
app.include_router(builder.router)

# CORS Configuration
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
