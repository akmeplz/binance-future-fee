# Binance Futures Funding 监控（5秒）

按 5 秒间隔监控币安 **USDT 永续**，并输出：
- 合约数量（仅统计当前有有效资金费结算时间、有效标记价/指数价、且费率可解析的 USDT 永续）
- 平均费率（年化）

> 说明：为避免“数量偏大”，数量与平均值使用同一口径（同一批有效 funding 合约）。

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
