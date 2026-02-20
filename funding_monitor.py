#!/usr/bin/env python3
import argparse
import json
import statistics
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

BASE_URL = "https://fapi.binance.com"
USDT = "USDT"
DEFAULT_INTERVAL_HOURS = 8

CHART_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Binance Funding 监控图表</title>
  <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #0b1220; color: #dbe4ff; }
    h2 { margin: 16px; }
    #chart { height: 420px; }
    #meta { margin: 0 16px 16px; opacity: .9; }
  </style>
</head>
<body>
  <h2>币安 USDT 永续资金费监控</h2>
  <div id="meta">加载中...</div>
  <div id="chart"></div>
  <script>
    const chart = LightweightCharts.createChart(document.getElementById('chart'), {
      layout: { background: { color: '#0b1220' }, textColor: '#dbe4ff' },
      grid: { vertLines: { color: '#1b2a4a' }, horzLines: { color: '#1b2a4a' } },
      rightPriceScale: { borderColor: '#304b7a' },
      leftPriceScale: { visible: true, borderColor: '#304b7a' },
      timeScale: { borderColor: '#304b7a', timeVisible: true, secondsVisible: true },
    });

    const avgSeries = chart.addLineSeries({ color: '#4da3ff', lineWidth: 2, title: '平均费率(年化%)' });
    const countSeries = chart.addLineSeries({ color: '#ffd166', lineWidth: 2, title: '合约数量' });
    countSeries.priceScaleId = 'left';

    async function refresh() {
      const r = await fetch('./chart_data.json?_=' + Date.now());
      const data = await r.json();
      const avg = data.points.map(p => ({ time: p.ts, value: p.avg_annualized_pct }));
      const cnt = data.points.map(p => ({ time: p.ts, value: p.contract_count }));
      avgSeries.setData(avg);
      countSeries.setData(cnt);

      const latest = data.points[data.points.length - 1];
      document.getElementById('meta').innerText = latest
        ? `最新: ${latest.time_utc} | 合约数量: ${latest.contract_count} | 平均费率(年化): ${latest.avg_annualized_pct.toFixed(4)}%`
        : '暂无数据';
      chart.timeScale().fitContent();
    }

    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>
"""


@dataclass
class Metrics:
    contract_count: int
    avg_annualized: float


def fetch_json(path: str, timeout: int = 10):
    request = urllib.request.Request(BASE_URL + path, headers={"User-Agent": "funding-monitor/3.0"})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def safe_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def annualize_rate(funding_rate: float, interval_hours: int) -> float:
    return funding_rate * (24 / interval_hours) * 365


def get_usdt_perpetual_trading_symbols() -> Dict[str, dict]:
    payload = fetch_json("/fapi/v1/exchangeInfo")
    now_ms = int(time.time() * 1000)
    symbols: Dict[str, dict] = {}

    for item in payload.get("symbols", []):
        if item.get("contractType") != "PERPETUAL":
            continue
        if item.get("status") != "TRADING":
            continue
        if item.get("marginAsset") != USDT:
            continue
        if item.get("quoteAsset") != USDT:
            continue

        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not symbol.endswith("USDT"):
            continue

        onboard_date = item.get("onboardDate")
        if isinstance(onboard_date, int) and onboard_date > now_ms:
            continue

        symbols[symbol] = item

    return symbols


def get_interval_hours_map() -> Dict[str, int]:
    rows = fetch_json("/fapi/v1/fundingInfo")
    result: Dict[str, int] = {}
    for row in rows:
        symbol = row.get("symbol")
        hours = row.get("fundingIntervalHours")
        if symbol and isinstance(hours, int) and hours > 0:
            result[symbol] = hours
    return result


def get_premium_rows() -> List[dict]:
    rows = fetch_json("/fapi/v1/premiumIndex")
    return rows if isinstance(rows, list) else []


def get_active_24h_ticker_symbols() -> set[str]:
    rows = fetch_json("/fapi/v1/ticker/24hr")
    if not isinstance(rows, list):
        return set()
    symbols = set()
    for row in rows:
        symbol = row.get("symbol")
        if isinstance(symbol, str) and symbol:
            symbols.add(symbol)
    return symbols


def calculate_metrics(
    symbols: Dict[str, dict],
    interval_hours_map: Dict[str, int],
    premium_rows: List[dict],
) -> Metrics:
    annualized_values: List[float] = []

    for row in premium_rows:
        symbol = row.get("symbol")
        if symbol not in symbols:
            continue

        next_funding_time = row.get("nextFundingTime")
        if not isinstance(next_funding_time, (int, float)) or next_funding_time <= 0:
            continue

        mark_price = safe_float(row.get("markPrice"))
        index_price = safe_float(row.get("indexPrice"))
        if mark_price is None or index_price is None:
            continue
        if mark_price <= 0 or index_price <= 0:
            continue

        funding_rate = safe_float(row.get("lastFundingRate"))
        if funding_rate is None:
            funding_rate = safe_float(row.get("fundingRate"))
        if funding_rate is None:
            continue

        interval_hours = interval_hours_map.get(symbol, DEFAULT_INTERVAL_HOURS)
        annualized_values.append(annualize_rate(funding_rate, interval_hours))

    # 数量口径：当前可交易 USDT 永续合约池（与交易端列表更一致）。
    count = len(symbols)
    avg = statistics.mean(annualized_values) if annualized_values else 0.0
    return Metrics(contract_count=count, avg_annualized=avg)


def write_chart_assets(chart_dir: Path):
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "chart.html").write_text(CHART_HTML, encoding="utf-8")


def load_points(path: Path, max_points: int) -> List[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        points = payload.get("points", [])
        return points[-max_points:]
    except Exception:
        return []


def save_points(path: Path, points: List[dict]):
    path.write_text(json.dumps({"points": points}, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="每5秒监控 Binance USDT 永续资金费")
    parser.add_argument("--interval", type=int, default=5, help="刷新间隔秒，默认5")
    parser.add_argument("--symbol-refresh", type=int, default=300, help="合约列表刷新秒，默认300")
    parser.add_argument("--chart-dir", default="./chart", help="图表输出目录")
    parser.add_argument("--max-points", type=int, default=720, help="图表保留最大点数")
    parser.add_argument("--once", action="store_true", help="仅执行一次")
    args = parser.parse_args()

    chart_dir = Path(args.chart_dir)
    data_path = chart_dir / "chart_data.json"
    write_chart_assets(chart_dir)
    print(f"TradingView 图表文件: {chart_dir / 'chart.html'}")

    symbols: Dict[str, dict] = {}
    interval_hours_map: Dict[str, int] = {}
    last_symbol_refresh = 0.0

    while True:
        now = time.time()

        if now - last_symbol_refresh >= args.symbol_refresh or not symbols:
            symbols = get_usdt_perpetual_trading_symbols()
            active_24h = get_active_24h_ticker_symbols()
            if active_24h:
                symbols = {k: v for k, v in symbols.items() if k in active_24h}
            interval_hours_map = get_interval_hours_map()
            last_symbol_refresh = now

        premium_rows = get_premium_rows()
        metrics = calculate_metrics(symbols, interval_hours_map, premium_rows)
        time_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        print(f"[{time_utc} UTC] 合约数量={metrics.contract_count} 平均费率(年化)={metrics.avg_annualized * 100:.4f}%")

        points = load_points(data_path, args.max_points)
        points.append(
            {
                "ts": int(now),
                "time_utc": time_utc,
                "contract_count": metrics.contract_count,
                "avg_annualized_pct": metrics.avg_annualized * 100,
            }
        )
        save_points(data_path, points[-args.max_points :])

        if args.once:
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已停止")
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1)
