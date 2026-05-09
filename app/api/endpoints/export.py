from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import json
import csv
import glob

router = APIRouter()

class ExportRequest(BaseModel):
    job_uuid: str
    place_id: Optional[str] = None
    name: Optional[str] = None
    generated_site_url: str = ""
    generated_domain: str = ""
    audit_report_url: str = ""
    ai_report: str = ""
    ai_status: str = ""
    ai_reason: str = ""
    maps_url: Optional[str] = ""
    query_slug: Optional[str] = None
    address: Optional[str] = ""


@router.post("/export/generated-site")
def export_generated_site(request: ExportRequest):
    """
    Bulletproof Sync Engine: Updates lead records in both JSON and CSV files.
    Uses Maps URL and IDs as primary keys to ensure zero-fail synchronization.
    """
    print(f"[*] AUTO-SYNC START: Lead='{request.name}' | URL='{request.maps_url}'")
    
    json_matches = []
    csv_matches = []

    # 1. Targeted Folder Search (High Performance)
    if request.query_slug:
        slug_dir = os.path.join("storage", "exports", request.query_slug)
        json_matches.append(os.path.join(slug_dir, f"{request.query_slug}.json"))
        csv_matches.append(os.path.join(slug_dir, f"{request.query_slug}.csv"))

    # 2. Global Fallback (Ensures we never miss a lead)
    if not any(os.path.exists(f) for f in json_matches):
        json_matches += glob.glob("storage/exports/**/*.json", recursive=True)
    if not any(os.path.exists(f) for f in csv_matches):
        csv_matches += glob.glob("storage/exports/**/*.csv", recursive=True)

    # Clean and deduplicate paths
    json_matches = list(set([os.path.abspath(f) for f in json_matches if os.path.exists(f)]))
    csv_matches = list(set([os.path.abspath(f) for f in csv_matches if os.path.exists(f)]))

    json_updated = False
    csv_updated = False

    # ───────────────────────── JSON SYNC ─────────────────────────
    # Also look for .meta.json files in the root of exports
    root_exports = os.path.join("storage", "exports")
    if os.path.exists(root_exports):
        for f in os.listdir(root_exports):
            if f.endswith(".meta.json"):
                json_matches.append(os.path.join(root_exports, f))

    for json_path in json_matches:
        try:
            if not os.path.exists(json_path): continue
            with open(json_path, "r", encoding="utf-8") as f:
                outer_data = json.load(f)
            
            # Handle both list and {"data": [...]} structures
            is_wrapped = isinstance(outer_data, dict) and "data" in outer_data
            data = outer_data["data"] if is_wrapped else outer_data
            
            if not isinstance(data, list): continue

            changed = False
            for record in data:
                # Normalize URLs for comparison (remove trailing slashes, etc.)
                rec_url = str(record.get("maps_url", "")).rstrip("/")
                req_url = str(request.maps_url or "").rstrip("/")
                
                # PRIMARY KEYS: Maps URL or Place ID
                match_url = req_url and rec_url == req_url
                match_place = request.place_id and (record.get("place_id") == request.place_id or record.get("id") == request.place_id)
                # SECONDARY KEY: Fuzzy Name (if URL/ID missing)
                match_name = not (match_url or match_place) and request.name and (request.name.lower() in record.get("name", "").lower() or record.get("name", "").lower() in request.name.lower())

                if match_url or match_place or match_name:
                    record["generated_site_url"] = request.generated_site_url
                    record["generated_domain"] = request.generated_domain
                    if request.audit_report_url: record["audit_report_url"] = request.audit_report_url
                    if request.ai_status: record["ai_status"] = request.ai_status
                    if request.ai_reason: record["ai_reason"] = request.ai_reason
                    if request.ai_report: record["ai_report"] = request.ai_report
                    changed = True
                    json_updated = True
                    print(f" [OK] JSON Record Found & Updated in {os.path.basename(json_path)}: {record.get('name')}")

            if changed:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(outer_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f" [!] JSON Sync Error in {json_path}: {e}")

    # ───────────────────────── CSV SYNC ─────────────────────────
    for csv_path in csv_matches:
        try:
            rows = []
            changed = False
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames) if reader.fieldnames else []
                for fld in ["generated_site_url", "generated_domain", "audit_report_url", "ai_status", "ai_reason", "ai_report"]:
                    if fld not in fieldnames: fieldnames.append(fld)

                for row in reader:
                    rec_url = str(row.get("maps_url", "")).rstrip("/")
                    req_url = str(request.maps_url or "").rstrip("/")

                    match_url = req_url and rec_url == req_url
                    match_place = request.place_id and (row.get("place_id") == request.place_id or row.get("id") == request.place_id)
                    match_name = not (match_url or match_place) and request.name and (request.name.lower() in row.get("name", "").lower() or row.get("name", "").lower() in request.name.lower())

                    if match_url or match_place or match_name:
                        row["generated_site_url"] = request.generated_site_url
                        row["generated_domain"] = request.generated_domain
                        if request.audit_report_url: row["audit_report_url"] = request.audit_report_url
                        if request.ai_status: row["ai_status"] = request.ai_status
                        if request.ai_reason: row["ai_reason"] = request.ai_reason
                        if request.ai_report: row["ai_report"] = request.ai_report
                        changed = True
                        csv_updated = True
                    rows.append(row)

            if changed:
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows(rows)
                print(f" [OK] CSV Record Found & Updated: {os.path.basename(csv_path)}")
        except Exception as e:
            print(f" [!] CSV Sync Error in {csv_path}: {e}")

    return {"status": "success", "json_updated": json_updated, "csv_updated": csv_updated}
