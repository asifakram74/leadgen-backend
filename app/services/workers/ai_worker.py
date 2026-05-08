from app.services.workers.worker_queues import ai_executor
from app.services.builder.ai_service import AISiteService
from app.db.database import get_db
from app.models.models import ScrapeJob


def queue_ai_audit(
    job_id,
    place_id
):
    ai_executor.submit(
        process_ai_audit,
        job_id,
        place_id
    )


def process_ai_audit(
    job_id,
    place_id
):
    try:

        db = next(get_db())

        job = db.query(ScrapeJob).filter(
            ScrapeJob.id == job_id
        ).first()

        if not job:
            return

        results = job.results

        for record in results:

            if record["place_id"] == place_id:

                if not record.get("website"):
                    return

                ai_service = AISiteService()

                audit = ai_service.analyze_website(
                    record["website"],
                    {
                        "name": record.get("name"),
                        "category": record.get("category")
                    }
                )

                record["ai_status"] = audit.get(
                    "status",
                    "Issues"
                )

                record["ai_reason"] = audit.get(
                    "reason",
                    ""
                )

        job.results = results

        db.commit()

    except Exception as e:
        print("AI worker error:", e)