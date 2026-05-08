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


@router.post("/export/generated-site")
def export_generated_site(request: ExportRequest):
    # Log incoming request for debugging
    print(f"[*] SYNC ATTEMPT: Name='{request.name}' | Job='{request.job_uuid}' | URL='{request.maps_url}'")
    
    json_matches = []
    csv_matches = []
    
    # 1. Search by Job UUID (Fastest)
    if request.job_uuid and len(request.job_uuid) > 10:
        json_matches = glob.glob(f"storage/exports/*{request.job_uuid}*.json")
        csv_matches = glob.glob(f"storage/exports/*{request.job_uuid}*.csv")

    # 2. Global Fallback (If job_uuid is wrong or missing)
    if not json_matches:
        json_matches = glob.glob("storage/exports/*.json")
    if not csv_matches:
        csv_matches = glob.glob("storage/exports/*.csv")

    json_updated = False
    csv_updated = False

    # ───────────────────────── JSON ─────────────────────────
    for json_path in json_matches:
        try:
            changed = False
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list): continue

            for record in data:
                # TRIPLE-MATCH: ID, URL, or Name (Final Fallback)
                match_id = request.place_id and record.get("id") == request.place_id
                match_url = request.maps_url and record.get("maps_url") == request.maps_url
                match_name = request.name and record.get("name") == request.name
                
                if match_id or match_url or match_name:
                    record["generated_site_url"] = request.generated_site_url
                    record["generated_domain"] = request.generated_domain
                    if request.audit_report_url: record["audit_report_url"] = request.audit_report_url
                    if request.ai_status: record["ai_status"] = request.ai_status
                    if request.ai_reason: record["ai_reason"] = request.ai_reason
                    if request.ai_report: record["ai_report"] = request.ai_report
                    changed = True
                    json_updated = True
                    print(f" [OK] JSON Updated: {record.get('name')} in {os.path.basename(json_path)}")

            if changed:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except: pass

    # ───────────────────────── CSV ─────────────────────────
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
                    match_id = request.place_id and row.get("id") == request.place_id
                    match_url = request.maps_url and row.get("maps_url") == request.maps_url
                    match_name = request.name and row.get("name") == request.name
                    
                    if match_id or match_url or match_name:
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
                print(f" [OK] CSV Updated: {os.path.basename(csv_path)}")
        except: pass

    return {"status": "success", "json_updated": json_updated, "csv_updated": csv_updated}



