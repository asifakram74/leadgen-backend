# Updated Google Maps Scraper — Sequential Pipeline Version
# Phase 1: Extract + Stream to Frontend
# Phase 2: Run AI Audit on ALL leads
# Phase 3: Run AI Builder

import time
import random
import uuid
import os

from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from app.services.scraper.scroll_engine import scroll_results
from app.services.scraper.parser import parse_place_details
from app.services.scraper.dedup import deduplicate
from app.services.builder.ai_service import AISiteService
from app.services.scraper.browser_manager import get_browser_context, block_heavy_resources

# ─────────────────────────────────────────────────────────────
# Trust Scoring
# ─────────────────────────────────────────────────────────────

def _score_trust(data: dict) -> str:
    try:
        # Handle "4.0" as float then int
        r_str = str(data.get("rating", "0")).strip()
        rating = float(r_str) if r_str else 0.0
        
        rev_str = str(data.get("reviews", "0")).replace(",", "").strip()
        reviews = int(float(rev_str)) if rev_str else 0
    except Exception:
        return "Unknown"

    if rating >= 4.5 and reviews >= 10:
        return "Elite"
    if rating >= 4.0:
        return "Trustworthy"
    if rating >= 3.0:
        return "Verified" if reviews >= 20 else "Growing"
    if rating > 0:
        return "At Risk"

    return "Unknown"

# ─────────────────────────────────────────────────────────────
# Worker — Extract Place Details (FAST ONLY)
# ─────────────────────────────────────────────────────────────

def _process_place_batch(
    links,
    start_idx,
    total,
    worker_id,
    headless,
    location_query,
    job_id,
):

    results = []

    with sync_playwright() as p:

        # Use persistent context ('pycache' browser)
        context = get_browser_context(p, worker_id=worker_id, headless=headless)

        try:
            for local_idx, link in enumerate(links):

                page = context.new_page()
                block_heavy_resources(page)
                page.set_default_timeout(15000)

                Stealth().apply_stealth_sync(page)

                try:

                    print(
                        f" [W{worker_id}][{start_idx+local_idx+1}/{total}] Extracting"
                    )

                    page.goto(
                        link,
                        timeout=15000,
                        wait_until="domcontentloaded",
                    )

                    data = parse_place_details(page)

                    if not data:
                        continue

                    data["maps_url"] = link
                    data["id"] = str(uuid.uuid4())
                    data["is_trustworthy"] = _score_trust(data)

                    website = data.get("website")

                    if website:
                        data["ai_status"] = "Pending AI Audit"
                        data["ai_reason"] = "Waiting for Phase 2"
                    else:
                        data["ai_status"] = "Missing"
                        data["ai_reason"] = "No website"

                    data["generated_site_url"] = ""
                    data["generated_domain"] = ""
                    data["audit_report_url"] = ""
                    data["ai_report"] = ""

                    results.append(data)

                except Exception as e:
                    print("Worker error:", e)

                finally:
                    page.close()

        finally:
            context.close()

    return results

# ─────────────────────────────────────────────────────────────
# Main Scraper
# ─────────────────────────────────────────────────────────────

class GoogleMapsScraper:

    def __init__(self, headless=True, job_id=None):
        self.headless = headless
        self.job_id = job_id

    # ─────────────────────────────────────────────────────────

    def collect_links(self, query: str, max_results=1000):

        place_links = []

        with sync_playwright() as p:

            # Use worker_id 999 for the search phase 'pycache'
            context = get_browser_context(p, worker_id=999, headless=self.headless)

            page = context.new_page()
            
            # Speed optimization: Block heavy resources in search phase too
            block_heavy_resources(page)
            Stealth().apply_stealth_sync(page)

            url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}?hl=en"

            print(f"Searching Maps: {query}")
            
            # Retry loop for Goto
            for attempt in range(3):
                try:
                    # 'domcontentloaded' is safer to ensure feed is populated instead of just 'commit'
                    page.goto(url, timeout=45000, wait_until="domcontentloaded")
                    break
                except Exception as e:
                    if attempt == 2: raise e
                    print(f" [!] Search attempt {attempt+1} failed. Retrying...")
                    time.sleep(random.uniform(2, 5))

            # Handle potential Google consent page (common on VPS in EU/UK)
            try:
                reject_btn = page.locator("button:has-text('Reject all')")
                if reject_btn.is_visible(timeout=2000):
                    reject_btn.click(timeout=2000)
                else:
                    accept_btn = page.locator("button:has-text('Accept all')")
                    if accept_btn.is_visible(timeout=2000):
                        accept_btn.click(timeout=2000)
            except Exception:
                pass

            # Small wait for results to populate after load
            try:
                page.wait_for_selector("div[role='feed']", timeout=15000)
            except Exception:
                print(" [!] Results feed not found or timed out. Attempting anyway...")

            # 25 scrolls is enough for most searches — 100 was 4x too slow
            scroll_results(page, max_scrolls=25)

            cards = page.query_selector_all("a.hfpxzc")
            
            if not cards:
                print(f" [!] No cards found for {query}. Saving debug info...")
                os.makedirs("storage/logs", exist_ok=True)
                debug_id = str(uuid.uuid4())[:8]
                try:
                    page.screenshot(path=f"storage/logs/debug_map_{debug_id}.png")
                    with open(f"storage/logs/debug_map_{debug_id}.html", "w", encoding="utf-8") as f:
                        f.write(page.content())
                    print(f" [!] Debug info saved to storage/logs/debug_map_{debug_id}.png")
                except Exception as e:
                    print(f" [!] Failed to save debug info: {e}")

            for a in cards:
                href = a.get_attribute("href")
                if href and "/maps/place/" in href:
                    if href not in place_links:
                        place_links.append(href)

            context.close()

        return place_links[:max_results]

    # ─────────────────────────────────────────────────────────

    def _scrape_zone_task(self, query, limit, on_data_callback):
        """Collects links and extracts place details. Streams raw data immediately.
        AI audit runs in a separate background pass."""
        try:
            links = self.collect_links(query, max_results=limit)
            if not links:
                return []
            
            # Extract basic place details
            results = self.process_links(links, query, on_data=on_data_callback)
            
            # Stream raw results immediately — no AI blocking
            if results and on_data_callback:
                on_data_callback(results)
            
            return results
        except Exception as e:
            print(f" [!] Zone task failed for {query}: {e}")
            raise e

    def scrape_only(
        self,
        queries: list[str],
        max_results=1000,
        on_data=None,
    ):
        """
        Phase 1 ONLY: Collect raw place data and stream immediately.
        No AI audit. No AI builder. Returns as soon as all scraping is done.
        """
        all_results = []
        max_r = int(max_results) if max_results else 50000
        
        # Limit per zone based on how many queries we have.
        limit_per_zone = max_r if len(queries) == 1 else 30

        print(f"[Scraper] Phase 1 — Raw collection. Zones: {len(queries)}, limit/zone: {limit_per_zone}")

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(self._scrape_zone_task, q, limit_per_zone, on_data): q
                for q in queries
            }

            for future in as_completed(futures):
                zone_results = future.result()
                if zone_results:
                    for item in zone_results:
                        url = item.get("maps_url")
                        if url and not any(r.get("maps_url") == url for r in all_results):
                            all_results.append(item)

                    if on_data:
                        on_data(all_results[:max_r])

                    print(f" [*] {len(all_results)} raw leads collected so far...")

                if len(all_results) >= max_r:
                    break

        print(f"[Scraper] Phase 1 done — {len(all_results)} total raw leads.")
        return all_results[:max_r]

    def run_ai_pipeline(self, all_results, query: str = "general", on_data=None, model_id: str = "deepseek-chat"):
        """
        Phase 2 ONLY: Run AI audit on already-collected leads.
        """
        print(f"[AI] Starting high-speed audit on {len(all_results)} leads using {model_id} for query: {query}...")
        # Uses the specified model (DeepSeek by default for high quality)
        audited = self._run_ai_audit(all_results, query=query, on_data=on_data, model_id=model_id)
        print(f"[AI] Pipeline complete — {len(audited)} leads audited.")
        return audited

    # ─────────────────────────────────────────────────────────

    def process_links(
        self,
        place_links: list[str],
        query: str,
        on_data=None,
    ):

        all_results = []

        total = len(place_links)

        # Heavily restrict concurrent browsers to prevent CPU/RAM thrashing
        workers_count = min(3, max(1, total // 10 + 1))

        batches = []
        step = max(5, total // workers_count) if workers_count > 0 else 5

        for i in range(0, total, step):
            batches.append(place_links[i:i+step])

        with ThreadPoolExecutor(max_workers=workers_count) as executor:

            futures = {}

            offset = 0

            for idx, batch in enumerate(batches):

                future = executor.submit(
                    _process_place_batch,
                    batch,
                    offset,
                    total,
                    idx,
                    self.headless,
                    query,
                    self.job_id,
                )

                futures[future] = idx

                offset += len(batch)

            for future in as_completed(futures):

                batch_results = future.result()

                if batch_results:

                    all_results.extend(batch_results)

                    if on_data:
                        on_data(
                            deduplicate(all_results)
                        )

        return deduplicate(all_results)

    # ─────────────────────────────────────────────────────────

    def _run_ai_audit(
        self,
        all_results,
        query: str = "general",
        on_data=None,
        model_id: str = "deepseek-chat",
    ):
        import re
        query_slug = re.sub(r'[^a-zA-Z0-9]+', '_', query).strip('_').lower()

        print(f"Starting AI Audit Phase for: {query}")

        def audit_lead(lead):
            if not lead.get("website"):
                lead["ai_status"] = "Skipped"
                return lead

            # Skip re-auditing if lead already has a finalized status from a previous cache
            if lead.get("ai_status") in ["Healthy", "Issues", "No Issue", "complete"]:
                return lead

            try:
                ai_service = AISiteService()
                
                # 1. Perform AI Analysis
                audit = ai_service.analyze_website(
                    lead["website"],
                    {
                        "name": lead.get("name"),
                        "category": lead.get("category"),
                    },
                    model_id=model_id
                )

                lead["ai_status"] = audit.get("status", "Issues")
                lead["ai_reason"] = audit.get("reason", "Analysis Complete")
                lead["ai_report"] = audit.get("report", "")

                # Ensure contact fields exist
                if "social_links" not in lead: lead["social_links"] = ""
                if "emails" not in lead: lead["emails"] = ""
                if "whatsapp" not in lead: lead["whatsapp"] = ""

                if audit.get("social_links"):
                    existing_links = [l.strip() for l in lead.get("social_links", "").split(",") if l.strip()]
                    new_links = [l.strip() for l in audit["social_links"].split(",") if l.strip()]
                    combined = list(dict.fromkeys(existing_links + new_links))
                    lead["social_links"] = ", ".join(combined)
                
                if audit.get("emails"):
                    existing_emails = [e.strip() for e in lead.get("emails", "").split(",") if e.strip()]
                    new_emails = [e.strip() for e in audit["emails"].split(",") if e.strip()]
                    combined_emails = list(dict.fromkeys(existing_emails + new_emails))
                    lead["emails"] = ", ".join(combined_emails)
                
                if audit.get("whatsapp") and not lead.get("whatsapp"):
                    lead["whatsapp"] = audit["whatsapp"]

                # ── 2. Generate Audit Report File (PDF/HTML) ──
                if lead["ai_report"]:
                    # Respect existing lead_folder
                    lead_folder = lead.get("lead_folder")
                    if not lead_folder:
                        raw_name = lead.get("name", "lead")
                        clean_name = re.sub(r'[^a-zA-Z0-9]+', '_', raw_name).strip('_')
                        import hashlib
                        stable_id = lead.get("place_id") or lead.get("maps_url", "")
                        url_hash = hashlib.md5(stable_id.encode()).hexdigest()[:6]
                        lead_folder = f"{query_slug}/{clean_name}_{url_hash}"
                        lead["lead_folder"] = lead_folder
                    
                    full_folder_path = os.path.join("storage", "leads", lead_folder.replace("storage/", "", 1).replace("leads/", "", 1))
                    
                    report_url = ai_service.create_audit_report_file(
                        lead["name"],
                        lead["ai_report"],
                        full_folder_path
                    )
                    
                    # Standardized URLs: HTML for live view, PDF for professional download
                    if report_url.endswith(".html"):
                        html_url = report_url
                        pdf_url = report_url.replace(".html", ".pdf")
                    elif report_url.endswith(".pdf"):
                        pdf_url = report_url
                        html_url = report_url.replace(".pdf", ".html")
                    else:
                        html_url = report_url
                        pdf_url = report_url

                    lead["audit_report_html_url"] = html_url
                    lead["audit_report_pdf_url"] = pdf_url
                    lead["audit_report_url"] = pdf_url # Keep legacy pointing to PDF
                
                # Ensure contact fields exist
                if "social_links" not in lead: lead["social_links"] = ""
                if "emails" not in lead: lead["emails"] = ""
                if "whatsapp" not in lead: lead["whatsapp"] = ""
            except Exception as e:
                lead["ai_status"] = "Analysis Error"
                lead["ai_reason"] = str(e)

            return lead

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(audit_lead, lead)
                for lead in all_results
            ]

            done = 0
            for f in as_completed(futures):
                done += 1
                print(f" [*] Audit Progress: {done}/{len(all_results)}")
                
                # Update UI after EVERY lead for real-time responsiveness
                if on_data:
                    on_data(all_results)

        return all_results

    # ─────────────────────────────────────────────────────────

    def _run_ai_builder(
        self,
        all_results,
        on_data=None,
    ):

        print("Starting AI Builder Phase")

        def build_site(lead):

            if lead.get("ai_status") != "Issues":
                return lead

            try:

                ai_service = AISiteService()

                site_url = ai_service.generate_website(
                    lead
                )

                lead["generated_site_url"] = site_url

            except Exception:

                lead["generated_site_url"] = ""

            return lead

        with ThreadPoolExecutor(max_workers=5) as executor:

            futures = [
                executor.submit(build_site, lead)
                for lead in all_results
            ]

            done = 0

            for f in as_completed(futures):

                done += 1

                if done % 3 == 0:

                    print(
                        f"Builder progress: {done}/{len(all_results)}"
                    )

                    if on_data:
                        on_data(all_results)

        return all_results
    # ─────────────────────────────────────────────────────────
    # Exports
    # ─────────────────────────────────────────────────────────

    def export_csv(self, data: list[dict], path: str):
        """
        Exports the lead data to a CSV file.
        """
        import csv
        if not data:
            print(" [!] No data to export to CSV.")
            return

        print(f" [*] Exporting {len(data)} leads to CSV: {path}")

        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(path), exist_ok=True)

            # Collect all possible keys from all items to ensure no column is missed
            all_keys = set()
            for item in data:
                all_keys.update(item.keys())
            
            # Defined preferred order for main columns
            preferred_order = [
                "name", "category", "website", "phone", "emails", "whatsapp", "social_links", "address", 
                "ai_status", "ai_reason", "audit_report_url", "maps_url",
                "is_trustworthy", "generated_site_url", "generated_domain"
            ]
            
            # Filter and sort fieldnames
            fieldnames = [k for k in preferred_order if k in all_keys]
            # Add any remaining keys that weren't in preferred_order
            remaining_keys = sorted(list(all_keys - set(preferred_order)))
            fieldnames.extend(remaining_keys)

            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(data)
                
            print(f" [+] CSV export successful: {path}")
        except Exception as e:
            print(f" [!] CSV Export Error: {e}")

    def export_json(self, data: list[dict], path: str):
        """
        Exports the lead data to a JSON file.
        """
        import json
        if not data:
            print(" [!] No data to export to JSON.")
            return

        print(f" [*] Exporting {len(data)} leads to JSON: {path}")

        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(path), exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            print(f" [+] JSON export successful: {path}")
        except Exception as e:
            print(f" [!] JSON Export Error: {e}")
