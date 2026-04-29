import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import Settings
from .repository import PortfolioRepository
from .services.historical_service import HistoricalIngestionService
from .services.pac_service import PacExecutionService
from .services.pricing_service import PriceIngestionService

logger = logging.getLogger(__name__)


BENCHMARK_SYMBOLS = ["SPY"]


class PriceRefreshScheduler:
    def __init__(
        self,
        settings: Settings,
        pricing_service: PriceIngestionService,
        pac_service: PacExecutionService | None = None,
        historical_service: HistoricalIngestionService | None = None,
        repository: PortfolioRepository | None = None,
    ) -> None:
        self.settings = settings
        self.pricing_service = pricing_service
        self.pac_service = pac_service
        self.historical_service = historical_service
        self.repository = repository
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

        if self.settings.price_scheduler_enabled and self.historical_service is not None and self.repository is not None:
            self._scheduler.add_job(
                self._run_benchmark_backfill,
                trigger='cron',
                hour=6,
                minute=30,
                id='benchmark_backfill',
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
            logger.info('Benchmark backfill scheduler started at 06:30 UTC')

        if self._scheduler.get_jobs():
            self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info('Scheduler stopped')

    def _run_refresh(self) -> None:
        try:
            # When target allocation feature is disabled, scheduler refreshes transaction assets instead.
            asset_scope = 'target' if self.settings.enable_target_allocation else 'transactions'
            response = self.pricing_service.refresh_prices(
                portfolio_id=self.settings.price_scheduler_portfolio_id,
                asset_scope=asset_scope,
                # Scheduler policy requested: use asset symbol, fallback to ISIN.
                prefer_symbol_then_isin=True,
            )
            logger.info(
                'Scheduled refresh completed scope=%s requested=%s refreshed=%s failed=%s',
                asset_scope,
                response.requested_assets,
                response.refreshed_assets,
                response.failed_assets,
            )
        except Exception as exc:  # nosec B110
            logger.exception('Scheduled refresh failed: %s', exc)

    def _run_benchmark_backfill(self) -> None:
        if self.historical_service is None or self.repository is None:
            return
        portfolio_id = self.settings.price_scheduler_portfolio_id
        for symbol in BENCHMARK_SYMBOLS:
            try:
                asset = self.repository.get_asset_by_symbol(symbol)
                if not asset:
                    continue
                self.historical_service.backfill_single_asset(
                    asset_id=asset["id"],
                    portfolio_id=portfolio_id,
                    days=30,
                )
                logger.info('Benchmark backfill completed symbol=%s', symbol)
            except Exception as exc:
                logger.exception('Benchmark backfill failed symbol=%s: %s', symbol, exc)

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
