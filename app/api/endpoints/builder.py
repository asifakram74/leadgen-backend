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
    job_uuid: Optional[str] = None
    category: str
    address: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    rating: Optional[str] = "0"
    reviews: Optional[str] = "0"
    website: Optional[str] = ""
    maps_url: Optional[str] = ""
    ai_report: Optional[str] = ""
    ai_status: Optional[str] = ""
    ai_reason: Optional[str] = ""
    audit_report_url: Optional[str] = ""
    lead_folder: Optional[str] = ""
    user_prompt: Optional[str] = ""  # Custom prompt from the user modal


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
            user_prompt=request.user_prompt or ""
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Builder failed: {str(e)}")

    # ── Step 2: Save generated site to disk ──
    # Create a stable folder name using the same logic as the scraper
    import hashlib, re
    
    # Priority 1: Use the explicit lead_folder if provided by the frontend
    folder_name = request.lead_folder or ""
    
    # Priority 2: reuse folder from audit_report_url if it exists
    if not folder_name and request.audit_report_url and "leads/" in request.audit_report_url:
        parts = request.audit_report_url.split("/")
        if "leads" in parts:
            idx = parts.index("leads")
            if len(parts) > idx + 1:
                folder_name = parts[idx + 1]

    # Fallback: recalculate hash (logic matches scraper exactly: prioritizes place_id)
    if not folder_name:
        stable_id = request.place_id or request.maps_url or str(uuid.uuid4())
        url_hash = hashlib.md5(stable_id.encode()).hexdigest()[:8]
        raw_name = request.name.lower()
        clean_name = re.sub(r'[^a-z0-9]+', '-', raw_name).strip('-')
        folder_name = f"{clean_name}-{url_hash}"

    base_path = os.path.join("storage", "leads", folder_name)
    os.makedirs(base_path, exist_ok=True)

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
    domain_slug = f"{folder_name}.onlinetoolpot.com"
    live_url    = f"https://{domain_slug}"
    # Return path WITHOUT /storage/ prefix — frontend adds the base
    preview_url = f"leads/{folder_name}/index.html"
    
    print(f"[*] Generated Domain: {domain_slug}")
    print(f"[*] Preview URL: {preview_url}")

    # ── Step 5: Sync back to CSV / JSON export files ──
    if request.job_uuid:
        try:
            # Decoupled call to avoid circular dependency crashes
            from app.api.endpoints.export import export_generated_site, ExportRequest
            sync_payload = ExportRequest(
                job_uuid=request.job_uuid,
                place_id=request.place_id,
                name=request.name,
                generated_site_url=preview_url,
                generated_domain=domain_slug,
                audit_report_url=audit_report_url,
                ai_report=request.ai_report or "",
                ai_status=request.ai_status or "",
                ai_reason=request.ai_reason or "",
                maps_url=request.maps_url or ""
            )
            export_generated_site(sync_payload)
            print(f"[OK] Global Sync complete for: {request.name}")
        except Exception as e:
            print(f"[SYNC ERROR] Failed to update lead data: {e}")

    else:
        print(f"[!] Warning: Missing job_uuid. Lead data update skipped.")

    return {
        "status": "success",
        "url": preview_url,
        "generated_site_url": preview_url,
        "generated_domain": domain_slug,
        "live_url": live_url,
        "folder": folder_name,
        "audit_report_url": audit_report_url,
        "message": f"Website for {request.name} is now live!",
    }


@router.get("/builder/download-audit/{folder_name}")
async def download_audit_report(
    folder_name: str,
    current_user: User = Depends(get_current_user)
):
    """
    Direct download endpoint for audit PDF reports.
    Supports either the folder name or the full audit_report_url path.
    """
    # Clean the input to extract the folder name
    clean_folder = folder_name
    if "/" in folder_name:
        parts = folder_name.split("/")
        if "leads" in parts:
            idx = parts.index("leads")
            if len(parts) > idx + 1:
                clean_folder = parts[idx + 1]

    # Use an absolute path to be 100% sure on Windows
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    base_path = os.path.join(root_dir, "storage", "leads", clean_folder)
    
    # DIAGNOSTIC: This will show up in your terminal
    print(f" [*] Download Request: {clean_folder}")
    print(f" [*] Full Path Check: {os.path.abspath(base_path)}")
    print(f" [*] Folder Exists: {os.path.exists(base_path)}")

    # Priority Order: PDF (Professional) > TXT (Simple) > HTML (Web fallback)
    # We look for each format and serve the first one we find
    for filename in ["audit_report.pdf", "audit_report.txt", "audit_report.html"]:
        file_path = os.path.join(base_path, filename)
        if os.path.exists(file_path):
            # Map extensions to correct media types
            if filename.endswith(".pdf"):
                media_type = "application/pdf"
            elif filename.endswith(".txt"):
                media_type = "text/plain"
            else:
                media_type = "text/html"

            # Set a clean download name
            ext = filename.split(".")[-1]
            download_name = f"Audit_{clean_folder}.{ext}"
            
            return FileResponse(
                path=file_path,
                media_type=media_type,
                filename=download_name,
                headers={"Content-Disposition": f"attachment; filename={download_name}"}
            )

    raise HTTPException(
        status_code=404,
        detail=f"Audit report not found. Please re-run the audit to generate a new PDF."
    )


