from __future__ import annotations

from datetime import date, timedelta
from math import isfinite

from .models import MWRResult, PerformanceSummary, TWRResult, TWRTimeseriesPoint
from .repository import PortfolioRepository

try:
    from scipy.optimize import brentq as scipy_brentq  # type: ignore
    from scipy.optimize import newton as scipy_newton  # type: ignore
except Exception:  # pragma: no cover - optional dependency in runtime
    scipy_brentq = None
    scipy_newton = None


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

    def calculate_twr(
        self,
        portfolio_id: int,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> TWRResult:
        start, end = self._resolve_date_range(portfolio_id, user_id, start_date, end_date)
        period_days = max((end - start).days, 1)

        cashflows = self.repo.get_external_cashflows(portfolio_id, user_id, start_date=start, end_date=end)
        cashflow_by_day: dict[date, float] = {}
        for cf in cashflows:
            day = date.fromisoformat(cf.date)
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

        cashflows = self.repo.get_external_cashflows(portfolio_id, user_id, start_date=start, end_date=end)
        start_value = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, start)
        end_value = self.repo.get_portfolio_value_at_date(portfolio_id, user_id, end)

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
        cashflows = self.repo.get_external_cashflows(portfolio_id, user_id, start_date=start, end_date=end)

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
        cashflows = self.repo.get_external_cashflows(portfolio_id, user_id, start_date=start, end_date=end)

        cf_by_day: dict[date, float] = {}
        for cf in cashflows:
            day = date.fromisoformat(cf.date)
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

        low = -0.9999
        high = 10.0
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
                if value > -0.999999 and isfinite(value):
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
        low = -0.9999
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
