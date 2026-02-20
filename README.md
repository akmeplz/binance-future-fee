# Binance Futures Funding 年化监控

实时监控币安**所有在交易中的永续合约**资金费，并按各自结算周期（1h / 4h / 8h）换算年化。

## 功能

- 自动拉取并监控所有 `PERPETUAL` 且 `TRADING` 的合约。
- 自动识别资金费结算周期：
  - 优先使用 `/fapi/v1/fundingInfo` 的 `fundingIntervalHours`
  - 未返回的默认按 8 小时
- 实时显示：
  - 平均年化
  - 合约总数量
  - 分结算周期统计
  - 年化最高/最低 Top5
- 定时刷新合约列表，自动适配上架/下架。

## 运行

```bash
python3 funding_monitor.py
```

常用参数：

```bash
# 每5秒刷新一次显示；每60秒刷新一次合约列表
python3 funding_monitor.py --interval 5 --symbol-refresh 60

# 只执行一次（用于测试）
python3 funding_monitor.py --once
```
