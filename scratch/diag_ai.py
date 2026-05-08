import os
import sys
from dotenv import load_dotenv

# Set PYTHONPATH so it can find 'app'
sys.path.append(os.getcwd())
load_dotenv()

from app.services.builder.ai_service import AISiteService

def test_ai_service():
    service = AISiteService()
    test_data = {
        "name": "Test Burger Shop",
        "category": "Fast Food",
        "maps_url": "https://google.com/maps",
        "website": "https://old-site.com",
        "ai_report": "The site uses red and yellow. It looks old.",
        "phone": "555-0199",
        "address": "123 Burger St"
    }
    
    print("[*] Testing AI Site Generation...", flush=True)
    try:
        # We wrap this to catch the EXACT error
        html = service.generate_landing_page(test_data)
        print(f"[OK] Generation Successful! HTML length: {len(html)}", flush=True)
    except Exception as e:
        print(f"[CRASH] AI Service failed with error: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ai_service()
