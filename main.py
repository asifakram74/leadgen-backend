import uvicorn

if __name__ == "__main__":
    print("[*] Booting up LeadStation Premium Backend...")
    print("[*] Running App Core Initialization...")
    # This automatically boots the deeply-nested app/main.py FastAPI instance!
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)