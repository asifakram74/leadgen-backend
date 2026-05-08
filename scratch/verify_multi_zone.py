from app.services.scraper.maps_scraper import GoogleMapsScraper
import time

def on_data(results):
    print(f"Total leads so far: {len(results)}")

scraper = GoogleMapsScraper(headless=True)
# Test with a single query
print("Testing Scraper for 'Plumbers in New York'...")
results = scraper.scrape("Plumbers in New York", max_results=20, on_data=on_data)
print(f"Final lead count: {len(results)}")
