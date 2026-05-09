import os
import random
from playwright.sync_api import sync_playwright, BrowserContext

# ─────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/537.36 Chrome/122 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122 Safari/537.36",
]

BLOCKED_RESOURCE_TYPES = {"image", "stylesheet", "font", "media", "other"}

def get_browser_context(p, worker_id: int = 0, headless: bool = True) -> BrowserContext:
    """
    Creates or retrieves a persistent browser context for a specific worker.
    This enables 'pycache' (persistent caching) for browsers, significantly
    speeding up subsequent loads of the same domains (like Google Maps).
    """
    cache_dir = os.path.join("storage", "browser_cache", f"worker_{worker_id}")
    os.makedirs(cache_dir, exist_ok=True)

    # Launch persistent context
    context = p.chromium.launch_persistent_context(
        user_data_dir=cache_dir,
        headless=headless,
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1280, "height": 800},
        locale="en-GB",
        timezone_id="Asia/Karachi",
        # Speed optimizations
        ignore_default_args=["--disable-component-update"],
        args=[
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ]
    )
    
    return context

def block_heavy_resources(page):
    """Standardized resource blocking to save bandwidth and CPU."""
    def handle_route(route):
        if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
            route.abort()
        else:
            route.continue_()
    page.route("**/*", handle_route)
