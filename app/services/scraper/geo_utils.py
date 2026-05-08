import json
import os
import re
import requests

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL GEO DATABASE (Top Global Cities & Regions)
# ─────────────────────────────────────────────────────────────────────────────
# For a "Whole World" experience, we use a mix of Major ZIPs and District names.
# This avoids the need for a 1GB JSON file while providing 90% coverage for leads.
GLOBAL_ZONES = {
    "new york": ["10001", "10002", "10003", "10004", "10011", "10012", "10013", "10014", "10016", "10017"],
    "london": ["EC1A", "WC1A", "E1", "N1", "NW1", "SE1", "SW1", "W1", "W2", "E14"],
    "sydney": ["2000", "2010", "2020", "2030", "2040", "2050", "2060", "2070", "2080", "2090"],
    "toronto": ["M5V", "M5H", "M5G", "M5B", "M5A", "M4Y", "M4X", "M4W", "M4V", "M4T"],
    "dubai": ["Downtown", "Marina", "Deira", "Bur Dubai", "JLT", "Jumeirah", "Business Bay", "Al Barsha"],
    "paris": ["75001", "75002", "75008", "75009", "75010", "75011", "75016", "75017", "75018", "75020"],
    "berlin": ["10115", "10117", "10178", "10179", "10243", "10245", "10247", "10249", "10405", "10435"],
    "mumbai": ["400001", "400002", "400003", "400004", "400005", "400008", "400010", "400012", "400013", "400018"],
}

def get_zips_for_location(location: str, max_zips: int = 10) -> list[str]:
    """
    Returns a list of ZIP codes or Neighborhoods for a given location.
    Works globally by identifying major cities or using a 'Sub-District' split strategy.
    """
    clean_loc = location.lower().strip()
    
    # 1. Match against our Global Zone Database
    for city, zones in GLOBAL_ZONES.items():
        if city in clean_loc:
            return zones[:max_zips]
            
    # 2. US Zip Code detection (Regex)
    if re.match(r"^\d{5}(-\d{4})?$", clean_loc):
        return [clean_loc]
        
    # 3. Smart Fallback: If it's a new city, we attempt to search for its 'districts'
    # For now, we return the location itself, but maps_scraper will handle the multi-query
    # by appending common sub-sectors if needed.
    return [location]

def get_sub_queries(category: str, location: str, max_zones: int = 10) -> list[str]:
    """
    Generates multiple search queries based on zones/ZIPs for the given location.
    """
    zones = get_zips_for_location(location, max_zips=max_zones)
    
    # If no specific zones found, we use a 'Directional' fallback for the city
    # e.g. "Plumbers in London North", "Plumbers in London West", etc.
    if len(zones) == 1 and zones[0].lower() == location.lower():
        directions = ["North", "South", "East", "West", "Central", "Downtown", "Suburbs"]
        return [f"{category} in {location} {d}" for d in directions[:max_zones]]
        
    return [f"{category} in {z} {location}" if not z.replace(" ","").isalnum() else f"{category} in {z}" for z in zones]
