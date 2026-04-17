from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import os
import uuid
import threading
import json
import requests

from app.services.scraper.maps_scraper import GoogleMapsScraper
from app.db.database import get_db
from app.models.models import User, ScrapeJob
from app.schemas.schemas import ScrapeJobResponse
from app.api.endpoints.users import get_current_user

router = APIRouter(tags=["Maps Scraper Data"])

# ─────────────────────────────────────────────────────────────────────────────
# In-memory job store for active scrape jobs
# Key: job_uuid, Value: { status, error, count, csv_url, json_url, job_id }
# NOTE: `data` (full results) is intentionally NOT stored here.
# Results live on disk as JSON files and are fetched from there by the frontend.
# ─────────────────────────────────────────────────────────────────────────────
_job_store: Dict[str, Dict[str, Any]] = {}

META_DIR = os.path.join("storage", "exports")


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
    max_results: Optional[int] = None


def _run_scrape_job(job_uuid: str, query: str, max_results: Optional[int], user_id: int):
    """
    Runs the full scrape pipeline in a daemon thread with incremental updates.
    """
    from app.db.database import SessionLocal

    _job_store[job_uuid]["status"] = "running"
    
    # Track results incrementally
    json_filename = f"export_{job_uuid}.json"
    json_path = os.path.join("storage", "exports", json_filename)
    os.makedirs(os.path.dirname(json_path), exist_ok=True)

    def on_data_callback(current_results):
        """Update metadata and disk file as soon as a chunk is ready."""
        _job_store[job_uuid]["count"] = len(current_results)
        # Store for real-time polling (optional, but requested for UX)
        _job_store[job_uuid]["data"] = current_results 
        
        # Persist results to disk immediately
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(current_results, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Error saving partial results for {job_uuid}: {e}")

    try:
        scraper = GoogleMapsScraper(headless=True)
        results = scraper.scrape(query, max_results=max_results, on_data=on_data_callback)

        # Export final files
        csv_filename = f"export_{job_uuid}.csv"
        csv_path = os.path.join("storage", "exports", csv_filename)
        scraper.export_csv(results, csv_path)
        
        # Ensure final JSON is written (callback might have done it already, but just in case)
        on_data_callback(results)

        csv_url = f"/storage/exports/{csv_filename}"
        json_url = f"/storage/exports/{json_filename}"

        # Persist DB record
        db = SessionLocal()
        try:
            job = ScrapeJob(
                user_id=user_id,
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

        # Build final metadata
        meta = {
            "status": "done",
            "count": len(results),
            "csv_url": csv_url,
            "json_url": json_url,
            "job_id": db_job_id,
            "error": None,
        }

        _job_store[job_uuid] = meta
        _save_meta(job_uuid, meta)

        print(f"[*] Scrape job {job_uuid} completed. Found {len(results)} results.")

        # Trigger n8n
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


@router.post("/api/scrape")
def start_scrape(
    request: ScrapeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Starts a Maps scrape job in the background and returns a job_id immediately.
    The client should poll GET /api/scrape/{job_id} for status.
    When status is 'done', the client fetches results from json_url directly.
    """
    query = f"{request.category} in {request.location}"
    print(f"[*] Queuing scrape job: {query}")

    job_uuid = str(uuid.uuid4())
    _job_store[job_uuid] = {"status": "queued", "count": 0, "error": None}

    thread = threading.Thread(
        target=_run_scrape_job,
        args=(job_uuid, query, request.max_results, current_user.id),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_uuid, "status": "queued", "query": query}


@router.get("/api/scrape/{job_id}")
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
        # Fallback: try loading persisted metadata from disk
        job = _load_meta(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found. It may have expired or never existed.")
    return job


@router.get("/api/scrapes")
def get_user_scrape_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
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


@router.delete("/api/scrape/{job_id}")
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
