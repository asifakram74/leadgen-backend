import re

class GeoService:
    # A robust map of major cities to their neighborhoods/zones for deep scraping
    CITY_ZONES = {
        # --- Pakistan ---
        "lahore": ["Gulberg", "DHA", "Johar Town", "Model Town", "Faisal Town", "Wapda Town", "Bahria Town", "Samanabad", "Garhi Shahu", "Mughalpura", "Cantonment"],
        "karachi": ["Clifton", "DHA", "Gulshan-e-Iqbal", "North Nazimabad", "PECHS", "Bahria Town", "Korangi", "Saddar", "Malir", "Nazimabad", "Landhi"],
        "islamabad": ["F-6", "F-7", "F-10", "F-11", "G-6", "G-9", "G-11", "I-8", "DHA", "Bahria Town", "E-7", "I-10"],
        "rawalpindi": ["Saddar", "Bahria Town", "DHA", "Satellite Town", "Chaklala", "Westridge", "Adyala Road", "Gulrez"],
        "multan": ["Gulgasht Colony", "Bosan Road", "Multan Cantt", "Shah Rukn-e-Alam", "Wapda Town", "Mumtazabad"],
        "faisalabad": ["People's Colony", "Madina Town", "D Ground", "Samanabad", "Kohinoor City", "Jaranwala Road"],
        "gujranwala": ["Satellite Town", "Model Town", "Wapda Town", "DC Road", "Rahwali Cantt", "Garden Town"],
        "sialkot": ["Sialkot Cantt", "Model Town", "Sialkot City", "Defence", "Kashmir Road"],
        "peshawar": ["Hayatabad", "University Road", "Peshawar Cantt", "Warsak Road", "Gulbahar", "Ring Road"],
        "hyderabad": ["Latifabad", "Qasimabad", "Hyderabad Cantt", "Saddar"],
        "quetta": ["Quetta Cantt", "Satellite Town", "Jinnah Road", "Samungli Road"],
        "bahawalpur": ["Model Town", "Bahawalpur Cantt", "Sadiq Colony"],
        "sargodha": ["Satellite Town", "Sargodha Cantt", "University Road"],

        # --- North America ---
        "new york": ["Manhattan", "Brooklyn", "Queens", "The Bronx", "Staten Island", "Harlem", "Chelsea", "Upper East Side"],
        "los angeles": ["Hollywood", "Santa Monica", "Beverly Hills", "Venice", "Downtown LA", "Pasadena", "Silver Lake"],
        "chicago": ["Lincoln Park", "Wicker Park", "The Loop", "Logan Square", "River North", "Hyde Park", "West Loop"],
        "toronto": ["Downtown Toronto", "North York", "Scarborough", "Etobicoke", "Mississauga", "The Beaches", "Liberty Village"],
        "vancouver": ["Gastown", "Yaletown", "Kitsilano", "Burnaby", "Richmond", "Surrey", "West End"],
        "houston": ["Downtown", "The Heights", "Montrose", "Galleria", "Sugar Land", "Katy", "The Woodlands"],
        "miami": ["South Beach", "Brickell", "Wynwood", "Coral Gables", "Little Havana", "Coconut Grove"],

        # --- Europe ---
        "london": ["Westminster", "Camden", "Islington", "Hackney", "Greenwich", "Chelsea", "Kensington", "Soho"],
        "paris": ["Le Marais", "Montmartre", "Latin Quarter", "Saint-Germain-des-Prés", "Champs-Élysées", "Bastille"],
        "berlin": ["Mitte", "Kreuzberg", "Prenzlauer Berg", "Neukölln", "Charlottenburg", "Friedrichshain"],
        "amsterdam": ["Centrum", "De Pijp", "Jordaan", "Oud-West", "Noord", "Zuid"],

        # --- Middle East & Asia ---
        "dubai": ["Deira", "Bur Dubai", "Jumeirah", "Downtown Dubai", "Dubai Marina", "Business Bay", "Palm Jumeirah", "JLT"],
        "abu dhabi": ["Al Reem Island", "Khalifa City", "Yas Island", "Saadiyat Island", "Corniche", "Al Maryah Island"],
        "riyadh": ["Al Olaya", "Al Malaz", "Al Murabba", "Diplomatic Quarter", "Al Nakheel"],
        "tokyo": ["Shinjuku", "Shibuya", "Ginza", "Akihabara", "Roppongi", "Asakusa", "Harajuku"],
        "singapore": ["Orchard", "Marina Bay", "Chinatown", "Little India", "Sentosa", "Jurong", "Tampines"],
        "sydney": ["Surry Hills", "Bondi", "Manly", "Parramatta", "Chatswood", "Newtown", "Darlinghurst"]
    }

    @staticmethod
    def suggest_locations(query: str) -> list[str]:
        """
        Returns a list of suggested locations with advanced relevance scoring.
        Matches the behavior shown in browser searches for 'aus'.
        """
        if not query or len(query) < 2:
            return []
            
        import requests
        import urllib.parse

        def norm(s: str) -> str:
            return s.lower().strip()

        def quick_levenshtein(s1, s2):
            if len(s1) < len(s2): return quick_levenshtein(s2, s1)
            if not s2: return len(s1)
            previous_row = range(len(s2) + 1)
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row
            return previous_row[-1]

        def relevance_score(q: str, display_name: str, components: list[str]) -> float:
            nq = norm(q)
            score = 0.0
            
            # 1. Check primary name (first part of display_name)
            primary_name = norm(display_name.split(",")[0])
            if primary_name == nq: score += 15
            elif primary_name.startswith(nq): score += 10
            
            # 2. Check all components
            for comp in components:
                ncomp = norm(comp)
                if not ncomp: continue
                if ncomp == nq: score += 5
                elif ncomp.startswith(nq): score += 3
                
                # Fuzzy factor
                lv = quick_levenshtein(ncomp[:max(len(ncomp), len(nq))], nq)
                denom = max(len(ncomp), len(nq), 1)
                score += 2 * (1 - min(1, lv / denom))
                
            return score

        # Auto-Correction for common typos and country names
        corrections = {
            "itlay": "Italy",
            "itly": "Italy",
            "aus": "Australia",
            "pak": "Pakistan",
            "pk": "Pakistan",
            "us": "United States",
            "usa": "United States",
            "uk": "United Kingdom",
            "uae": "United Arab Emirates",
        }
        
        q_low = query.lower().strip()
        search_query = corrections.get(q_low, query)

        try:
            safe_q = urllib.parse.quote(search_query)
            # Use accept-language to prefer international results
            url = f"https://nominatim.openstreetmap.org/search?q={safe_q}&format=json&addressdetails=1&limit=20&accept-language=en"
            
            headers = {
                "User-Agent": "LeadStation_CRM_V2_Global_Browser_v5",
                "Accept": "application/json"
            }
            
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code != 200:
                return []
                
            data = response.json()
            items = []
            
            # Famous Cities Priority Map (City -> Country)
            FAMOUS_CITIES = {
                "lahore": "Pakistan",
                "karachi": "Pakistan",
                "london": "United Kingdom",
                "paris": "France",
                "tokyo": "Japan",
                "dubai": "United Arab Emirates",
                "sydney": "Australia",
                "toronto": "Canada",
            }
            
            for d in data:
                addr = d.get("address", {})
                display_full = d.get("display_name", "")
                
                # Extract components for better labeling
                city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("suburb") or ""
                state = addr.get("state") or addr.get("province") or addr.get("region") or ""
                country = addr.get("country", "")
                
                # Force English names even if Nominatim returns local script
                if not any(ord(c) < 128 for c in city) and addr.get("name"):
                    city = addr.get("name")
                
                # 1. Formatting: City, State, Country
                if city:
                    name = f"{city}, {country}" if not state or state.lower() == city.lower() else f"{city}, {state}, {country}"
                elif state:
                    name = f"{state}, {country}"
                else:
                    name = country or display_full.split(",")[0]

                if not name: continue
                
                # 2. Advanced Scoring
                score = relevance_score(search_query, display_full, [city, state, country])
                
                # Boost for famous city-country matches (e.g. Lahore -> Pakistan)
                if city.lower() in FAMOUS_CITIES and FAMOUS_CITIES[city.lower()].lower() == country.lower():
                    score += 20

                # Penalty for US results if the query doesn't explicitly mention US 
                if "united states" in country.lower() and "usa" not in search_query.lower() and "united states" not in search_query.lower():
                    score -= 10
                
                # Massive boost for exact country match
                if country.lower() == norm(search_query):
                    score += 30

                items.append({"name": name, "score": score})
            
            # Sort by score descending
            ranked = sorted(items, key=lambda x: x["score"], reverse=True)
            
            # Unique names limit 12
            seen = set()
            unique_names = []
            for r in ranked:
                if r["name"] not in seen:
                    # Final cleanup: Remove any non-English script parts from the display
                    clean_name = re.sub(r'[^\x00-\x7F]+', '', r["name"]).strip().strip(",")
                    if not clean_name: clean_name = r["name"]
                    
                    unique_names.append(clean_name)
                    seen.add(r["name"])
                    if len(unique_names) >= 12: break
                    
            return unique_names
            
        except Exception as e:
            print(f"[!] Nominatim Suggestion Error: {str(e)}")
            q_low = query.lower().strip()
            return [c.title() for c in GeoService.CITY_ZONES.keys() if q_low in c.lower()][:5]

    @staticmethod
    def geocode_forward(query: str) -> list[dict]:
        """Python implementation of your geocodeForwardFull method"""
        import requests, urllib.parse
        safe_q = urllib.parse.quote(query)
        url = f"https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&limit=10&q={safe_q}"
        res = requests.get(url, headers={"User-Agent": "persona-cv/1.0"})
        if res.status_code != 200: return []
        data = res.json()
        results = []
        for d in data:
            addr = d.get("address", {})
            city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("hamlet") or ""
            country = addr.get("country", "")
            results.append({
                "id": str(d.get("place_id")),
                "city": city,
                "country": country,
                "lat": float(d.get("lat", 0)),
                "lon": float(d.get("lon", 0)),
                "name": ", ".join(filter(None, [city, country]))
            })
        return results

    @staticmethod
    def reverse_geocode(lat: float, lon: float) -> dict:
        """Python implementation of your reverseGeocode method"""
        import requests
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&addressdetails=1&lat={lat}&lon={lon}"
        res = requests.get(url, headers={"User-Agent": "persona-cv/1.0"})
        if res.status_code != 200: return {}
        d = res.json()
        addr = d.get("address", {})
        city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("hamlet") or ""
        country = addr.get("country", "")
        return {
            "city": city,
            "country": country,
            "name": ", ".join(filter(None, [city, country]))
        }

    @staticmethod
    def get_infinite_grid(category: str, location: str, max_results: int) -> list[str]:
        """
        Bypasses the 120-result Google Maps limit by fetching the bounding box of the target location 
        and slicing it into a mathematical grid of GPS coordinates.
        """
        import requests, urllib.parse, random
        
        print(f" [*] Infinite Grid Dispatcher initializing for: {location}")
        
        # If the requested quota is small (< 500), just use the standard sub_queries method to save time
        if max_results < 500:
            print(" [*] Quota < 500, falling back to standard area dispatch.")
            return GeoService.get_sub_queries(category, location)
            
        safe_q = urllib.parse.quote(location)
        url = f"https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&limit=1&q={safe_q}"
        try:
            res = requests.get(url, headers={"User-Agent": "leadgen-infinite/1.0"})
            if res.status_code == 200 and res.json():
                data = res.json()[0]
                if "boundingbox" in data:
                    min_lat, max_lat, min_lon, max_lon = map(float, data["boundingbox"])
                    
                    # Calculate how many points we need. For "every street" level detail, we increase density.
                    # We assume ~50 unique results per grid point to avoid missing local spots.
                    target_points = min(max_results // 50 + 1, 500) # Max 500 points for extreme coverage
                    
                    lat_span = max_lat - min_lat
                    lon_span = max_lon - min_lon
                    
                    # If it's a tiny area (e.g., a single small town), don't grid it
                    if lat_span < 0.05 or lon_span < 0.05:
                        print(" [*] Area too small for grid, falling back to standard dispatch.")
                        return GeoService.get_sub_queries(category, location)
                        
                    # Calculate step size to achieve target_points
                    area = lat_span * lon_span
                    step = (area / target_points) ** 0.5
                    
                    # Ensure step is at least 0.05 (~3 miles) to prevent overlapping searches
                    step = max(step, 0.05)
                    
                    queries = []
                    # Create grid points
                    curr_lat = min_lat
                    while curr_lat <= max_lat:
                        curr_lon = min_lon
                        while curr_lon <= max_lon:
                            queries.append(f"{category} near {curr_lat:.4f},{curr_lon:.4f}")
                            curr_lon += step
                        curr_lat += step
                        
                    print(f" [*] Grid Dispatcher generated {len(queries)} coordinate zones for massive extraction.")
                    
                    if not queries:
                        return GeoService.get_sub_queries(category, location)
                    
                    # Shuffle queries to ensure distributed sampling across the state/country
                    random.shuffle(queries)
                    
                    return queries[:target_points]
                    
        except Exception as e:
            print(f" [!] Grid Dispatcher failed to fetch bounding box: {e}")
            
        print(" [*] Falling back to standard sub_queries")
        return GeoService.get_sub_queries(category, location)

    # Intelligence mapping for broad geographic areas (Countries, States, Provinces)
    # When a broad area is selected, we dispatch queries to its major hubs.
    GLOBAL_LOCATIONS = {
        "australia": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Gold Coast", "Canberra", "Hobart"],
        "united states": ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio", "San Diego", "Dallas", "Austin"],
        "united kingdom": ["London", "Birmingham", "Manchester", "Glasgow", "Liverpool", "Leeds", "Sheffield", "Edinburgh"],
        "canada": ["Toronto", "Montreal", "Vancouver", "Calgary", "Ottawa", "Edmonton", "Winnipeg", "Quebec City"],
        "pakistan": ["Karachi", "Lahore", "Islamabad", "Faisalabad", "Rawalpindi", "Multan", "Peshawar", "Gujranwala"],
        "united arab emirates": ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah", "Fujairah"],
        "germany": ["Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt", "Stuttgart", "Dusseldorf", "Leipzig"],
        "france": ["Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Nantes", "Strasbourg", "Montpellier"],
        "italy": ["Rome", "Milan", "Naples", "Turin", "Palermo", "Genoa", "Bologna", "Florence"],
        
        # States / Provinces
        "california": ["Los Angeles", "San Francisco", "San Diego", "San Jose", "Sacramento"],
        "texas": ["Houston", "San Antonio", "Dallas", "Austin", "Fort Worth"],
        "punjab": ["Lahore", "Faisalabad", "Rawalpindi", "Multan", "Gujranwala"],
        "ontario": ["Toronto", "Ottawa", "Mississauga", "Brampton", "Hamilton"],
        "new south wales": ["Sydney", "Newcastle", "Wollongong", "Central Coast"],
    }

    @staticmethod
    def get_sub_queries(category: str, location: str) -> list[str]:
        """
        Takes a category and location, and returns a list of specific search queries.
        Optimized to handle Cities, States, and Countries with priority routing.
        """
        location_clean = location.lower().strip()
        
        # 1. PRIORITY: Check for Manual City Zone Mapping (Deep local scrape)
        # If the user specifies a known city, we dive into its neighborhoods.
        for city, zones in GeoService.CITY_ZONES.items():
            if city in location_clean:
                print(f" [*] Major city detected: '{city}'. Using top 4 neighborhoods for fast results.")
                country_hint = location.strip()
                # Limit to 4 zones max — fast first results, avoid 20-min waits
                top_zones = zones[:4]
                return [f"{category} in {zone}, {city.title()}, {country_hint}" for zone in top_zones]

        # 2. SECONDARY: Check for Country/State Intelligence Mapping
        # If no specific city is found but a broad area is mentioned, we hit major hubs.
        for area, hubs in GeoService.GLOBAL_LOCATIONS.items():
            if area in location_clean:
                print(f" [*] Broad area detected: '{area}'. Dispatching to {len(hubs)} hubs.")
                # Include both hub and full area for unambiguous geo context
                return [f"{category} in {hub}, {location.strip()}" for hub in hubs]
        
        # 3. FALLBACK: Smart Global Splitter (For unknown locations)
        # Splits the search into geographic sectors to maximize results.
        print(f" [*] Applying Global Sector Splitter for: '{location}'")
        sectors = ["North", "South", "East", "West", "Central", "Downtown"]
        return [f"{category} in {sector} {location.strip()}" for sector in sectors]
