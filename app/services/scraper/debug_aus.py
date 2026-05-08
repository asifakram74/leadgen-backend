import requests
import json

def test_aus():
    url = "https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&limit=10&q=aus"
    headers = {"User-Agent": "LeadStation_Test"}
    r = requests.get(url, headers=headers).json()
    for d in r:
        addr = d.get('address', {})
        print(f"DISPLAY: {d.get('display_name')}")
        print(f"   CITY: {addr.get('city') or addr.get('town') or addr.get('village') or addr.get('hamlet')}")
        print(f"  STATE: {addr.get('state') or addr.get('province') or addr.get('region')}")
        print(f"COUNTRY: {addr.get('country')}")
        print("-" * 20)

if __name__ == "__main__":
    test_aus()
