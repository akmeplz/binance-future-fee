# Binance Futures Funding 监控（5秒）

按 5 秒间隔监控币安 **USDT 永续**，并输出：
- 合约数量（当前可交易 USDT 永续合约池；由 `exchangeInfo` 与 `24hr ticker` 交集得到）
- 平均费率（年化）

> 说明：数量与交易端列表口径对齐；平均费率仍按有有效资金费与价格数据的合约计算。

## 运行

```bash
python3 funding_monitor.py
```

## 图表

脚本会自动生成：
- `chart/chart.html`
- `chart/chart_data.json`

查看方式：

```bash
python3 -m http.server 8000 --directory chart
# 打开 http://127.0.0.1:8000/chart.html
```

## 参数

```bash
python3 funding_monitor.py \
  --interval 5 \
  --symbol-refresh 300 \
  --chart-dir ./chart \
  --max-points 720
```
