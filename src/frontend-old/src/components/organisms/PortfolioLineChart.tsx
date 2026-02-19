import { useMemo, useState, type MouseEvent } from "react";

import type { TimeSeriesPoint } from "../../types";
import Button from "../atoms/Button";
import Panel from "../atoms/Panel";

type ChartRange = "1M" | "3M" | "YTD" | "1Y";

const chartRanges: ChartRange[] = ["1M", "3M", "YTD", "1Y"];

function formatDate(dateValue: string): string {
  const date = new Date(`${dateValue}T00:00:00`);
  return date.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

type PortfolioLineChartProps = {
  timeseries: TimeSeriesPoint[];
  currencyFormatter: Intl.NumberFormat;
};

function PortfolioLineChart({ timeseries, currencyFormatter }: PortfolioLineChartProps) {
  const [chartRange, setChartRange] = useState<ChartRange>("1Y");
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const filteredTimeseries = useMemo(() => {
    if (timeseries.length === 0) {
      return [];
    }
    const last = new Date(`${timeseries[timeseries.length - 1].date}T00:00:00`);
    let threshold = new Date(last);

    if (chartRange === "1M") {
      threshold.setDate(last.getDate() - 30);
    } else if (chartRange === "3M") {
      threshold.setDate(last.getDate() - 90);
    } else if (chartRange === "YTD") {
      threshold = new Date(last.getFullYear(), 0, 1);
    } else {
      threshold.setDate(last.getDate() - 365);
    }

    return timeseries.filter((point) => new Date(`${point.date}T00:00:00`) >= threshold);
  }, [timeseries, chartRange]);

  const chartModel = useMemo(() => {
    const width = 900;
    const height = 300;
    const margin = { top: 20, right: 16, bottom: 34, left: 72 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;

    if (filteredTimeseries.length < 2) {
      return {
        width,
        height,
        margin,
        plotWidth,
        plotHeight,
        path: "",
        points: [] as { x: number; y: number }[],
        yTicks: [] as { value: number; y: number }[],
        xTicks: [] as { label: string; x: number }[],
      };
    }

    const values = filteredTimeseries.map((point) => point.market_value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = Math.max(max - min, 1);

    const points = filteredTimeseries.map((point, index) => {
      const x = margin.left + (index / (filteredTimeseries.length - 1)) * plotWidth;
      const y = margin.top + plotHeight - ((point.market_value - min) / range) * plotHeight;
      return { x, y };
    });

    const path = points
      .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
      .join(" ");

    const yTicks = [max, min + range / 2, min].map((value) => ({
      value,
      y: margin.top + plotHeight - ((value - min) / range) * plotHeight,
    }));

    const firstLabel = filteredTimeseries[0].date;
    const midLabel = filteredTimeseries[Math.floor((filteredTimeseries.length - 1) / 2)].date;
    const lastLabel = filteredTimeseries[filteredTimeseries.length - 1].date;
    const xTicks = [
      { label: formatDate(firstLabel), x: margin.left },
      { label: formatDate(midLabel), x: margin.left + plotWidth / 2 },
      { label: formatDate(lastLabel), x: margin.left + plotWidth },
    ];

    return {
      width,
      height,
      margin,
      plotWidth,
      plotHeight,
      path,
      points,
      yTicks,
      xTicks,
    };
  }, [filteredTimeseries]);

  const hoverPoint = useMemo(() => {
    if (hoverIndex === null || hoverIndex < 0 || hoverIndex >= filteredTimeseries.length) {
      return null;
    }
    return {
      data: filteredTimeseries[hoverIndex],
      coord: chartModel.points[hoverIndex],
    };
  }, [hoverIndex, filteredTimeseries, chartModel.points]);

  const latestPoint = filteredTimeseries[filteredTimeseries.length - 1];

  function onChartHover(event: MouseEvent<SVGRectElement>) {
    if (filteredTimeseries.length < 2) {
      setHoverIndex(null);
      return;
    }

    const rect = event.currentTarget.getBoundingClientRect();
    const relativeX = event.clientX - rect.left;
    const plotX = (relativeX / rect.width) * chartModel.plotWidth;
    const step = chartModel.plotWidth / (filteredTimeseries.length - 1);
    const idx = Math.round(plotX / step);
    setHoverIndex(Math.max(0, Math.min(filteredTimeseries.length - 1, idx)));
  }

  return (
    <Panel title="Andamento 1Y">
      <p>
        Ultimo punto: {latestPoint?.date ?? "n/a"} - {latestPoint ? currencyFormatter.format(latestPoint.market_value) : currencyFormatter.format(0)}
      </p>
      <div className="range-switch">
        {chartRanges.map((rangeValue) => (
          <Button
            type="button"
            key={rangeValue}
            variant="range"
            active={rangeValue === chartRange}
            onClick={() => {
              setChartRange(rangeValue);
              setHoverIndex(null);
            }}
          >
            {rangeValue}
          </Button>
        ))}
      </div>
      <div className="chart-wrap">
        {chartModel.path ? (
          <svg viewBox={`0 0 ${chartModel.width} ${chartModel.height}`} role="img" aria-label="Andamento valore portfolio su 1 anno">
            {chartModel.yTicks.map((tick) => (
              <g key={tick.y}>
                <line className="y-grid-line" x1={chartModel.margin.left} y1={tick.y} x2={chartModel.width - chartModel.margin.right} y2={tick.y} />
                <text className="axis-label axis-label-y" x={chartModel.margin.left - 10} y={tick.y + 4}>
                  {currencyFormatter.format(tick.value)}
                </text>
              </g>
            ))}

            {chartModel.xTicks.map((tick) => (
              <text key={tick.label + tick.x} className="axis-label axis-label-x" x={tick.x} y={chartModel.height - 10} textAnchor="middle">
                {tick.label}
              </text>
            ))}

            <path d={chartModel.path} className="line-path" />

            {hoverPoint && (
              <g>
                <line
                  className="hover-line"
                  x1={hoverPoint.coord.x}
                  y1={chartModel.margin.top}
                  x2={hoverPoint.coord.x}
                  y2={chartModel.height - chartModel.margin.bottom}
                />
                <circle className="hover-dot" cx={hoverPoint.coord.x} cy={hoverPoint.coord.y} r={4} />
                <g transform={`translate(${hoverPoint.coord.x + 8}, ${hoverPoint.coord.y - 12})`}>
                  <rect className="tooltip-bg" rx={6} ry={6} width={140} height={40} />
                  <text className="tooltip-text" x={8} y={16}>
                    {formatDate(hoverPoint.data.date)}
                  </text>
                  <text className="tooltip-text" x={8} y={31}>
                    {currencyFormatter.format(hoverPoint.data.market_value)}
                  </text>
                </g>
              </g>
            )}

            <rect
              className="hover-capture"
              x={chartModel.margin.left}
              y={chartModel.margin.top}
              width={chartModel.plotWidth}
              height={chartModel.plotHeight}
              onMouseMove={onChartHover}
              onMouseLeave={() => setHoverIndex(null)}
            />
          </svg>
        ) : (
          <p className="hint">Dati insufficienti per il grafico.</p>
        )}
      </div>
      <div className="chart-legend">
        <span className="legend-item">
          <i className="legend-dot line" /> Valore portfolio
        </span>
        <span className="legend-item">
          <i className="legend-dot hover" /> Punto selezionato
        </span>
      </div>
    </Panel>
  );
}

export default PortfolioLineChart;
