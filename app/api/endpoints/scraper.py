from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import os
import uuid
import threading
import json
import requests
import csv
import re

from app.services.scraper.maps_scraper import GoogleMapsScraper
from app.db.database import get_db
from app.models.models import User, ScrapeJob
from app.schemas.schemas import ScrapeJobResponse
from app.api.endpoints.users import get_current_user

router = APIRouter(tags=["Maps Scraper Data"])

@router.get("/locations/suggest")
def suggest_locations(q: str):
    """
    Returns a list of location suggestions based on the query string.
    """
    from app.services.scraper.geo_service import GeoService
    return GeoService.suggest_locations(q)

# ─────────────────────────────────────────────────────────────────────────────
# In-memory job store for active scrape jobs
# Key: job_uuid, Value: { status, error, count, csv_url, json_url, job_id }
# NOTE: `data` (full results) is intentionally NOT stored here.
# Results live on disk as JSON files and are fetched from there by the frontend.
# ─────────────────────────────────────────────────────────────────────────────
_job_store: Dict[str, Dict[str, Any]] = {}

META_DIR = os.path.join("storage", "exports")

def slugify(text: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]+', '_', text).strip('_').lower()

def _save_meta(job_uuid: str, payload: dict):
    """Persist job metadata to disk so it survives server restarts."""
    os.makedirs(META_DIR, exist_ok=True)
    path = os.path.join(META_DIR, f"{job_uuid}.meta.json")
    try:
        with open(path, "w") as f:
            json.dump(payload, f)
    except Exception as e:
        print(f"[!] Failed to save meta for {job_uuid}: {e}")


def _load_meta(job_uuid: str) -> Optional[dict]:
    """Load job metadata from disk if not found in memory."""
    path = os.path.join(META_DIR, f"{job_uuid}.meta.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Failed to read meta for {job_uuid}: {e}")
    return None


class ScrapeRequest(BaseModel):
    category: str
    location: Optional[str] = ""
    max_results: Optional[int] = None


def _run_scrape_job(job_uuid: str, query: str, category: str, max_results: Optional[int], user_id: int):
    """
    Runs the full scrape pipeline in a daemon thread with incremental updates.
    """
    from app.db.database import SessionLocal

    _job_store[job_uuid]["status"] = "running"
    print(f"[*] Initializing Discovery Engine for Job: {job_uuid}")
    discovery_engine = GoogleMapsScraper()
    
    # Track results incrementally
    safe_query = slugify(query)
    json_filename = f"export_{safe_query}_{job_uuid}.json"
    json_path = os.path.join("storage", "exports", json_filename)
    os.makedirs(os.path.dirname(json_path), exist_ok=True)

    # Cumulative results tracking
    master_results = []
    results_lock = threading.Lock()

    def on_data_callback(new_chunk):
        """Merges new chunk into master list and updates UI state."""
        nonlocal master_results
        
        with results_lock:
            # 1. Standardize fields for new items
            for item in new_chunk:
                if "generated_site_url" not in item: item["generated_site_url"] = ""
                if "generated_domain" not in item: item["generated_domain"] = ""
                if "audit_report_url" not in item: item["audit_report_url"] = ""
                if "ai_status" not in item: item["ai_status"] = "Pending..."
                if "ai_reason" not in item: item["ai_reason"] = "Waiting for analysis..."
                if "category" not in item: item["category"] = category
            
            # 2. Merge & Update Existing Items (Deduplicated by maps_url)
            # Create a lookup map for existing results
            master_map = {r.get("maps_url"): i for i, r in enumerate(master_results) if r.get("maps_url")}
            
            for item in new_chunk:
                m_url = item.get("maps_url")
                if m_url in master_map:
                    # Update existing lead with new data (e.g. AI status, reports)
                    idx = master_map[m_url]
                    master_results[idx].update(item)
                else:
                    # Add as new lead
                    master_results.append(item)
                    master_map[m_url] = len(master_results) - 1

            # 3. Update job store
            _job_store[job_uuid]["count"] = len(master_results)
            _job_store[job_uuid]["data"] = master_results 
            
            # 4. Persist to disk
            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(master_results, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[!] Error saving results for {job_uuid}: {e}")

    try:
        from app.services.scraper.geo_service import GeoService
        
        max_r = max_results or 50000
        
        # Determine location
        loc = query.replace(category, "").replace(" in ", "").strip()
        
        if not loc:
            sub_queries = [category]
        else:
            sub_queries = GeoService.get_sub_queries(category, loc)
        
        # ── PHASE 1: RAW SCRAPING ──────────────────────────────────
        # Collect all place data and stream to UI immediately.
        # Job is marked 'done' after this — user gets results fast.
        raw_results = discovery_engine.scrape_only(
            queries=sub_queries,
            max_results=max_r,
            on_data=on_data_callback
        )

        # Export raw results right away
        csv_filename = f"export_{safe_query}_{job_uuid}.csv"
        json_filename = f"export_{safe_query}_{job_uuid}.json"
        csv_path = os.path.join("storage", "exports", csv_filename)
        json_path = os.path.join("storage", "exports", json_filename)

        discovery_engine.export_csv(raw_results, csv_path)
        discovery_engine.export_json(raw_results, json_path)

        csv_url = f"/storage/exports/{csv_filename}"
        json_url = f"/storage/exports/{json_filename}"

        # Persist DB record
        db = SessionLocal()
        try:
            job = ScrapeJob(
                user_id=user_id,
                category=category,
                location=query,
                query_string=query,
                csv_file_url=csv_url,
                json_file_url=json_url
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            db_job_id = job.id
        finally:
            db.close()

        # Mark job as DONE for scraping — UI can show results now
        meta = {
            "status": "done",
            "count": len(raw_results),
            "csv_url": csv_url,
            "json_url": json_url,
            "job_id": db_job_id,
            "error": None,
            "ai_status": "auditing",  # AI is still running in background
        }
        _job_store[job_uuid].update(meta)
        _job_store[job_uuid]["data"] = raw_results
        _save_meta(job_uuid, _job_store[job_uuid])

        print(f"[*] Scrape job {job_uuid} — Phase 1 done. {len(raw_results)} leads ready. Launching AI in background...")

        # ── PHASE 2: AI AUDIT IN BACKGROUND ───────────────────────
        # Runs after job is 'done' — updates the JSON file progressively.
        def run_background_ai():
            def ai_update_callback(updated_results):
                """Save incremental AI updates to disk so UI can see them."""
                try:
                    _job_store[job_uuid]["data"] = updated_results
                    _job_store[job_uuid]["count"] = len(updated_results)
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(updated_results, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"[!] AI update save error: {e}")

            try:
                discovery_engine.run_ai_pipeline(raw_results, on_data=ai_update_callback)
                # Final save
                discovery_engine.export_csv(raw_results, csv_path)
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(raw_results, f, indent=2, ensure_ascii=False)
                _job_store[job_uuid]["ai_status"] = "complete"
                print(f"[*] Background AI pipeline complete for {job_uuid}.")
            except Exception as e:
                print(f"[!] Background AI pipeline error for {job_uuid}: {e}")
                _job_store[job_uuid]["ai_status"] = "error"

        ai_thread = threading.Thread(target=run_background_ai, daemon=True)
        ai_thread.start()

        # Trigger n8n if configured
        n8n_webhook = os.getenv("N8N_SCRAPE_COMPLETE_WEBHOOK")
        if n8n_webhook:
            try:
                requests.post(n8n_webhook, json=meta, timeout=10)
            except Exception:
                pass

    except Exception as e:
        print(f"[!] Scrape job {job_uuid} failed: {e}")
        error_meta = {"status": "error", "error": str(e), "count": 0}
        _job_store[job_uuid] = error_meta
        _save_meta(job_uuid, error_meta)


@router.post("/lead")
def start_scrape(
    request: ScrapeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Starts a Maps scrape job in the background and returns a job_id immediately.
    The client should poll GET /api/leads/{job_id} for status.
    When status is 'done', the client fetches results from json_url directly.
    """
    category_clean = request.category.strip()
    location_clean = request.location.strip()

    if not location_clean:
        query = category_clean
    elif category_clean.lower() in location_clean.lower():
        # Prevent duplication if user typed "mosque" in category and "mosque in Pakistan" in location
        query = location_clean
    else:
        query = f"{category_clean} in {location_clean}"
    print(f"[*] Queuing scrape job: {query}")

    job_uuid = str(uuid.uuid4())
    _job_store[job_uuid] = {"status": "queued", "count": 0, "error": None}

    thread = threading.Thread(
        target=_run_scrape_job,
        args=(job_uuid, query, request.category, request.max_results, current_user.id),
        daemon=True,
    )
    thread.start()

    return {
        "job_id": job_uuid, 
        "status": "queued", 
        "query": query,
        "message": "High-performance scraper active. Extracting leads with optimized speed and AI auditing."
    }


@router.get("/lead/{job_id}")
def get_scrape_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Polls the status of a running or completed scrape job.
    Returns status: 'queued' | 'running' | 'done' | 'error'
    On 'done': includes count, csv_url, json_url, job_id (DB id).
    NOTE: Full data is NOT returned here — fetch from json_url instead.
    Falls back to disk meta if job is no longer in memory (e.g. after restart).
    """
    job = _job_store.get(job_id)
    if not job:
        job = _load_meta(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found. It may have expired or never existed.")
    
    # Lazy load data if missing but status is done or running (from disk)
    if (job.get("status") in ["done", "running"]) and "data" not in job:
        json_url = job.get("json_url") or f"/storage/exports/export_{slugify(job.get('query_string', ''))}_{job_id}.json"
        json_path = json_url.lstrip("/")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    job["data"] = json.load(f)
            except Exception:
                pass
    return job


@router.get("/leads")
def get_user_scrape_history(
    scope: str = "mine",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        if scope == "all" and current_user.role == "super_admin":
            # Join with User to show who ran what
            jobs = db.query(ScrapeJob, User.email).join(User, ScrapeJob.user_id == User.id).order_by(ScrapeJob.created_at.desc()).all()
            return [
                {
                    "id": job.ScrapeJob.id,
                    "query_string": job.ScrapeJob.query_string,
                    "csv_url": job.ScrapeJob.csv_file_url,
                    "json_url": job.ScrapeJob.json_file_url,
                    "created_at": job.ScrapeJob.created_at,
                    "user_email": job.email
                }
                for job in jobs
            ]
        
        # Default: Only show current user's data
        jobs = db.query(ScrapeJob).filter(
            ScrapeJob.user_id == current_user.id
        ).order_by(ScrapeJob.created_at.desc()).all()

        return [
            {
                "id": job.id,
                "query_string": job.query_string,
                "csv_url": job.csv_file_url,
                "json_url": job.json_file_url,
                "created_at": job.created_at,
            }
            for job in jobs
        ]
    except Exception:
        import traceback
        raise HTTPException(status_code=500, detail=traceback.format_exc())


@router.delete("/lead/{job_id}")
def delete_scrape_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deletes a specific scrape job from DB and its associated files from disk.
    """
    job = db.query(ScrapeJob).filter(ScrapeJob.id == job_id, ScrapeJob.user_id == current_user.id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Extraction not found or unauthorized.")

    # File Cleanup
    try:
        csv_path = job.csv_file_url.lstrip("/")
        json_path = job.json_file_url.lstrip("/")
        meta_path = os.path.join(META_DIR, f"{job_id}.meta.json")

        for path in [csv_path, json_path, meta_path]:
            if os.path.exists(path):
                os.remove(path)
    except Exception as e:
        print(f"[!] Error deleting files for job {job_id}: {e}")

    db.delete(job)
    db.commit()

    return {"status": "success", "message": "Extraction eradicated successfully."}

class ReAuditRequest(BaseModel):
    lead_id: str
    job_uuid: Optional[str] = None

@router.post("/lead/re-audit")
async def re_audit_lead(
    request: ReAuditRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Manually re-triggers AI analysis for a single lead. 
    Now automatically searches for the job if job_uuid is not provided.
    """
    if not os.path.exists(META_DIR):
        os.makedirs(META_DIR, exist_ok=True)
        
    target_job_uuid = request.job_uuid
    found_path = ""

    # 1. Find which job this lead belongs to
    if not target_job_uuid:
        print(f"[*] Searching for Lead ID: {request.lead_id} in {META_DIR}")
        for filename in os.listdir(META_DIR):
            if filename.endswith(".json") and not filename.endswith(".meta.json"):
                temp_path = os.path.join(META_DIR, filename)
                try:
                    with open(temp_path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if not content: continue
                        leads_list = json.loads(content)
                        if any(l.get("id") == request.lead_id for l in leads_list):
                            target_job_uuid = filename.replace(".json", "")
                            found_path = temp_path
                            print(f"[*] Found lead in job: {target_job_uuid}")
                            break
                except Exception as e:
                    print(f"[!] Warning: Could not read {filename}: {e}")
                    continue
    else:
        found_path = os.path.join(META_DIR, f"{target_job_uuid}.json")

    if not target_job_uuid or not os.path.exists(found_path):
        raise HTTPException(status_code=404, detail="Lead not found in any existing jobs")

    # 2. Load results
    with open(found_path, "r", encoding="utf-8") as f:
        leads = json.load(f)

    # 3. Find the lead
    target_lead = next((l for l in leads if l.get("id") == request.lead_id), None)
    if not target_lead:
        raise HTTPException(status_code=404, detail="Lead not found in this job")

    # 3. Perform Audit
    try:
        from app.services.builder.ai_service import AISiteService
        ai_service = AISiteService()
        
        # Clear old error status
        target_lead["ai_status"] = "Retrying Analysis..."
        target_lead["ai_reason"] = "Manual retry triggered."

        # Run Audit
        print(f" [*] Re-triggering Audit for: {target_lead.get('name')} at {target_lead.get('website')}")
        audit = ai_service.analyze_website(target_lead.get("website", ""), {
            "name": target_lead.get("name"),
            "category": target_lead.get("category", "")
        })

        actual_status = audit.get("status", "Issues")
        report_text = audit.get("report", "")
        
        # Create folder & report if needed
        import hashlib, re
        stable_id = target_lead.get("place_id") or target_lead.get("maps_url", "")
        url_hash = hashlib.md5(stable_id.encode()).hexdigest()[:8]
        raw_name = target_lead.get("name", "lead").lower()
        clean_name = re.sub(r'[^a-z0-9]+', '-', raw_name).strip('-')
        folder_name = f"{clean_name}-{url_hash}"
        lead_path = os.path.join("storage", "leads", folder_name)

        report_url = ""
        if actual_status != "No Issue" and report_text:
            report_url = ai_service.create_audit_report_file(
                target_lead.get("name", "Lead"),
                report_text,
                lead_path
            )

        # Update lead in place with fresh intelligence & contacts
        target_lead["ai_status"] = actual_status
        target_lead["ai_reason"] = audit.get("reason", "Analysis Complete")
        target_lead["ai_report"] = report_text
        target_lead["audit_report_url"] = report_url
        target_lead["lead_folder"] = folder_name

        # Ensure contact fields exist
        if "social_links" not in target_lead: target_lead["social_links"] = ""
        if "emails" not in target_lead: target_lead["emails"] = ""
        if "whatsapp" not in target_lead: target_lead["whatsapp"] = ""

        if audit.get("social_links"):
            # Cleanly merge social footprints without duplicates
            existing_links = [l.strip() for l in target_lead.get("social_links", "").split(",") if l.strip()]
            new_links = [l.strip() for l in audit["social_links"].split(",") if l.strip()]
            combined = list(dict.fromkeys(existing_links + new_links)) # Preserve order + dedupe
            target_lead["social_links"] = ", ".join(combined)
        
        if audit.get("emails"):
            # Update emails if AI found new ones
            existing_emails = [e.strip() for e in target_lead.get("emails", "").split(",") if e.strip()]
            new_emails = [e.strip() for e in audit["emails"].split(",") if e.strip()]
            combined_emails = list(dict.fromkeys(existing_emails + new_emails))
            target_lead["emails"] = ", ".join(combined_emails)
        
        if audit.get("whatsapp") and not target_lead.get("whatsapp"):
            target_lead["whatsapp"] = audit["whatsapp"]

        # 4. Save back to JSON
        with open(found_path, "w", encoding="utf-8") as f:
            json.dump(leads, f, indent=2, ensure_ascii=False)

        # 5. Save back to CSV if it exists
        csv_path = found_path.replace(".json", ".csv")
        if os.path.exists(csv_path):
            try:
                import pandas as pd
                df = pd.read_csv(csv_path)
                if "id" in df.columns:
                    mask = df["id"] == request.lead_id
                    if mask.any():
                        df.loc[mask, "ai_status"] = actual_status
                        df.loc[mask, "ai_reason"] = target_lead["ai_reason"]
                        df.loc[mask, "ai_report"] = report_text
                        df.loc[mask, "audit_report_url"] = report_url
                        df.loc[mask, "lead_folder"] = folder_name
                        df.to_csv(csv_path, index=False)
                        print(f"[*] Updated CSV file: {csv_path}")
            except Exception as csv_err:
                print(f"[!] Error updating CSV: {csv_err}")

        # Final check: Ensure the report URL is clean for the frontend
        if target_lead["audit_report_url"] and target_lead["audit_report_url"].startswith("/"):
            # If your frontend prefers "leads/..." instead of "/storage/leads/..."
            # we can strip the prefix here if needed, but usually /storage/ is better.
            pass

        return target_lead

    except Exception as e:
        target_lead["ai_status"] = "Analysis Error"
        target_lead["ai_reason"] = f"Retry Failed: {str(e)}"
        # Still save the new error reason
        if 'found_path' in locals() and os.path.exists(found_path):
            with open(found_path, "w", encoding="utf-8") as f:
                json.dump(leads, f, indent=2, ensure_ascii=False)
        return target_lead
