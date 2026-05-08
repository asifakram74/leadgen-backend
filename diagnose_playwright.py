import os
import sys

def diagnose():
    print("--- Playwright Diagnostic Tool ---")
    
    # Check if playwright is installed
    try:
        import playwright
        print(f"[SUCCESS] Playwright is installed (version: {playwright.__version__})")
    except ImportError:
        print("[FAIL] Playwright is NOT installed. Run: pip install playwright")
        return

    # Check for playwright-stealth
    try:
        import playwright_stealth
        print("[SUCCESS] playwright-stealth is installed")
    except ImportError:
        print("[FAIL] playwright-stealth is NOT installed. Run: pip install playwright-stealth")

    from playwright.sync_api import sync_playwright
    
    CHROMIUM_PATH = "/www/wwwroot/leadgenbackend.onlinetoolpot.com/browsers/chromium_headless_shell-1208/chrome-headless-shell-linux64/chrome-headless-shell"
    
    print(f"\nChecking Path: {CHROMIUM_PATH}")
    if os.path.exists(CHROMIUM_PATH):
        print(f"[SUCCESS] Path exists.")
        if os.access(CHROMIUM_PATH, os.X_OK):
            print(f"[SUCCESS] Path is executable.")
        else:
            print(f"[FAIL] Path is NOT executable. Run: chmod +x {CHROMIUM_PATH}")
    else:
        print(f"[INFO] Path does not exist. This is fine if using default playwright browsers.")

    print("\nAttempting to launch browser...")
    try:
        with sync_playwright() as p:
            # Try default first
            print("Trying default launch...")
            try:
                browser = p.chromium.launch(headless=True)
                print("[SUCCESS] Default chromium launched.")
                browser.close()
            except Exception as e:
                print(f"[FAIL] Default chromium failed: {e}")
            
            # Try custom path if it exists
            if os.path.exists(CHROMIUM_PATH):
                print(f"Trying custom path {CHROMIUM_PATH}...")
                try:
                    browser = p.chromium.launch(executable_path=CHROMIUM_PATH, headless=True)
                    print("[SUCCESS] Custom chromium launched.")
                    browser.close()
                except Exception as e:
                    print(f"[FAIL] Custom chromium failed: {e}")
                    print("\nTIP: Make sure you have installed system dependencies:")
                    print("  playwright install-deps chromium")

    except Exception as e:
        print(f"[CRITICAL] Playwright sync_playwright() failed: {e}")

if __name__ == "__main__":
    diagnose()
