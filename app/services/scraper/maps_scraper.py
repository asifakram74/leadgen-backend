import time
import random
import uuid
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright, Browser
from playwright_stealth import Stealth

from app.services.scraper.scroll_engine import scroll_results
from app.services.scraper.parser import parse_place_details
from app.services.scraper.website_scraper import extract_website_details
from app.services.scraper.dedup import deduplicate
from app.services.builder.ai_service import AISiteService


# ─────────────────────────────────────────────────────────────────────────────
# Concurrency settings
# Each worker gets its OWN browser context (isolated fingerprint/session).
# Workers are staggered so they don't all hit Google simultaneously.
# ─────────────────────────────────────────────────────────────────────────────
CONCURRENT_WORKERS = 3          # Keep ≤3 to stay under Google's radar
WORKER_STAGGER_SECONDS = 2.0    # Delay between starting each worker


# ─────────────────────────────────────────────────────────────────────────────
# Rotating user agents — each context picks a random one to look like
# a different user on a different machine.
# ─────────────────────────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Slightly randomized viewports so no two workers look identical
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 800},
    {"width": 1366, "height": 768},
]


def _score_trust(data: dict) -> str:
    rating_val, reviews_val = 0.0, 0
    try:
        rating_val = float(data.get("rating", "0"))
        reviews_val = int(data.get("reviews", "0").replace(",", ""))
    except Exception:
        pass

    if rating_val >= 4.0:
        return "Trustworthy"
    elif rating_val >= 3.0:
        return "Okay" if reviews_val < 50 else "Average"
    elif rating_val > 0:
        return "Okay" if reviews_val < 50 else "Poor"
    return "Unknown"


def _process_place_batch(links: list[str], start_idx: int, total: int, worker_id: int, headless: bool) -> list[dict]:
    """
    Worker function — runs in a thread pool.
    Each worker MUST have its own playwright instance to avoid greenlet thread-switching errors.
    """
    results = []
    
    with sync_playwright() as p:
        # Launch a dedicated browser for this worker
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        
        # Each worker = isolated context with unique UA + viewport
        ua = USER_AGENTS[worker_id % len(USER_AGENTS)]
        vp = VIEWPORTS[worker_id % len(VIEWPORTS)]

        context = browser.new_context(
            user_agent=ua,
            viewport=vp,
            locale="en-US",
            timezone_id="America/New_York",
            color_scheme="light",
        )

        try:
            for local_idx, link in enumerate(links):
                global_idx = start_idx + local_idx + 1
                page = context.new_page()

                # Apply stealth
                Stealth().apply_stealth_sync(page)

                try:
                    print(f" [W{worker_id}][{global_idx}/{total}] Extracting: {link[:50]}...")
                    page.goto(link, timeout=60000, wait_until="domcontentloaded")

                    # Human-like pause
                    time.sleep(random.uniform(0.5, 1.2))

                    data = parse_place_details(page)
                    if not data:
                        continue

                    data["maps_url"] = link
                    data["id"] = str(uuid.uuid4())
                    data["is_trustworthy"] = _score_trust(data)

                    # Website scraping
                    website_url = data.get("website", "")
                    social_domains = [
                        "facebook.com", "instagram.com", "twitter.com", "x.com",
                        "linkedin.com", "youtube.com", "tiktok.com"
                    ]

                    if website_url and any(d in website_url for d in social_domains):
                        data["social_links"] = website_url
                        data["website"] = ""
                        data["emails"] = ""
                        data["whatsapp"] = ""
                    elif website_url:
                        print(f"   [W{worker_id}] -> Scraping website: {website_url}")
                        web_data = extract_website_details(page, website_url)
                        data["emails"] = ", ".join(web_data.get("emails", []))
                        data["social_links"] = ", ".join(web_data.get("social_links", []))
                        data["whatsapp"] = ", ".join(web_data.get("whatsapp", []))
                    else:
                        data["emails"] = ""
                        data["social_links"] = ""
                        data["whatsapp"] = ""

                    # AI Website Audit (Automatic Analysis)
                    if data.get("website"):
                        print(f"   [W{worker_id}] -> AI Analyzing: {data['website']}")
                        ai_service = AISiteService()
                        audit = ai_service.analyze_website(data["website"], {
                            "name": data.get("name"),
                            "category": data.get("category", "")
                        })
                        data["ai_status"] = audit.get("status")
                        data["ai_reason"] = audit.get("reason")
                    else:
                        data["ai_status"] = "Missing"
                        data["ai_reason"] = "No website link found on Google Maps."

                    results.append(data)

                except Exception as e:
                    print(f" [W{worker_id}][!] Error on place {global_idx}: {e}")
                finally:
                    try:
                        page.close()
                    except Exception:
                        pass

                    # Short cooldown
                    time.sleep(random.uniform(0.3, 0.8))

        finally:
            try:
                context.close()
                browser.close()
            except Exception:
                pass

    return results


class GoogleMapsScraper:
    def __init__(self, headless=True):
        self.headless = headless

    def scrape(self, query: str, max_results=10000, on_data=None):
        all_results = []

        # ── Phase 1: Scroll & collect all place links ──
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ]
            )
            # Use a slightly longer timeout and wait for network idle to ensure everything loads
            search_context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport=random.choice(VIEWPORTS),
                locale="en-US",
                timezone_id="America/New_York",
            )
            search_page = search_context.new_page()
            Stealth().apply_stealth_sync(search_page)

            url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
            print(f" [*] Searching Maps for: {query}")
            search_page.goto(url, timeout=60000)

            try:
                search_page.wait_for_selector("div[role='feed']", timeout=15000)
            except Exception as e:
                print(" [!] Timeout waiting for results feed.", e)

            time.sleep(random.uniform(1.5, 2.5))

            print(" [*] Scrolling to gather all results...")
            scroll_results(search_page, max_scrolls=1500)

            cards = search_page.query_selector_all("a.hfpxzc")
            place_links = []
            for a in cards:
                href = a.get_attribute("href")
                if href and "/maps/place/" in href and href not in place_links:
                    place_links.append(href)

            search_page.close()
            search_context.close()
            browser.close()

            place_links = place_links[:max_results]
            total = len(place_links)
            
            # Using 10 workers if we have 50+ results to ensure we hit the 20-lead first batch quickly
            workers_count = min(10, max(1, total // 5)) if total > 20 else 5
            if total == 0:
                print(" [!] No results found.")
                return []
                
            print(f" [*] Found {total} places. Launching {workers_count} concurrent workers...")

            # ── Phase 2: Split links into optimized batches ──
            # First batch is a burst of 20 for immediate volume (Target: < 20s).
            # Subsequent batches are 10 leads each, staggered for steady delivery.
            all_batches = []
            if total > 0:
                # 1. Immediate Burst Batch
                initial_size = 20
                all_batches.append(place_links[0:initial_size])
                
                # 2. Sequential Rhythm Batches (10 leads each)
                if total > initial_size:
                    rest = place_links[initial_size:]
                    step = 10
                    for i in range(0, len(rest), step):
                        all_batches.append(rest[i:i + step])

            # ── Phase 3: Paced Concurrent Execution ──
            # We use a higher worker count for the initial burst to hit the 20s target.
            with ThreadPoolExecutor(max_workers=workers_count) as executor:
                futures = {}
                running_offset = 0
                for idx, batch in enumerate(all_batches):
                    start_idx = running_offset
                    running_offset += len(batch)
                    
                    worker_id = idx % workers_count
                    future = executor.submit(
                        _process_place_batch,
                        batch, start_idx, total, worker_id, self.headless
                    )
                    futures[future] = idx

                    # Logic: Initial burst moves fast, then we stagger every ~10s 
                    # for that 'heartbeat' feeling on the frontend.
                    if idx == 0:
                        # Allow the first 20 leads to start moving immediately
                        time.sleep(0.5) 
                    else:
                        # Delay subsequent submissions to aim for the 10s rhythm
                        time.sleep(10.0) 

                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        batch_results = future.result()
                        if batch_results:
                            all_results.extend(batch_results)
                            if on_data:
                                on_data(deduplicate(all_results))
                            print(f" [Chunk {idx}] Processed. Total so far: {len(all_results)}")
                    except Exception as e:
                        print(f" [Chunk {idx}] Crashed: {e}")

        final_results = deduplicate(all_results)
        print(f" [*] Final count: {len(final_results)}")
        return final_results

    def export_csv(self, data, path):
        if not data:
            print(" [!] No data to export to CSV.")
            return
        pd.DataFrame(data).to_csv(path, index=False)
        print(f" [*] Data exported to CSV: {path}")

    def export_json(self, data, path):
        if not data:
            print(" [!] No data to export to JSON.")
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f" [*] Data exported to JSON: {path}")