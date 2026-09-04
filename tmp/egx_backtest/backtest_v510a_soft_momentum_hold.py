import glob,json,os,sys
from collections import defaultdict
from datetime import datetime
sys.path.insert(0,"tmp/egx_backtest")
import analyze_v58_hazard_attribution as hz
import backtest_v58_selective_hazard_gate as v58
TRAIN=("2021-01-01","2022-12-31"); V23=("2023-01-01","2023-12-31"); V24=("2024-01-01","2024-12-31"); FINAL=("2025-01-01","2026-02-28")
INITIAL=100000.0; FULL=0.50; HALF_FRICTION=0.0025; TARGET=0.12; STOP=0.045; H=7; SLOTS=2
def exit_price(t,data):
    if t["exit_type"]=="stop": return t["entry"]*(1-STOP)
    if t["exit_type"]=="target": return t["entry"]*(1+TARGET)
    return next(r["close"] for r in data[t["symbol"]] if r["date"]==t["exit_date"])
