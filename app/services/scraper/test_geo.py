import requests

def test_nominatim(query):
    url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(query)}&format=json&addressdetails=1&limit=12"
    headers = {
        "User-Agent": "LeadStation_CRM_V2_Scraper_Global_Search_v2"
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Testing 'australia'...")
    test_nominatim("australia")
    print("\nTesting 'itlay'...")
    test_nominatim("itlay")
