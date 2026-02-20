# Binance Futures Funding 监控（5秒）

按 5 秒间隔监控币安 **USDT 本位（仅 `marginAsset=USDT` 且 `quoteAsset=USDT`）**在交易永续合约，输出：
- 合约数量（有资金费数据）
- 平均费率（年化）

并使用 TradingView 的 `lightweight-charts` 生成本地图表页面。

## 运行

```bash
python3 funding_monitor.py
```

示例输出（每 5 秒一行）：

```text
[2026-02-20 10:00:00 UTC] 合约数量=400 平均费率(年化)=12.3456%
```

## 图表

脚本启动后会生成：
- `chart/chart.html`
- `chart/chart_data.json`

本地查看（任选其一）：

```bash
python3 -m http.server 8000 --directory chart
# 然后打开 http://127.0.0.1:8000/chart.html
```

## 参数

```bash
python3 funding_monitor.py \
  --interval 5 \
  --symbol-refresh 300 \
  --chart-dir ./chart \
  --max-points 720
```
