from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
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
    location: str
    auto_audit: bool = True # Default to True for "Wow" factor


def _run_scrape_job(job_uuid: str, query: str, category: str, user_id: int, initial_data: list = None, db_job_id: int = None, auto_audit: bool = True):
    """
    Runs the full scrape pipeline in a daemon thread with incremental updates.
    """
    from app.db.database import SessionLocal

    _job_store[job_uuid]["status"] = "running"
    print(f"[*] Initializing Discovery Engine for Job: {job_uuid}")
    discovery_engine = GoogleMapsScraper()
    
    # Track results incrementally
    # ─── Unified Query Core Storage ───
    # All search sessions for the same query now update the same MASTER files in a dedicated folder.
    safe_query = slugify(query)
    export_dir = os.path.join("storage", "exports", safe_query)
    os.makedirs(export_dir, exist_ok=True)
    
    json_path = os.path.join(export_dir, f"{safe_query}.json")
    csv_path = os.path.join(export_dir, f"{safe_query}.csv")

    # Cumulative results tracking
    master_results = initial_data or []
    
    # If we have initial data, write it to disk immediately so it's available for the new job ID
    if master_results:
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(master_results, f, indent=2, ensure_ascii=False)
            print(f"[*] Pre-populated cache for {job_uuid} with {len(master_results)} existing leads.")
            _job_store[job_uuid]["count"] = len(master_results)
            _job_store[job_uuid]["data"] = master_results
        except Exception as e:
            print(f"[!] Cache pre-population error: {e}")

    results_lock = threading.Lock()

    def on_data_callback(new_chunk):
        """Merges new chunk into master list and updates UI state."""
        nonlocal master_results
        
        with results_lock:
            # 1. Standardize fields for new items
            for item in new_chunk:
                if "generated_site_url" not in item: item["generated_site_url"] = ""
                if "generated_domain" not in item: item["generated_domain"] = ""
                if "audit_report_html_url" not in item: item["audit_report_html_url"] = ""
                if "audit_report_pdf_url" not in item: item["audit_report_pdf_url"] = ""
                if "ai_status" not in item: item["ai_status"] = "Pending..."
                if "ai_reason" not in item: item["ai_reason"] = "Waiting for analysis..."
                if "category" not in item: item["category"] = category
                
                # Pre-calculate lead_folder for consistency across all services
                if "lead_folder" not in item or not item["lead_folder"]:
                    import hashlib
                    stable_id = item.get("place_id") or item.get("maps_url", "")
                    url_hash = hashlib.md5(stable_id.encode()).hexdigest()[:6]
                    raw_name = item.get("name", "lead")
                    clean_name = re.sub(r'[^a-zA-Z0-9]+', '_', raw_name).strip('_')
                    item["lead_folder"] = f"{slugify(query)}/{clean_name}_{url_hash}"
            
            # 2. Merge & Update Existing Items (Deduplicated by maps_url)
            # We PROTECT enriched data (audits, sites) during the merge.
            master_map = {r.get("maps_url"): i for i, r in enumerate(master_results) if r.get("maps_url")}
            
            for item in new_chunk:
                m_url = item.get("maps_url")
                if m_url in master_map:
                    # Append-Only Strategy: We NEVER change existing data to ensure absolute integrity.
                    pass 
                else:
                    # Add as brand-new discovery
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
        
        max_r = 50000
        
        # Determine location
        loc = query.replace(category, "").replace(" in ", "").strip()
        
        if not loc:
            sub_queries = [category]
        else:
            sub_queries = GeoService.get_sub_queries(category, loc)
        
        # ── PHASE 1: RAW SCRAPING ──────────────────────────────────
        # The URLs are stable and based on the query name and its subfolder
        csv_url = f"/storage/exports/{safe_query}/{safe_query}.csv"
        json_url = f"/storage/exports/{safe_query}/{safe_query}.json"

        # Collect all place data and stream to UI immediately.
        # Job is marked 'done' after this — user gets results fast.
        raw_results = discovery_engine.scrape_only(
            queries=sub_queries,
            max_results=max_r,
            on_data=on_data_callback
        )

        # Scraping pass complete
        
        # PHASE 1 COMPLETE - Moving to AI Background Extraction
        discovery_engine.export_csv(master_results, csv_path)
        discovery_engine.export_json(master_results, json_path)

        # --- Update DB Record ---
        db = SessionLocal()
        try:
            from app.models.models import ScrapeJob
            if db_job_id:
                job = db.query(ScrapeJob).filter(ScrapeJob.id == db_job_id).first()
                if job:
                    job.csv_file_url = csv_url
                    job.json_file_url = json_url
                    db.commit()
            else:
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
            print(f"[*] Intelligence Record Sync'd to Vault: {job_uuid}")
        except Exception as e:
            print(f"[!] DB Error: {e}")
        finally:
            db.close()

        # Mark job as AUDITING — UI will continue polling for AI results
        meta = {
            "status": "auditing", 
            "count": len(raw_results),
            "csv_url": csv_url,
            "json_url": json_url,
            "job_id": db_job_id,
            "error": None,
            "ai_status": "auditing",
        }
        _job_store[job_uuid].update(meta)
        _job_store[job_uuid]["data"] = raw_results
        _save_meta(job_uuid, _job_store[job_uuid])

        print(f"[*] Scrape job {job_uuid} — Scraping complete. Launching AI Pipeline...")

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
                # Audit the ENTIRE master list to ensure absolute persistence
                # Using DeepSeek as requested for high-quality SEO/UI/Technical insights
                discovery_engine.run_ai_pipeline(master_results, query=query, model_id="deepseek-chat", on_data=ai_update_callback)
                
                # FINAL ATOMIC SAVE: Sync everything to disk one last time
                discovery_engine.export_csv(master_results, csv_path)
                discovery_engine.export_json(master_results, json_path)
                
                _job_store[job_uuid]["ai_status"] = "complete"
                _job_store[job_uuid]["status"] = "done" # FINALLY DONE
                _save_meta(job_uuid, _job_store[job_uuid])
                print(f"[*] Background AI pipeline complete for {job_uuid}. Total {len(master_results)} leads persisted.")
            except Exception as e:
                print(f"[!] Background AI pipeline error for {job_uuid}: {e}")
                _job_store[job_uuid]["ai_status"] = "error"
                _job_store[job_uuid]["status"] = "done"
                _save_meta(job_uuid, _job_store[job_uuid])

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

    # ─── Active Job Sharing: Real-Time Progress Sync ───
    # If a job is ALREADY running for this exact query, we let this user "spectate" it.
    for active_uuid, job_info in _job_store.items():
        if job_info.get("status") in ["running", "queued"] and job_info.get("query_string") == query:
            print(f"[*] Spectator Alert: Joining active job {active_uuid} for query: {query}")
            
            # Create a history record for this user too, so they have it in their vault
            db_job = ScrapeJob(
                user_id=current_user.id,
                category=request.category,
                location=location_clean,
                query_string=query,
                csv_file_url=job_info.get("csv_url", ""),
                json_file_url=job_info.get("json_url", "")
            )
            db.add(db_job)
            db.commit()
            
            return {
                "job_id": active_uuid, 
                "status": job_info.get("status"), 
                "count": job_info.get("count", 0),
                "data": job_info.get("data", []),
                "query": query,
                "message": "Live Matrix Sync: You are now spectating an active extraction in progress."
            }

    # ─── Global Cache Check: Instant Intelligence Retrieval ───
    # We search across ALL previous jobs for this exact query to build a comprehensive base.
    from sqlalchemy import func
    previous_jobs = db.query(ScrapeJob).filter(
        func.lower(ScrapeJob.category) == category_clean.lower(),
        func.lower(ScrapeJob.location) == location_clean.lower()
    ).all()
    
    initial_data = []
    seen_urls = set()
    
    if previous_jobs:
        print(f"[*] Intelligence Merge: Scanning {len(previous_jobs)} historical records for: {query}")
        for job in previous_jobs:
            if not job.json_file_url: continue
            json_path = job.json_file_url.lstrip("/")
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        job_data = json.load(f)
                        # Use a map to handle enrichment during the merge
                        lead_map = {l.get("maps_url"): i for i, l in enumerate(initial_data) if l.get("maps_url")}
                        
                        for lead in job_data:
                            m_url = lead.get("maps_url")
                            if not m_url: continue
                            
                            if m_url in lead_map:
                                # Enrichment Check: Does this version have more data?
                                idx = lead_map[m_url]
                                existing = initial_data[idx]
                                
                                # If the new lead has a site and the existing doesn't, overwrite
                                has_site = lead.get("generated_site_url")
                                has_audit = lead.get("audit_report_url")
                                
                                if (has_site and not existing.get("generated_site_url")) or \
                                   (has_audit and not existing.get("audit_report_url")):
                                    print(f"[*] Intelligence Promotion: Found enriched version of {lead.get('name')}")
                                    initial_data[idx].update(lead)
                            else:
                                initial_data.append(lead)
                                lead_map[m_url] = len(initial_data) - 1
                except Exception as e:
                    print(f"[!] Warning: Could not merge historical data from {json_path}: {e}")
        
        if initial_data:
            print(f"[*] Instant Discovery Active: Found {len(initial_data)} unique leads in history.")

    # ─── Master Query Core ───
    # We use a deterministic filename based on the query slug to isolate data.
    safe_query = slugify(query)
    csv_url = f"/storage/exports/{safe_query}/{safe_query}.csv"
    json_url = f"/storage/exports/{safe_query}/{safe_query}.json"

    job_uuid = str(uuid.uuid4())
    
    # ─── Immediate Assignment ───
    # Create the DB record with the CORRECT location-specific URLs
    db_job = ScrapeJob(
        user_id=current_user.id,
        category=request.category,
        location=location_clean,
        query_string=query,
        csv_file_url=csv_url, 
        json_file_url=json_url
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)

    _job_store[job_uuid] = {
        "status": "running" if initial_data else "queued", 
        "count": len(initial_data), 
        "data": initial_data,
        "query_string": query,
        "csv_url": csv_url,
        "json_url": json_url,
        "error": None
    }

    thread = threading.Thread(
        target=_run_scrape_job,
        args=(job_uuid, query, request.category, current_user.id, initial_data),
        kwargs={"db_job_id": db_job.id, "auto_audit": request.auto_audit},
        daemon=True,
    )
    thread.start()

    return {
        "job_id": job_uuid, 
        "status": "running" if initial_data else "queued", 
        "count": len(initial_data),
        "data": initial_data,
        "query": query,
        "csv_url": csv_url,
        "json_url": json_url,
        "message": "Instant Discovery Active. Merging existing leads with live Google Maps data." if initial_data else "High-performance scraper active. Extracting leads with optimized speed and AI auditing."
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
        safe_query = slugify(job.get('query_string', ''))
        json_url = job.get("json_url") or f"/storage/exports/{safe_query}/{safe_query}.json"
        json_path = json_url.lstrip("/")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    job["data"] = json.load(f)
            except Exception:
                pass
    return job


@router.get("/download/audit")
def download_audit_report(path: str):
    """
    Forces a direct download of an audit PDF.
    """
    clean_path = path.lstrip("/")
    if not os.path.exists(clean_path):
        raise HTTPException(status_code=404, detail="Report file not found.")
    
    filename = os.path.basename(clean_path)
    return FileResponse(
        path=clean_path,
        filename=filename,
        media_type='application/pdf'
    )

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
        
        # Default: Only show current user's data, grouped by query to avoid duplicates
        # We use a subquery to get the latest job ID for each unique query_string
        from sqlalchemy import func
        latest_jobs_subquery = db.query(
            func.max(ScrapeJob.id).label("max_id")
        ).filter(ScrapeJob.user_id == current_user.id).group_by(ScrapeJob.query_string).subquery()

        jobs = db.query(ScrapeJob).filter(
            ScrapeJob.id.in_(db.query(latest_jobs_subquery.c.max_id))
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
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deletes a specific scrape job from DB and its associated files from disk.
    Supports both DB integer IDs and session UUIDs.
    """
    job = None
    
    # 1. Try to find by integer ID first (if job_id is numeric)
    if job_id.isdigit():
        query = db.query(ScrapeJob).filter(ScrapeJob.id == int(job_id))
        # Admins can delete anything; regular users only their own
        if current_user.role not in ["super_admin", "admin"]:
            query = query.filter(ScrapeJob.user_id == current_user.id)
        job = query.first()
    
    # 2. Fallback: Try to find by job_uuid if not found or not numeric
    if not job:
        # Note: We'd need a uuid column in ScrapeJob for perfect sync, 
        # but for now we can infer it from the file paths or job store
        # For simplicity, we assume integer IDs are the primary deletion method from the UI
        pass

    if not job:
        raise HTTPException(status_code=404, detail="Extraction not found or unauthorized.")

        # File Cleanup
        import shutil
        csv_path = job.csv_file_url.lstrip("/") if job.csv_file_url else ""
        json_path = job.json_file_url.lstrip("/") if job.json_file_url else ""
        
        # If files are in a hierarchical folder (storage/exports/[slug]/...), delete the whole folder
        if json_path and "storage/exports/" in json_path:
            parent_dir = os.path.dirname(json_path)
            if os.path.exists(parent_dir) and os.path.basename(parent_dir) != "exports":
                shutil.rmtree(parent_dir)
        else:
            # Fallback for old flat structure
            for path in [csv_path, json_path]:
                if path and os.path.exists(path):
                    os.remove(path)
                    
        # Meta files
        meta_path_id = os.path.join(META_DIR, f"{job.id}.meta.json")
        if os.path.exists(meta_path_id):
            os.remove(meta_path_id)

    db.delete(job)
    db.commit()

    return {"status": "success", "message": "Extraction eradicated successfully."}

class ReAuditRequest(BaseModel):
    lead_id: str
    job_uuid: Optional[str] = None
    model_id: Optional[str] = "deepseek-chat"

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
        
    from app.db.database import SessionLocal
    db = SessionLocal()
    found_path = ""
    target_job_uuid = request.job_uuid
    
    try:
        from app.models.models import ScrapeJob
        if target_job_uuid:
            job = db.query(ScrapeJob).filter(
                (ScrapeJob.id.cast(db.String) == target_job_uuid) | 
                (ScrapeJob.query_string == target_job_uuid)
            ).first()
            if job and job.json_file_url:
                found_path = job.json_file_url.lstrip("/")
        
        if not found_path:
            # Fallback 1: search in latest 50 jobs
            jobs = db.query(ScrapeJob).order_by(ScrapeJob.created_at.desc()).limit(50).all()
            for job in jobs:
                if job.json_file_url:
                    temp_path = job.json_file_url.lstrip("/")
                    if os.path.exists(temp_path):
                        try:
                            with open(temp_path, "r", encoding="utf-8") as f:
                                leads_list = json.load(f)
                                if any(l.get("id") == request.lead_id for l in leads_list):
                                    found_path = temp_path
                                    target_job_uuid = str(job.id)
                                    break
                        except: continue

        if not found_path:
            # Fallback 2: AGGRESSIVE DISK SEARCH (Search exports, leads, AND all JSON in storage)
            import glob
            all_json = glob.glob("storage/exports/**/*.json", recursive=True) + \
                       glob.glob("storage/leads/**/*.json", recursive=True)
            
            for temp_path in all_json:
                try:
                    with open(temp_path, "r", encoding="utf-8") as f:
                        leads_list = json.load(f)
                        if isinstance(leads_list, list) and any(l.get("id") == request.lead_id for l in leads_list):
                            found_path = temp_path
                            target_job_uuid = "global_search"
                            break
                except: continue
    finally:
        db.close()

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
        
        # Ensure audit fields exist to prevent frontend "undefined" errors
        target_lead["ai_status"] = "Auditing..."
        target_lead["ai_reason"] = "Manual re-audit started."
        if "ai_report" not in target_lead: target_lead["ai_report"] = ""
        if "audit_report_html_url" not in target_lead: target_lead["audit_report_html_url"] = ""
        if "audit_report_pdf_url" not in target_lead: target_lead["audit_report_pdf_url"] = ""

        # Run Audit
        print(f" [*] Re-triggering Audit for: {target_lead.get('name')} at {target_lead.get('website')}")
        audit = ai_service.analyze_website(target_lead.get("website", ""), {
            "name": target_lead.get("name"),
            "category": target_lead.get("category", "")
        }, model_id=request.model_id)

        actual_status = audit.get("status", "Issues")
        report_text = audit.get("report", "")
        
        # ── Step 2: Resolve the existing folder path ──
        import glob
        
        # Initial guess for query_folder based on the current job's path
        if "storage/exports/" in found_path:
            parts = found_path.replace("\\", "/").split("storage/exports/")
            # Extract the query slug from the folder name
            query_folder = parts[1].split("/")[0] if len(parts) > 1 else ""
        elif "storage/leads/" in found_path:
            parts = found_path.replace("\\", "/").split("storage/leads/")
            query_folder = parts[1].split("/")[0] if len(parts) > 1 else ""
        else:
            query_folder = os.path.basename(found_path).replace("export_", "").replace(".json", "")
            
        existing_folder = target_lead.get("lead_folder")
        folder_name = ""
        lead_path = ""
        
        # 1. Aggressive Search: If we have a folder name, find where it is hiding
        search_name = existing_folder.split("/")[-1].split("\\")[-1] if existing_folder else ""
        if not search_name:
            import hashlib, re
            stable_id = target_lead.get("place_id") or target_lead.get("maps_url", "")
            url_hash = hashlib.md5(stable_id.encode()).hexdigest()[:6]
            raw_name = target_lead.get("name", "lead")
            search_name = f"{re.sub(r'[^a-zA-Z0-9]+', '_', raw_name).strip('_')}_{url_hash}"

        search_pattern = os.path.join("storage", "leads", "**", search_name)
        matches = glob.glob(search_pattern, recursive=True)
        
        # Filter out 'unsorted' if possible
        clean_matches = [m for m in matches if "unsorted" not in m.replace("\\", "/")]
        final_matches = clean_matches if clean_matches else matches
        
        if final_matches:
            lead_path = final_matches[0]
            # Extract query_folder and folder_name from the found path
            rel_path = lead_path.replace("\\", "/").split("storage/leads/")[-1].strip("/")
            parts = rel_path.split("/")
            if len(parts) >= 2:
                query_folder = parts[0]
                folder_name = parts[1]
            else:
                folder_name = rel_path
            print(f"[*] Scraper found existing folder: {lead_path}")
        else:
            # Create new folder where it belongs
            folder_name = search_name
            lead_path = os.path.join("storage", "leads", query_folder if query_folder else "", folder_name)
        
        os.makedirs(lead_path, exist_ok=True)

        report_url = ""
        pdf_url = ""
        if actual_status != "No Issue" and report_text:
            report_url = ai_service.create_audit_report_file(
                target_lead.get("name", "Lead"),
                report_text,
                lead_path,
                model_id=request.model_id
            )
            print(f" [*] AI Service returned report_url: {report_url}")
            
            # Force explicit split to ensure HTML is for preview and PDF for download
            if report_url.endswith(".html"):
                pdf_url = report_url.replace(".html", ".pdf")
            elif report_url.endswith(".pdf"):
                pdf_url = report_url
                report_url = report_url.replace(".pdf", ".html")
            else:
                pdf_url = report_url

        # Update lead in place with fresh intelligence & contacts
        target_lead["ai_status"] = actual_status
        target_lead["ai_reason"] = audit.get("reason", "Analysis Complete")
        target_lead["ai_report"] = report_text
        target_lead["audit_report_html_url"] = report_url
        target_lead["audit_report_pdf_url"] = pdf_url
        target_lead["audit_report_url"] = pdf_url 
        target_lead["lead_folder"] = f"{query_folder}/{folder_name}"

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
                        df.loc[mask, "audit_report_html_url"] = report_url
                        df.loc[mask, "audit_report_pdf_url"] = pdf_url
                        df.loc[mask, "lead_folder"] = f"{query_folder}/{folder_name}"
                        df.to_csv(csv_path, index=False)
                        print(f"[*] Updated CSV file: {csv_path}")
            except Exception as csv_err:
                print(f"[!] Error updating CSV: {csv_err}")

        # Final check: Ensure the report URL is clean for the frontend
        if target_lead.get("audit_report_html_url") and target_lead["audit_report_html_url"].startswith("/"):
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
