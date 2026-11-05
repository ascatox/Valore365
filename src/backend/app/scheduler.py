import logging
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler

from .config import Settings
from .constants.benchmarks import BENCHMARK_SYMBOLS
from .repository import PortfolioRepository
from .services.historical_service import HistoricalIngestionService
from .services.pac_service import PacExecutionService
from .services.pricing_service import PriceIngestionService

logger = logging.getLogger(__name__)


class PriceRefreshScheduler:
    def __init__(
        self,
        settings: Settings,
        pricing_service: PriceIngestionService,
        pac_service: PacExecutionService | None = None,
        historical_service: HistoricalIngestionService | None = None,
        repository: PortfolioRepository | None = None,
        market_data_sync=None,
    ) -> None:
        self.settings = settings
        self.pricing_service = pricing_service
        self.pac_service = pac_service
        self.historical_service = historical_service
        self.repository = repository
        # TASK-54: when set, the daily bars job runs the full market data sync
        # (quotes, bars, FX) through the same lock as the other triggers.
        self.market_data_sync = market_data_sync
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

        if self._daily_bars_enabled() and (self.historical_service is not None or self.market_data_sync is not None):
            hour = int(getattr(self.settings, 'daily_bars_scheduler_hour', 22))
            minute = int(getattr(self.settings, 'daily_bars_scheduler_minute', 30))
            self._scheduler.add_job(
                self._run_daily_bars,
                trigger='cron',
                day_of_week='mon-fri',
                hour=hour,
                minute=minute,
                id='daily_bars',
                max_instances=1,
                coalesce=True,
                # Still run if the process was busy/paused at the scheduled
                # minute (APScheduler drops misfires after 1s by default).
                misfire_grace_time=6 * 3600,
                replace_existing=True,
            )
            logger.info('Daily bars scheduler started at %02d:%02d UTC mon-fri', hour, minute)
        else:
            logger.info('Daily bars scheduler disabled')

        if self._scheduler.get_jobs():
            self._scheduler.start()

    def _daily_bars_enabled(self) -> bool:
        """DAILY_BARS_SCHEDULER_ENABLED, or PRICE_SCHEDULER_ENABLED when it is unset."""
        flag = getattr(self.settings, 'daily_bars_scheduler_enabled', None)
        if flag is None:
            return bool(self.settings.price_scheduler_enabled)
        return bool(flag)

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info('Scheduler stopped')

    def _run_refresh(self) -> None:
        try:
            # When target allocation feature is disabled, scheduler refreshes transaction assets instead.
            asset_scope = 'target' if self.settings.enable_target_allocation else 'transactions'
            # Solo il job in background salta le borse chiuse: di notte e nel
            # weekend le quotazioni non cambiano e ogni richiesta a Yahoo pesa
            # sul rate limit. I refresh manuali dalle API non passano di qui.
            market_hours_at = datetime.now(UTC) if self.settings.price_scheduler_market_hours_only else None
            response = self.pricing_service.refresh_prices(
                portfolio_id=self.settings.price_scheduler_portfolio_id,
                asset_scope=asset_scope,
                # Scheduler policy requested: use asset symbol, fallback to ISIN.
                prefer_symbol_then_isin=True,
                market_hours_at=market_hours_at,
            )
            unchanged = list(getattr(response, 'unchanged_ts_symbols', None) or [])
            logger.info(
                'Scheduled refresh completed scope=%s requested=%s refreshed=%s failed=%s unchanged_ts=%s%s',
                asset_scope,
                response.requested_assets,
                response.refreshed_assets,
                response.failed_assets,
                len(unchanged),
                f" unchanged_ts_symbols={','.join(unchanged)}" if unchanged else '',
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

    def _run_daily_bars(self) -> None:
        """Daily closes of every active asset held in any portfolio (TASK-53).

        With a market data sync service (the app wiring, TASK-54) this is
        run_sync(trigger='scheduler'): same steps, lock and run record as the
        external trigger and the startup catch-up.
        """
        if self.market_data_sync is not None:
            try:
                outcome = self.market_data_sync.run_sync('scheduler')
            except Exception as exc:  # nosec B110
                logger.exception('Scheduled market data sync failed: %s', exc)
                return
            logger.info(
                'Scheduled market data sync run_id=%s status=%s',
                getattr(outcome, 'run_id', None), getattr(outcome, 'status', None),
            )
            return
        if self.historical_service is None:
            return
        days = int(getattr(self.settings, 'daily_bars_lookback_days', 10))
        try:
            result = self.historical_service.refresh_recent_daily_bars(days=days)
        except Exception as exc:  # nosec B110
            logger.exception('Daily bars job failed: %s', exc)
            return
        logger.info(
            'Daily bars job completed lookback_days=%s requested=%s updated=%s no_new_bar=%s lagging=%s failed=%s '
            'skipped=%s lagging_symbols=%s failed_symbols=%s',
            days,
            result.requested,
            len(result.updated),
            len(result.no_new_bar),
            len(result.lagging),
            len(result.failed),
            len(result.skipped),
            ','.join(result.lagging) or '-',
            ','.join(result.failed) or '-',
        )

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
