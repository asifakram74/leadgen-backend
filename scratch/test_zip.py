import requests
import json

def get_zips(city):
    # This is a bit tricky as zippopotam needs state and city
    # Let's try a more general approach or a different API
    # Or just use a simple mock for now to demonstrate the architecture
    print(f"Searching ZIPs for {city}...")
    # For demonstration, let's just return a few for New York
    if "New York" in city:
        return ["10001", "10002", "10003", "10004", "10005"]
    return []

print(get_zips("New York"))
