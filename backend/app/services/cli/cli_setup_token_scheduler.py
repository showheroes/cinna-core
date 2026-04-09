"""
CLI Setup Token Cleanup Scheduler.

Periodically removes expired and used CLI setup tokens.
Follows the same pattern as file_cleanup_scheduler.py.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session

from app.core.db import engine

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def run_cleanup():
    """Run CLI setup token cleanup."""
    try:
        from app.services.cli.cli_service import CLIService

        with Session(engine) as session:
            count = CLIService.cleanup_expired_setup_tokens(session)
            logger.info(f"CLI setup token cleanup complete: {count} tokens removed")
    except Exception as e:
        logger.error(f"CLI setup token cleanup failed: {e}")


def start_scheduler():
    """Start background scheduler (call on app startup)."""
    scheduler.add_job(run_cleanup, "interval", hours=1, id="cli_setup_token_cleanup")
    scheduler.start()
    logger.info("CLI setup token cleanup scheduler started (runs every hour)")


def shutdown_scheduler():
    """Stop background scheduler (call on app shutdown)."""
    scheduler.shutdown()
    logger.info("CLI setup token cleanup scheduler stopped")
