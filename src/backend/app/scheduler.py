import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import Settings
from .pricing_service import PriceIngestionService

logger = logging.getLogger(__name__)


class PriceRefreshScheduler:
    def __init__(self, settings: Settings, pricing_service: PriceIngestionService) -> None:
        self.settings = settings
        self.pricing_service = pricing_service
        self._scheduler = BackgroundScheduler(timezone='UTC')

    def start(self) -> None:
        if not self.settings.price_scheduler_enabled:
            logger.info('Price scheduler disabled')
            return

        interval = max(5, int(self.settings.price_scheduler_interval_seconds))
        self._scheduler.add_job(
            self._run_refresh,
            trigger='interval',
            seconds=interval,
            id='price_refresh',
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            'Price scheduler started interval=%ss portfolio_id=%s',
            interval,
            self.settings.price_scheduler_portfolio_id,
        )

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info('Price scheduler stopped')

    def _run_refresh(self) -> None:
        try:
            response = self.pricing_service.refresh_prices(portfolio_id=self.settings.price_scheduler_portfolio_id)
            logger.info(
                'Scheduled refresh completed requested=%s refreshed=%s failed=%s',
                response.requested_assets,
                response.refreshed_assets,
                response.failed_assets,
            )
        except Exception as exc:  # nosec B110
            logger.exception('Scheduled refresh failed: %s', exc)
