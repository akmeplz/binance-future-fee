#!/usr/bin/env python3
import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

BASE_URL = "https://fapi.binance.com"


def fetch_json(path: str, timeout: int = 10):
    req = urllib.request.Request(BASE_URL + path, headers={"User-Agent": "funding-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_trading_perpetual_symbols() -> Dict[str, dict]:
    data = fetch_json("/fapi/v1/exchangeInfo")
    now_ms = int(time.time() * 1000)
    symbols = {}
    for item in data.get("symbols", []):
        if item.get("contractType") != "PERPETUAL":
            continue
        if item.get("status") != "TRADING":
            continue
        onboard_date = item.get("onboardDate")
        if isinstance(onboard_date, int) and onboard_date > now_ms:
            continue
        symbols[item["symbol"]] = item
    return symbols


def get_interval_hours_map() -> Dict[str, int]:
    interval_map: Dict[str, int] = {}
    # Binance only returns overridden intervals here; missing symbols default to 8 hours.
    try:
        rows = fetch_json("/fapi/v1/fundingInfo")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"获取 fundingInfo 失败: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"获取 fundingInfo 失败: {e.reason}") from e

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
    settlements_per_year = (24 / interval_hours) * 365
    return funding_rate * settlements_per_year


def clear_screen():
    sys.stdout.write("\033[2J\033[H")


def format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def collect_snapshot(
    symbol_meta: Dict[str, dict], interval_hours_map: Dict[str, int], premium_rows: List[dict]
) -> Tuple[List[Tuple[str, float, int]], List[str]]:
    records: List[Tuple[str, float, int]] = []
    warnings: List[str] = []

    premium_map = {row.get("symbol"): row for row in premium_rows if row.get("symbol")}

    for symbol in symbol_meta:
        row = premium_map.get(symbol)
        if not row:
            warnings.append(f"{symbol}: 无实时 fundingRate")
            continue
        rate_raw = row.get("lastFundingRate")
        if rate_raw is None:
            rate_raw = row.get("fundingRate")
        try:
            funding_rate = float(rate_raw)
        except (TypeError, ValueError):
            warnings.append(f"{symbol}: fundingRate 非法值 {rate_raw}")
            continue

        interval_hours = interval_hours_map.get(symbol, 8)
        ann = annualize_rate(funding_rate, interval_hours)
        records.append((symbol, ann, interval_hours))

    return records, warnings


def render(snapshot: List[Tuple[str, float, int]], warnings: List[str], updated_at: datetime):
    clear_screen()

    count = len(snapshot)
    annualized_values = [x[1] for x in snapshot]
    avg_annualized = statistics.mean(annualized_values) if annualized_values else 0.0

    by_interval: Dict[int, List[float]] = {}
    for _, ann, interval in snapshot:
        by_interval.setdefault(interval, []).append(ann)

    print("币安合约资金费年化监控（实时）")
    print("=" * 52)
    print(f"更新时间(UTC): {updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"合约总数量: {count}")
    print(f"平均年化: {format_pct(avg_annualized)}")
    print("-" * 52)

    if by_interval:
        print("分结算周期统计:")
        for interval in sorted(by_interval):
            vals = by_interval[interval]
            print(
                f"  {interval}小时: 数量={len(vals):4d} 平均年化={format_pct(statistics.mean(vals))}"
            )
    else:
        print("暂无数据")

    if snapshot:
        top = sorted(snapshot, key=lambda x: x[1], reverse=True)[:5]
        bottom = sorted(snapshot, key=lambda x: x[1])[:5]
        print("-" * 52)
        print("年化最高 Top 5:")
        for symbol, ann, interval in top:
            print(f"  {symbol:15s} {format_pct(ann):>10s} ({interval}h)")

        print("年化最低 Top 5:")
        for symbol, ann, interval in bottom:
            print(f"  {symbol:15s} {format_pct(ann):>10s} ({interval}h)")

    if warnings:
        print("-" * 52)
        print(f"警告: {len(warnings)} 条（仅显示前 5 条）")
        for line in warnings[:5]:
            print("  -", line)



def main():
    parser = argparse.ArgumentParser(description="监控币安所有永续合约资金费年化")
    parser.add_argument("--interval", type=int, default=15, help="刷新间隔秒数，默认 15")
    parser.add_argument(
        "--symbol-refresh", type=int, default=300, help="合约列表刷新秒数（考虑上架/下架），默认 300"
    )
    parser.add_argument("--once", action="store_true", help="仅抓取并展示一次")
    args = parser.parse_args()

    if args.interval <= 0 or args.symbol_refresh <= 0:
        raise SystemExit("interval 和 symbol-refresh 必须是正整数")

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
        snapshot, warnings = collect_snapshot(symbol_meta, interval_hours_map, premium_rows)
        render(snapshot, warnings, datetime.now(timezone.utc))

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
