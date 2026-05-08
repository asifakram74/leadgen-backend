from playwright.sync_api import sync_playwright
from app.services.scraper.website_scraper import extract_website_details
from app.services.workers.worker_queues import website_executor
from app.db.database import get_db
from app.models.models import ScrapeJob


def queue_website_scrape(
    job_id,
    place_id,
    website_url
):
    website_executor.submit(
        process_website_scrape,
        job_id,
        place_id,
        website_url
    )


def process_website_scrape(
    job_id,
    place_id,
    website_url
):
    try:

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True
            )

            context = browser.new_context()

            page = context.new_page()

            web_data = extract_website_details(
                page,
                website_url
            )

            browser.close()

        update_place_website_data(
            job_id,
            place_id,
            web_data
        )

        from app.services.workers.ai_worker import queue_ai_audit

        queue_ai_audit(
            job_id,
            place_id
        )

    except Exception as e:
        print("Website worker error:", e)


def update_place_website_data(
    job_id,
    place_id,
    web_data
):
    db = next(get_db())

    job = db.query(ScrapeJob).filter(
        ScrapeJob.id == job_id
    ).first()

    if not job:
        return

    results = job.results

    for record in results:

        if record["place_id"] == place_id:

            record["emails"] = web_data["emails"]
            record["social_links"] = web_data["social_links"]
            record["whatsapp"] = web_data["whatsapp"]

    job.results = results

    db.commit()