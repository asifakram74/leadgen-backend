from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os
import uuid
from app.services.builder.ai_service import AISiteService
from app.api.endpoints.users import get_current_user
from app.models.models import User

router = APIRouter()

class BuildRequest(BaseModel):
    name: str
    place_id: Optional[str] = None
    maps_url: Optional[str] = None
    job_uuid: Optional[str] = None
    category: str
    address: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    rating: Optional[str] = "0"
    reviews: Optional[str] = "0"
    website: Optional[str] = ""
    ai_report: Optional[str] = ""
    ai_status: Optional[str] = ""
    ai_reason: Optional[str] = ""
    audit_report_url: Optional[str] = ""
    lead_folder: Optional[str] = ""
    user_prompt: Optional[str] = ""  # Custom prompt from the user modal
    model_id: Optional[str] = "gemini-2.5-flash-preview-05-20"  # Default model


@router.post("/builder/generate")
async def generate_site(
    request: BuildRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Generates a premium site using AI and deploys it to a local folder.
    Returns the URL where the site can be accessed.
    """
    ai_service = AISiteService()

    # ── Step 1: Generate HTML ──
    try:
        html_content = ai_service.generate_landing_page(
            request.model_dump(),
            user_prompt=request.user_prompt or "",
            model_id=request.model_id or "gemini-2.5-flash-preview-05-20"
        )
        
        # BULLETPROOF CHECK: Disallow success if content is just an error message
        if not html_content or "Gemini Error:" in html_content or "DeepSeek Error:" in html_content:
            error_msg = html_content if html_content else "AI returned empty content"
            raise Exception(error_msg)

    except Exception as e:
        error_msg = str(e)
        status_code = 500
        # Detect Quota / Rate limits for 429
        if "quota" in error_msg.lower() or "rate limit" in error_msg.lower() or "429" in error_msg or "limit" in error_msg.lower():
            status_code = 429
        
        # Friendly suggestion for 500 errors
        detail = error_msg
        if status_code == 500:
            detail = f"Intelligence Glitch: {error_msg}. Please try generating again or switch models."
            
        raise HTTPException(status_code=status_code, detail=detail)

    # ── Step 2: Save generated site to disk ──
    import hashlib, re
    from app.db.database import SessionLocal
    from app.models.models import ScrapeJob
    
    db = SessionLocal()
    query_slug = "" # Start empty instead of "unsorted"
    try:
        if request.job_uuid:
            from app.models.models import ScrapeJob
            job = db.query(ScrapeJob).filter(
                (ScrapeJob.id.cast(db.String) == request.job_uuid) | 
                (ScrapeJob.query_string == request.job_uuid)
            ).first()
            if job:
                # Use the query slug from the job
                query_slug = re.sub(r'[^a-zA-Z0-9]+', '_', job.query_string).strip('_').lower()
    finally:
        db.close()
    
    # ── Fallback: Detect query_slug from lead_folder if job lookup failed ──
    if not query_slug and request.lead_folder:
        parts = request.lead_folder.replace("\\", "/").split("/")
        if len(parts) >= 2:
            query_slug = parts[0]
            print(f"[*] Detected query_slug from lead_folder: {query_slug}")

    # ── Step 2: Resolve the existing folder path ──
    folder_name = request.lead_folder or ""
    base_path = ""

    if folder_name:
        # 1. Aggressive Search: Look for this folder name ANYWHERE in storage/leads/
        import glob
        # We search for the leaf folder name to find where it might be hiding
        leaf_name = folder_name.split("/")[-1].split("\\")[-1]
        search_pattern = os.path.join("storage", "leads", "**", leaf_name)
        matches = glob.glob(search_pattern, recursive=True)
        
        # Filter out the 'unsorted' matches if possible to prefer the clean ones
        clean_matches = [m for m in matches if "unsorted" not in m.replace("\\", "/")]
        final_matches = clean_matches if clean_matches else matches
        
        if final_matches:
            base_path = final_matches[0]
            print(f"[*] Found existing lead folder at: {base_path}")
        else:
            # 2. Fallback to specific query_slug if we have one
            if query_slug:
                base_path = os.path.join("storage", "leads", query_slug, leaf_name)
            else:
                # 3. Last resort: just put it in storage/leads/leaf_name
                base_path = os.path.join("storage", "leads", leaf_name)
    else:
        # No folder name provided, generate one
        import hashlib, re
        stable_id = request.place_id or request.maps_url or str(uuid.uuid4())
        url_hash = hashlib.md5(stable_id.encode()).hexdigest()[:6]
        clean_name = re.sub(r'[^a-zA-Z0-9]+', '_', request.name).strip('_')
        folder_name = f"{clean_name}_{url_hash}"
        base_path = os.path.join("storage", "leads", query_slug if query_slug else "", folder_name)
    
    os.makedirs(base_path, exist_ok=True)
    
    # Update folder_name to be the relative path from storage/leads/ for consistency
    # This ensures the frontend gets the CLEAN path
    folder_name = base_path.replace("\\", "/").split("storage/leads/")[-1].strip("/")

    with open(os.path.join(base_path, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)

    # ── Step 3: Generate / reuse audit PDF ──
    audit_report_url = request.audit_report_url or ""

    if not audit_report_url and request.ai_report:
        # No prior audit report — generate one now
        try:
            audit_report_url = ai_service.create_audit_report_file(
                request.name,
                request.ai_report,
                base_path
            )
            print(f"[OK] Audit PDF generated: {audit_report_url}")
        except Exception as e:
            print(f"[PDF GEN ERROR] {e}")

    # ── Step 4: Build response URLs ──
    # Clean folder name for URL building
    clean_slug = folder_name.replace("/", "").replace("\\", "")
    domain_slug = f"{clean_slug}.onlinetoolpot.com"
    live_url    = f"https://{domain_slug}"
    # Return path WITH /storage/ prefix for direct browser access
    # BULLETPROOF: If folder_name already contains a path separator, don't prepend query_slug
    if "/" in folder_name.replace("\\", "/"):
        preview_url = f"/storage/leads/{folder_name}/index.html"
    else:
        preview_url = f"/storage/leads/{query_slug}/{folder_name}/index.html" if query_slug else f"/storage/leads/{folder_name}/index.html"
    
    print(f"[*] Generated Domain: {domain_slug}")
    print(f"[*] Preview URL: {preview_url}")

    # ── Step 5: Sync back to CSV / JSON export files ──
    try:
        # Decoupled call to avoid circular dependency crashes
        from app.api.endpoints.export import export_generated_site, ExportRequest
        sync_payload = ExportRequest(
            job_uuid=request.job_uuid or "UNSET",
            query_slug=query_slug,
            place_id=request.place_id,
            name=request.name,
            generated_site_url=preview_url,
            generated_domain=domain_slug,
            audit_report_url=audit_report_url,
            ai_report=request.ai_report or "",
            ai_status=request.ai_status or "",
            ai_reason=request.ai_reason or "",
            maps_url=request.maps_url or "",
            address=request.address or ""
        )
        export_generated_site(sync_payload)
        print(f"[OK] Global Sync complete for: {request.name}")
    except Exception as e:
        print(f"[SYNC ERROR] Failed to update lead data: {e}")

    return {
        "status": "success",
        "url": preview_url,
        "generated_site_url": preview_url,
        "generated_domain": domain_slug,
        "live_url": live_url,
        "folder": folder_name if "/" in folder_name.replace("\\", "/") else (f"{query_slug}/{folder_name}" if query_slug else folder_name),
        "audit_report_url": audit_report_url,
        "message": f"Website for {request.name} is now live!",
    }


@router.get("/builder/download-audit/{folder_name:path}")
async def download_audit_report(
    folder_name: str,
    current_user: User = Depends(get_current_user)
):
    """
    Direct download endpoint for audit PDF reports.
    Supports either the folder name or the full audit_report_url path.
    """
    from pathlib import Path
    
    # 1. Clean the input path
    clean_folder = folder_name.strip("/\\").replace("\\", "/")
    
    # Aggressively strip prefixes
    prefixes = ["storage/leads/", "storage/leads", "leads/", "leads"]
    for p in prefixes:
        if clean_folder.lower().startswith(p):
            clean_folder = clean_folder[len(p):].lstrip("/\\")
            break

    # 2. Resolve root directory reliably
    current_file = Path(__file__).resolve()
    root_dir = current_file.parents[3] # endpoints -> api -> app -> root
    storage_leads = root_dir / "storage" / "leads"
    base_path = storage_leads / clean_folder
    
    # 3. Search for available report formats
    formats = [
        ("audit_report.pdf", "application/pdf"),
        ("audit_report.txt", "text/plain"),
        ("audit_report.html", "text/html")
    ]
    
    for filename, media_type in formats:
        file_path = base_path / filename
        if file_path.exists():
            download_name = f"Audit_{clean_folder.replace('/', '_')}.{filename.split('.')[-1]}"
            return FileResponse(
                path=str(file_path),
                media_type=media_type,
                filename=download_name,
                headers={"Content-Disposition": f"attachment; filename={download_name}"}
            )

    raise HTTPException(
        status_code=404,
        detail=f"Audit report not found. Checked: {base_path}"
    )


