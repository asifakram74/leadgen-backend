from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict
import os
import uuid

from app.services.builder.ai_service import AISiteService
from app.api.endpoints.users import get_current_user
from app.models.models import User

router = APIRouter()

class BuildRequest(BaseModel):
    name: str
    category: str
    address: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    rating: Optional[str] = "0"
    reviews: Optional[str] = "0"

@router.post("/api/builder/generate")
async def generate_site(
    request: BuildRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Generates a premium site using AI and 'deploys' it to a local folder.
    Returns the URL where the site can be accessed.
    """
    ai_service = AISiteService()
    
    # 1. Generate the HTML code
    try:
        html_content = ai_service.generate_landing_page(request.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Builder failed: {str(e)}")

    # 2. Save the file to the webroot
    # On aaPanel, you should point a domain to this directory
    # We create a unique folder for each generation
    site_id = str(uuid.uuid4())[:8]
    safe_name = request.name.lower().replace(" ", "-").replace("/", "-")
    folder_name = f"{safe_name}-{site_id}"
    
    # Path where aaPanel hosts static sites
    # Defaulting to storage/sites for local testing, 
    # Change this to /www/wwwroot/generated_sites/ on your server
    base_path = os.path.join("storage", "sites", folder_name)
    os.makedirs(base_path, exist_ok=True)
    
    with open(os.path.join(base_path, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)

    # 3. Construct the URL
    # Replace 'onlinetoolpot.com' with your actual domain
    generated_url = f"https://{folder_name}.onlinetoolpot.com" 
    
    # For now, return a preview link that works locally
    preview_url = f"/storage/sites/{folder_name}/index.html"

    return {
        "status": "success",
        "url": preview_url,
        "live_url": generated_url,
        "message": f"Website for {request.name} is now live!"
    }
