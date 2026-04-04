from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta
from math import isfinite, sqrt

from ..models import (
    DrawdownPoint,
    DrawdownResponse,
    GainTimeseriesPoint,
    HallOfFameResponse,
    MonthlyReturnCell,
    MonthlyReturnsResponse,
    MWRResult,
    MWRTimeseriesPoint,
    PerformanceSummary,
    RankedPeriod,
    RollingWindowPoint,
    RollingWindowsResponse,
    TWRResult,
    TWRTimeseriesPoint,
    YearlyReturnItem,
)
from ..repository import PortfolioRepository

try:
    from scipy.optimize import brentq as scipy_brentq  # type: ignore
    from scipy.optimize import newton as scipy_newton  # type: ignore
except Exception:  # pragma: no cover - optional dependency in runtime
    scipy_brentq = None
    scipy_newton = None

logger = logging.getLogger(__name__)


_PERIOD_TO_DAYS: dict[str, int] = {
    '1m': 30,
    '3m': 90,
    '6m': 180,
    '1y': 365,
    '3y': 1095,
}


class PerformanceService:
    def __init__(self, repo: PortfolioRepository) -> None:
        self.repo = repo

    def _get_cashflows_with_fallback(
        self,
        portfolio_id: int,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> tuple[list, bool]:
        """Return (cashflows, used_trade_fallback).

        If no deposit/withdrawal/dividend/fee/interest exist in the period,
        falls back to buy/sell as implicit investor cashflows.
        """
        cashflows = self.repo.get_external_cashflows(
            portfolio_id, user_id, start_date=start_date, end_date=end_date,
        )
        if cashflows:
            return cashflows, False

        trade_cashflows = self.repo.get_external_cashflows(
            portfolio_id, user_id, start_date=start_date, end_date=end_date, include_trades=True,
        )
        buy_sell_flows = [cf for cf in trade_cashflows if cf.side in ("buy", "sell")]
        if buy_sell_flows:
            return trade_cashflows, True

        return [], False

    def calculate_twr(
        self,
        portfolio_id: int,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> TWRResult:
        start, end = self._resolve_date_range(portfolio_id, user_id, start_date, end_date)
        period_days = max((end - start).days, 1)

        cashflows, use_trade_flows = self._get_cashflows_with_fallback(portfolio_id, user_id, start, end)
        cashflow_by_day: dict[date, float] = {}
        for cf in cashflows:
            day = date.fromisoformat(cf.date)
            if use_trade_flows and cf.side in ("buy", "sell"):
                # For TWR, buy/sell don't change portfolio value (internal movements).
                # Register the date to break sub-periods, but with zero cashflow amount.
                cashflow_by_day.setdefault(day, 0.0)
            else:
                cashflow_by_day[day] = cashflow_by_day.get(day, 0.0) + float(cf.amount)

        start_value = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, start)

        if start_value <= 0:
            first_positive_cf_day = next(
                (d for d in sorted(cashflow_by_day.keys()) if start <= d <= end and cashflow_by_day.get(d, 0.0) > 0),
                None,
            )
            if first_positive_cf_day is not None:
                start = first_positive_cf_day
                period_days = max((end - start).days, 1)
                start_value = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, start)

        if start_value <= 0:
            return TWRResult(
                twr_pct=0.0,
                twr_annualized_pct=0.0 if period_days >= 365 else None,
                period_days=period_days,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            )

        event_days = sorted(d for d in cashflow_by_day.keys() if start < d <= end)
        linked = 1.0
        subperiod_start_value = start_value

        for day in event_days + [end]:
            end_value = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, day)
            cf_amount = cashflow_by_day.get(day, 0.0) if day in event_days else 0.0
            if subperiod_start_value > 0:
                r_i = (end_value - subperiod_start_value - cf_amount) / subperiod_start_value
                linked *= 1.0 + r_i
            subperiod_start_value = end_value

        twr = linked - 1.0
        twr_ann: float | None = None
        if period_days >= 365 and (1.0 + twr) > 0:
            twr_ann = ((1.0 + twr) ** (365.0 / period_days) - 1.0) * 100.0

        return TWRResult(
            twr_pct=round(twr * 100.0, 4),
            twr_annualized_pct=round(twr_ann, 4) if twr_ann is not None else None,
            period_days=period_days,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )

    def calculate_mwr(
        self,
        portfolio_id: int,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> MWRResult:
        start, end = self._resolve_date_range(portfolio_id, user_id, start_date, end_date)
        period_days = max((end - start).days, 1)

        cashflows, use_trade_flows = self._get_cashflows_with_fallback(portfolio_id, user_id, start, end)
        start_value = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, start)
        end_value = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, end)

        # When using buy/sell as cashflows, adjust portfolio values to
        # exclude the cash impact of trades (avoid double-counting).
        if use_trade_flows:
            all_before = self.repo.get_external_cashflows(
                portfolio_id, user_id, end_date=start, include_trades=True,
            )
            cash_before = sum(cf.amount for cf in all_before if cf.side in ("buy", "sell"))
            start_value = start_value - cash_before

            buy_sell_in_period = [cf for cf in cashflows if cf.side in ("buy", "sell")]
            cash_in_period = sum(cf.amount for cf in buy_sell_in_period)
            end_value = end_value - cash_before - cash_in_period

        if start_value == 0 and not cashflows and end_value == 0:
            return MWRResult(
                mwr_pct=0.0,
                period_days=period_days,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                converged=True,
            )

        flows: list[tuple[float, float]] = []
        # Investor perspective: initial portfolio value is an outflow.
        if start_value != 0:
            flows.append((0.0, -float(start_value)))

        for cf in cashflows:
            day = date.fromisoformat(cf.date)
            days = float((day - start).days)
            # Repo amount sign is portfolio perspective; invert for investor perspective.
            flows.append((days, -float(cf.amount)))

        flows.append((float((end - start).days), float(end_value)))

        if not flows:
            return MWRResult(
                mwr_pct=0.0,
                period_days=period_days,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                converged=True,
            )

        has_pos = any(cf > 0 for _, cf in flows)
        has_neg = any(cf < 0 for _, cf in flows)
        if not (has_pos and has_neg):
            return MWRResult(
                mwr_pct=None,
                period_days=period_days,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                converged=False,
            )

        rate = self._solve_irr(flows)
        if rate is None or not isfinite(rate):
            return MWRResult(
                mwr_pct=None,
                period_days=period_days,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                converged=False,
            )

        return MWRResult(
            mwr_pct=round(rate * 100.0, 4),
            period_days=period_days,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            converged=True,
        )

    def get_performance_summary(
        self,
        portfolio_id: int,
        user_id: str,
        period: str = '1y',
    ) -> PerformanceSummary:
        start, end = self._resolve_period_range(portfolio_id, user_id, period)

        twr = self.calculate_twr(portfolio_id, user_id, start, end)
        mwr = self.calculate_mwr(portfolio_id, user_id, start, end)
        cashflows, use_trade_flows = self._get_cashflows_with_fallback(portfolio_id, user_id, start, end)

        if use_trade_flows:
            # Treat buy cost as "deposits" and sell proceeds as "withdrawals"
            total_deposits = sum(cf.amount for cf in cashflows if cf.side == 'buy')
            total_withdrawals = sum(-cf.amount for cf in cashflows if cf.side == 'sell')
        else:
            total_deposits = sum(cf.amount for cf in cashflows if cf.side == 'deposit')
            total_withdrawals = sum(-cf.amount for cf in cashflows if cf.side == 'withdrawal')
        net_invested = total_deposits - total_withdrawals
        current_value = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, end)

        period_days = max((end - start).days, 1)
        return PerformanceSummary(
            period=period,
            period_label=self._period_label(period),
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            period_days=period_days,
            twr=twr,
            mwr=mwr,
            total_deposits=round(total_deposits, 2),
            total_withdrawals=round(total_withdrawals, 2),
            net_invested=round(net_invested, 2),
            current_value=round(current_value, 2),
            absolute_gain=round(current_value - net_invested, 2),
        )

    def get_twr_timeseries(
        self,
        portfolio_id: int,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[TWRTimeseriesPoint]:
        start, end = self._resolve_date_range(portfolio_id, user_id, start_date, end_date)
        cashflows, use_trade_flows = self._get_cashflows_with_fallback(portfolio_id, user_id, start, end)

        cf_by_day: dict[date, float] = {}
        for cf in cashflows:
            day = date.fromisoformat(cf.date)
            if use_trade_flows and cf.side in ("buy", "sell"):
                # Buy/sell are internal movements — zero cashflow for TWR formula
                cf_by_day.setdefault(day, 0.0)
            else:
                cf_by_day[day] = cf_by_day.get(day, 0.0) + float(cf.amount)

        values: dict[date, float] = {}
        cursor = start
        while cursor <= end:
            values[cursor] = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, cursor)
            cursor += timedelta(days=1)

        points: list[TWRTimeseriesPoint] = []
        cumulative = 1.0
        points.append(
            TWRTimeseriesPoint(
                date=start.isoformat(),
                cumulative_twr_pct=0.0,
                portfolio_value=round(values.get(start, 0.0), 2),
            )
        )

        cursor = start + timedelta(days=1)
        while cursor <= end:
            prev_day = cursor - timedelta(days=1)
            prev_value = float(values.get(prev_day, 0.0))
            curr_value = float(values.get(cursor, 0.0))
            cf_amount = float(cf_by_day.get(cursor, 0.0))

            daily_return = (curr_value - prev_value - cf_amount) / prev_value if prev_value > 0 else 0.0
            cumulative *= 1.0 + daily_return

            points.append(
                TWRTimeseriesPoint(
                    date=cursor.isoformat(),
                    cumulative_twr_pct=round((cumulative - 1.0) * 100.0, 4),
                    portfolio_value=round(curr_value, 2),
                )
            )
            cursor += timedelta(days=1)

        return points

    def get_gain_timeseries(
        self,
        portfolio_id: int,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[GainTimeseriesPoint]:
        start, end = self._resolve_date_range(portfolio_id, user_id, start_date, end_date)
        cashflows, use_trade_flows = self._get_cashflows_with_fallback(portfolio_id, user_id, start, end)

        # For net_invested, use deposit/withdrawal (or buy/sell if fallback)
        invest_sides = ('buy', 'sell') if use_trade_flows else ('deposit', 'withdrawal')
        cf_by_day: dict[date, float] = {}
        for cf in cashflows:
            day = date.fromisoformat(cf.date)
            if cf.side in invest_sides:
                cf_by_day[day] = cf_by_day.get(day, 0.0) + float(cf.amount)

        points: list[GainTimeseriesPoint] = []
        cumulative_invested = 0.0
        cursor = start
        while cursor <= end:
            cumulative_invested += cf_by_day.get(cursor, 0.0)
            pv = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, cursor)
            gain = pv - cumulative_invested
            points.append(
                GainTimeseriesPoint(
                    date=cursor.isoformat(),
                    portfolio_value=round(pv, 2),
                    net_invested=round(cumulative_invested, 2),
                    absolute_gain=round(gain, 2),
                )
            )
            cursor += timedelta(days=1)

        return points

    def get_mwr_timeseries(
        self,
        portfolio_id: int,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[MWRTimeseriesPoint]:
        start, end = self._resolve_date_range(portfolio_id, user_id, start_date, end_date)
        period_days = (end - start).days

        # Weekly sampling for periods > 365 days to limit IRR solves
        if period_days > 365:
            step = 7
        else:
            step = 1

        # Pre-fetch all cashflows once (with buy/sell fallback)
        cashflows, use_trade_flows = self._get_cashflows_with_fallback(portfolio_id, user_id, start, end)
        start_value = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, start)

        # When using buy/sell as cashflows, adjust start_value to asset-only
        if use_trade_flows:
            all_before = self.repo.get_external_cashflows(
                portfolio_id, user_id, end_date=start, include_trades=True,
            )
            cash_before = sum(cf.amount for cf in all_before if cf.side in ("buy", "sell"))
            start_value = start_value - cash_before

        # Pre-compute cashflow list with day offsets
        cf_entries: list[tuple[date, float, float]] = []  # (day, days_from_start, amount_investor)
        for cf in cashflows:
            day = date.fromisoformat(cf.date)
            days_offset = float((day - start).days)
            cf_entries.append((day, days_offset, -float(cf.amount)))

        # Pre-compute buy/sell cash by day for value adjustments
        trade_cash_by_day: dict[date, float] = {}
        if use_trade_flows:
            for cf in cashflows:
                if cf.side in ("buy", "sell"):
                    day = date.fromisoformat(cf.date)
                    trade_cash_by_day[day] = trade_cash_by_day.get(day, 0.0) + float(cf.amount)

        points: list[MWRTimeseriesPoint] = []
        points.append(MWRTimeseriesPoint(date=start.isoformat(), cumulative_mwr_pct=0.0))

        cursor = start + timedelta(days=step)
        while cursor <= end:
            cursor_days = float((cursor - start).days)
            cursor_value = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, cursor)

            # When using trade flows, adjust cursor_value to asset-only
            if use_trade_flows:
                cash_up_to_cursor = sum(
                    amt for day, amt in trade_cash_by_day.items() if start < day <= cursor
                )
                cursor_value = cursor_value - cash_before - cash_up_to_cursor

            # Build flows for start..cursor
            flows: list[tuple[float, float]] = []
            if start_value != 0:
                flows.append((0.0, -float(start_value)))
            for day, days_offset, inv_amount in cf_entries:
                if day <= cursor and day > start:
                    flows.append((days_offset, inv_amount))
            flows.append((cursor_days, float(cursor_value)))

            mwr_pct: float | None = None
            if flows:
                has_pos = any(cf > 0 for _, cf in flows)
                has_neg = any(cf < 0 for _, cf in flows)
                if has_pos and has_neg:
                    rate = self._solve_irr(flows)
                    if rate is not None and isfinite(rate):
                        mwr_pct = round(rate * 100.0, 4)

            points.append(MWRTimeseriesPoint(date=cursor.isoformat(), cumulative_mwr_pct=mwr_pct))
            cursor += timedelta(days=step)

        # Ensure the last point is exactly 'end' if we didn't land on it
        if points[-1].date != end.isoformat():
            cursor_days = float((end - start).days)
            end_value = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, end)
            if use_trade_flows:
                total_trade_cash = sum(trade_cash_by_day.values())
                end_value = end_value - cash_before - total_trade_cash
            flows = []
            if start_value != 0:
                flows.append((0.0, -float(start_value)))
            for day, days_offset, inv_amount in cf_entries:
                if day <= end and day > start:
                    flows.append((days_offset, inv_amount))
            flows.append((cursor_days, float(end_value)))

            mwr_pct = None
            if flows:
                has_pos = any(cf > 0 for _, cf in flows)
                has_neg = any(cf < 0 for _, cf in flows)
                if has_pos and has_neg:
                    rate = self._solve_irr(flows)
                    if rate is not None and isfinite(rate):
                        mwr_pct = round(rate * 100.0, 4)

            points.append(MWRTimeseriesPoint(date=end.isoformat(), cumulative_mwr_pct=mwr_pct))

        return points

    # --- Advanced analytics ---

    _MONTH_NAMES = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu',
                    'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic']

    def _build_monthly_returns(
        self,
        portfolio_id: int,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """Single-pass computation of daily TWR series and monthly returns.

        Returns:
            (daily_series, monthly_returns) where:
            - daily_series: [{'date': date, 'cumulative_twr': float, 'portfolio_value': float}, ...]
            - monthly_returns: [{'year': int, 'month': int, 'return_pct': float}, ...]
        """
        start, end = self._resolve_date_range(portfolio_id, user_id, start_date, end_date)
        cashflows, use_trade_flows = self._get_cashflows_with_fallback(portfolio_id, user_id, start, end)

        cf_by_day: dict[date, float] = {}
        for cf in cashflows:
            day = date.fromisoformat(cf.date)
            if use_trade_flows and cf.side in ("buy", "sell"):
                cf_by_day.setdefault(day, 0.0)
            else:
                cf_by_day[day] = cf_by_day.get(day, 0.0) + float(cf.amount)

        daily_series: list[dict] = []
        cumulative = 1.0
        prev_value = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, start)
        daily_series.append({'date': start, 'cumulative_twr': cumulative, 'portfolio_value': prev_value})

        # Track month boundaries for monthly returns
        month_start_cum = cumulative
        current_month = (start.year, start.month)
        monthly_returns: list[dict] = []

        cursor = start + timedelta(days=1)
        while cursor <= end:
            curr_value = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, cursor)
            cf_amount = float(cf_by_day.get(cursor, 0.0))

            if prev_value > 0:
                daily_return = (curr_value - prev_value - cf_amount) / prev_value
            else:
                daily_return = 0.0
            cumulative *= 1.0 + daily_return

            daily_series.append({'date': cursor, 'cumulative_twr': cumulative, 'portfolio_value': curr_value})

            # Check month boundary
            cursor_month = (cursor.year, cursor.month)
            if cursor_month != current_month:
                # Close previous month
                if month_start_cum > 0:
                    month_return = (daily_series[-2]['cumulative_twr'] / month_start_cum - 1.0) * 100.0
                else:
                    month_return = 0.0
                monthly_returns.append({
                    'year': current_month[0],
                    'month': current_month[1],
                    'return_pct': round(month_return, 4),
                })
                month_start_cum = daily_series[-2]['cumulative_twr']
                current_month = cursor_month

            prev_value = curr_value
            cursor += timedelta(days=1)

        # Close final (partial) month
        if month_start_cum > 0 and daily_series:
            month_return = (daily_series[-1]['cumulative_twr'] / month_start_cum - 1.0) * 100.0
        else:
            month_return = 0.0
        monthly_returns.append({
            'year': current_month[0],
            'month': current_month[1],
            'return_pct': round(month_return, 4),
        })

        return daily_series, monthly_returns

    def get_monthly_returns(
        self,
        portfolio_id: int,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> MonthlyReturnsResponse:
        start, end = self._resolve_date_range(portfolio_id, user_id, start_date, end_date)
        _, monthly = self._build_monthly_returns(portfolio_id, user_id, start, end)

        # Compute yearly returns by chaining monthly
        yearly_acc: dict[int, float] = {}
        for m in monthly:
            yearly_acc.setdefault(m['year'], 1.0)
            yearly_acc[m['year']] *= 1.0 + m['return_pct'] / 100.0
        yearly_returns = [
            YearlyReturnItem(year=y, return_pct=round((v - 1.0) * 100.0, 4))
            for y, v in sorted(yearly_acc.items())
        ]

        return MonthlyReturnsResponse(
            portfolio_id=portfolio_id,
            cells=[MonthlyReturnCell(**m) for m in monthly],
            yearly_returns=yearly_returns,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )

    def get_drawdown(
        self,
        portfolio_id: int,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> DrawdownResponse:
        start, end = self._resolve_date_range(portfolio_id, user_id, start_date, end_date)
        daily, _ = self._build_monthly_returns(portfolio_id, user_id, start, end)

        peak = 0.0
        peak_date: date | None = None
        peak_value: float | None = None
        max_dd = 0.0
        max_dd_start: date | None = None
        max_dd_end: date | None = None
        current_dd_start: date | None = None
        points: list[DrawdownPoint] = []

        for d in daily:
            cum = d['cumulative_twr']
            if cum >= peak:
                peak = cum
                peak_date = d['date']
                peak_value = d['portfolio_value']
                current_dd_start = d['date']

            dd = ((cum - peak) / peak) * 100.0 if peak > 0 else 0.0

            if dd < max_dd:
                max_dd = dd
                max_dd_start = current_dd_start
                max_dd_end = d['date']

            points.append(DrawdownPoint(
                date=d['date'].isoformat(),
                drawdown_pct=round(dd, 4),
            ))

        current_dd = points[-1].drawdown_pct if points else 0.0

        return DrawdownResponse(
            portfolio_id=portfolio_id,
            points=points,
            max_drawdown_pct=round(max_dd, 4),
            max_drawdown_start=max_dd_start.isoformat() if max_dd_start else None,
            max_drawdown_end=max_dd_end.isoformat() if max_dd_end else None,
            current_drawdown_pct=current_dd,
            peak_date=peak_date.isoformat() if peak_date else None,
            peak_value=round(peak_value, 2) if peak_value is not None else None,
        )

    def get_rolling_windows(
        self,
        portfolio_id: int,
        user_id: str,
        window_months: int = 12,
        risk_free_rate: float = 2.0,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> RollingWindowsResponse:
        start, end = self._resolve_date_range(portfolio_id, user_id, start_date, end_date)
        _, monthly = self._build_monthly_returns(portfolio_id, user_id, start, end)

        points: list[RollingWindowPoint] = []

        for i in range(len(monthly)):
            if i < window_months - 1:
                continue
            window = monthly[i - window_months + 1: i + 1]

            # CAGR: chain monthly returns, annualize
            product = 1.0
            returns: list[float] = []
            for m in window:
                r = m['return_pct'] / 100.0
                product *= 1.0 + r
                returns.append(r)

            cagr = (product ** (12.0 / window_months) - 1.0) * 100.0 if product > 0 else None

            # Annualized volatility: stdev(monthly) * sqrt(12)
            vol: float | None = None
            if len(returns) > 1:
                try:
                    vol = statistics.stdev(returns) * sqrt(12) * 100.0
                except statistics.StatisticsError:
                    vol = None

            # Sharpe ratio
            sharpe: float | None = None
            if cagr is not None and vol is not None and vol > 0:
                sharpe = (cagr - risk_free_rate) / vol

            m_entry = monthly[i]
            label = f"{m_entry['year']}-{m_entry['month']:02d}"
            points.append(RollingWindowPoint(
                date=label,
                cagr_pct=round(cagr, 4) if cagr is not None else None,
                volatility_pct=round(vol, 4) if vol is not None else None,
                sharpe_ratio=round(sharpe, 4) if sharpe is not None else None,
            ))

        return RollingWindowsResponse(
            portfolio_id=portfolio_id,
            window_months=window_months,
            risk_free_rate_pct=risk_free_rate,
            points=points,
        )

    def get_hall_of_fame(
        self,
        portfolio_id: int,
        user_id: str,
        top_n: int = 5,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> HallOfFameResponse:
        start, end = self._resolve_date_range(portfolio_id, user_id, start_date, end_date)
        _, monthly = self._build_monthly_returns(portfolio_id, user_id, start, end)

        # Monthly ranking
        month_entries = [
            RankedPeriod(
                year=m['year'],
                month=m['month'],
                return_pct=m['return_pct'],
                label=f"{self._MONTH_NAMES[m['month'] - 1]} {m['year']}",
            )
            for m in monthly
        ]
        sorted_months = sorted(month_entries, key=lambda x: x.return_pct, reverse=True)
        best_months = sorted_months[:top_n]
        worst_months = list(reversed(sorted_months[-top_n:]))

        # Yearly ranking
        yearly_acc: dict[int, float] = {}
        for m in monthly:
            yearly_acc.setdefault(m['year'], 1.0)
            yearly_acc[m['year']] *= 1.0 + m['return_pct'] / 100.0
        year_entries = [
            RankedPeriod(
                year=y,
                month=None,
                return_pct=round((v - 1.0) * 100.0, 4),
                label=str(y),
            )
            for y, v in yearly_acc.items()
        ]
        sorted_years = sorted(year_entries, key=lambda x: x.return_pct, reverse=True)
        best_years = sorted_years[:top_n]
        worst_years = list(reversed(sorted_years[-top_n:]))

        return HallOfFameResponse(
            portfolio_id=portfolio_id,
            best_months=best_months,
            worst_months=worst_months,
            best_years=best_years,
            worst_years=worst_years,
        )

    def _resolve_date_range(
        self,
        portfolio_id: int,
        user_id: str,
        start_date: date | None,
        end_date: date | None,
    ) -> tuple[date, date]:
        portfolio_start = self.repo.get_portfolio_created_date(portfolio_id, user_id)
        end = end_date or date.today()
        start = start_date or portfolio_start

        if end < start:
            raise ValueError('Intervallo date non valido')

        if start < portfolio_start:
            start = portfolio_start

        return start, end

    def _resolve_period_range(self, portfolio_id: int, user_id: str, period: str) -> tuple[date, date]:
        period_key = (period or '').lower().strip()
        end = date.today()
        portfolio_start = self.repo.get_portfolio_created_date(portfolio_id, user_id)

        if period_key == 'ytd':
            start = date(end.year, 1, 1)
        elif period_key == 'all':
            start = portfolio_start
        elif period_key in _PERIOD_TO_DAYS:
            start = end - timedelta(days=_PERIOD_TO_DAYS[period_key])
        else:
            raise ValueError('period non valido')

        if start < portfolio_start:
            start = portfolio_start

        if end < start:
            start = end

        return start, end

    def _period_label(self, period: str) -> str:
        labels = {
            '1m': '1 mese',
            '3m': '3 mesi',
            '6m': '6 mesi',
            'ytd': 'Da inizio anno',
            '1y': '1 anno',
            '3y': '3 anni',
            'all': 'Da sempre',
        }
        return labels.get(period, period)

    def _solve_irr(self, flows: list[tuple[float, float]]) -> float | None:
        def npv(rate: float) -> float:
            if rate <= -0.999999:
                return float('inf')
            total = 0.0
            for days, cf in flows:
                total += cf / ((1.0 + rate) ** (days / 365.0))
            return total

        def d_npv(rate: float) -> float:
            if rate <= -0.999999:
                return float('inf')
            total = 0.0
            for days, cf in flows:
                t = days / 365.0
                total += (-t * cf) / ((1.0 + rate) ** (t + 1.0))
            return total

        # Realistic bounds: -99% to +1000% annualized
        low = -0.99
        high = 10.0

        # Detect multiple zero crossings (sign changes) to warn about
        # ambiguous IRR when cashflows change sign multiple times.
        probe_points = [-0.99, -0.9, -0.5, -0.2, 0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
        sign_changes = 0
        prev_f = npv(probe_points[0])
        for x in probe_points[1:]:
            f_x = npv(x)
            if isfinite(prev_f) and isfinite(f_x) and prev_f * f_x < 0:
                sign_changes += 1
            if isfinite(f_x):
                prev_f = f_x
        if sign_changes > 1:
            logger.warning(
                "IRR: NPV curve has %d zero crossings in [%.2f, %.2f] — "
                "multiple IRR solutions possible; returning the first root found.",
                sign_changes, low, high,
            )

        f_low = npv(low)
        f_high = npv(high)

        if isfinite(f_low) and isfinite(f_high) and (f_low == 0 or f_high == 0 or f_low * f_high < 0):
            if scipy_brentq is not None:
                try:
                    return float(scipy_brentq(npv, low, high, maxiter=200, xtol=1e-9))
                except Exception:
                    pass
            return self._bisection(npv, low, high)

        if scipy_newton is not None:
            try:
                value = float(scipy_newton(npv, x0=0.1, fprime=d_npv, maxiter=100, tol=1e-8))
                if low <= value <= high and isfinite(value):
                    return value
            except Exception:
                pass

        return self._search_bisection(npv)

    def _bisection(self, fn, low: float, high: float, max_iter: int = 200) -> float | None:
        f_low = fn(low)
        f_high = fn(high)
        if not isfinite(f_low) or not isfinite(f_high) or f_low * f_high > 0:
            return None
        for _ in range(max_iter):
            mid = (low + high) / 2.0
            f_mid = fn(mid)
            if not isfinite(f_mid):
                return None
            if abs(f_mid) < 1e-8:
                return mid
            if f_low * f_mid <= 0:
                high = mid
                f_high = f_mid
            else:
                low = mid
                f_low = f_mid
        return (low + high) / 2.0

    def _search_bisection(self, fn) -> float | None:
        low = -0.99
        probes = [-0.9, -0.5, -0.2, 0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
        prev_x = low
        prev_f = fn(prev_x)
        for x in probes:
            f_x = fn(x)
            if isfinite(prev_f) and isfinite(f_x) and (prev_f == 0 or f_x == 0 or prev_f * f_x < 0):
                return self._bisection(fn, prev_x, x)
            prev_x = x
            prev_f = f_x
        return None
