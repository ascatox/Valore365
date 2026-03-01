import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import Settings
from .pac_service import PacExecutionService
from .pricing_service import PriceIngestionService

logger = logging.getLogger(__name__)


class PriceRefreshScheduler:
    def __init__(
        self,
        settings: Settings,
        pricing_service: PriceIngestionService,
        pac_service: PacExecutionService | None = None,
    ) -> None:
        self.settings = settings
        self.pricing_service = pricing_service
        self.pac_service = pac_service
        self._scheduler = BackgroundScheduler(timezone='UTC')

    def start(self) -> None:
        if self.settings.price_scheduler_enabled:
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
            logger.info(
                'Price scheduler started interval=%ss portfolio_id=%s',
                interval,
                self.settings.price_scheduler_portfolio_id,
            )
        else:
            logger.info('Price scheduler disabled')

        if self.settings.pac_scheduler_enabled and self.pac_service is not None:
            self._scheduler.add_job(
                self._run_pac_processing,
                trigger='cron',
                hour=self.settings.pac_execution_hour,
                id='pac_processing',
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
            logger.info('PAC scheduler started at hour=%s UTC', self.settings.pac_execution_hour)
        else:
            logger.info('PAC scheduler disabled')

        if self._scheduler.get_jobs():
            self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info('Scheduler stopped')

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

    def _run_pac_processing(self) -> None:
        if self.pac_service is None:
            return
        try:
            result = self.pac_service.process_due_rules()
            logger.info(
                'PAC processing completed rules=%s executions=%s',
                result.get("rules_processed", 0),
                result.get("executions_generated", 0),
            )
        except Exception as exc:  # nosec B110
            logger.exception('PAC processing failed: %s', exc)
