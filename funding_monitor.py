#!/usr/bin/env python3
import argparse
import json
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

BASE_URL = "https://fapi.binance.com"
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
  <h2>币安永续合约资金费监控</h2>
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


def fetch_json(path: str, timeout: int = 10):
    req = urllib.request.Request(BASE_URL + path, headers={"User-Agent": "funding-monitor/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_trading_perpetual_symbols() -> Dict[str, dict]:
    data = fetch_json("/fapi/v1/exchangeInfo")
    now_ms = int(time.time() * 1000)
    symbols = {}
    for item in data.get("symbols", []):
        if item.get("contractType") == "PERPETUAL" and item.get("status") == "TRADING":
            onboard = item.get("onboardDate")
            if isinstance(onboard, int) and onboard > now_ms:
                continue
            symbols[item["symbol"]] = item
    return symbols


def get_interval_hours_map() -> Dict[str, int]:
    rows = fetch_json("/fapi/v1/fundingInfo")
    interval_map: Dict[str, int] = {}
    for row in rows:
        symbol = row.get("symbol")
        hours = row.get("fundingIntervalHours")
        if symbol and isinstance(hours, int) and hours > 0:
            interval_map[symbol] = hours
    return interval_map


def get_premium_index_rows() -> List[dict]:
    data = fetch_json("/fapi/v1/premiumIndex")
    return data if isinstance(data, list) else []


def annualize_rate(funding_rate: float, interval_hours: int) -> float:
    return funding_rate * (24 / interval_hours) * 365


def collect_metrics(symbol_meta: Dict[str, dict], interval_hours_map: Dict[str, int], premium_rows: List[dict]) -> Tuple[int, float]:
    premium_map = {row.get("symbol"): row for row in premium_rows if row.get("symbol")}
    annualized_values: List[float] = []

    for symbol in symbol_meta:
        row = premium_map.get(symbol)
        if not row:
            continue
        raw = row.get("lastFundingRate", row.get("fundingRate"))
        try:
            rate = float(raw)
        except (TypeError, ValueError):
            continue
        interval_hours = interval_hours_map.get(symbol, 8)
        annualized_values.append(annualize_rate(rate, interval_hours))

    count = len(annualized_values)
    avg_annualized = statistics.mean(annualized_values) if annualized_values else 0.0
    return count, avg_annualized


def write_chart_assets(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "chart.html").write_text(CHART_HTML, encoding="utf-8")


def load_points(path: Path, max_points: int) -> List[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        points = data.get("points", [])
        return points[-max_points:]
    except Exception:
        return []


def save_points(path: Path, points: List[dict]):
    path.write_text(json.dumps({"points": points}, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="5秒监控币安合约数量和平均费率(年化)")
    parser.add_argument("--interval", type=int, default=5, help="刷新间隔秒数，默认5")
    parser.add_argument("--symbol-refresh", type=int, default=300, help="合约列表刷新秒数，默认300")
    parser.add_argument("--chart-dir", default="./chart", help="图表输出目录，默认 ./chart")
    parser.add_argument("--max-points", type=int, default=720, help="图表最多保留点数，默认720")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    chart_dir = Path(args.chart_dir)
    data_path = chart_dir / "chart_data.json"
    write_chart_assets(chart_dir)

    print(f"TradingView 图表文件: {chart_dir / 'chart.html'}")

    symbol_meta: Dict[str, dict] = {}
    interval_hours_map: Dict[str, int] = {}
    last_symbol_refresh = 0.0

    while True:
        now = time.time()
        if now - last_symbol_refresh >= args.symbol_refresh or not symbol_meta:
            symbol_meta = get_trading_perpetual_symbols()
            interval_hours_map = get_interval_hours_map()
            last_symbol_refresh = now

        premium_rows = get_premium_index_rows()
        count, avg_annualized = collect_metrics(symbol_meta, interval_hours_map, premium_rows)
        ts = int(now)
        time_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        print(f"[{time_utc} UTC] 合约数量={count} 平均费率(年化)={avg_annualized * 100:.4f}%")

        points = load_points(data_path, args.max_points)
        points.append({
            "ts": ts,
            "time_utc": time_utc,
            "contract_count": count,
            "avg_annualized_pct": avg_annualized * 100,
        })
        points = points[-args.max_points:]
        save_points(data_path, points)

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
