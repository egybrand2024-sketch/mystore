import glob,json,os,sys
from collections import defaultdict,Counter
from statistics import mean

sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3
import backtest_v51_correlation_risk as v51

PERIOD=("2024-01-01","2024-12-31"); INITIAL=100000.0; FRICTION=0.005; SLOTS=2

def in_period(d,p): return p[0] <= d <= p[1]
def avg(xs): return mean(xs) if xs else None

def build_maps(data):
    closes={}; dates=set()
    for s,rows in data.items():
        closes[s]={r["date"]:r["close"] for r in rows}; dates.update(closes[s])
    return closes,sorted(dates)

def simulate(trades,raw_by_key,data,market,signal_counts):
    closes,all_dates=build_maps(data); dates=[d for d in all_dates if PERIOD[0]<=d<=PERIOD[1]]; di={d:i for i,d in enumerate(dates)}
    eb=defaultdict(list); xb=defaultdict(list)
    for t in trades: eb[t["entry_date"]].append(t); xb[t["exit_date"]].append(t)
    for d in eb: eb[d].sort(key=lambda x:(-x["liquidity"],-x.get("quality",0),x["symbol"]))
    half=FRICTION/2; cash=INITIAL; pos={}; last={}; curve=[]; real=[]; skipped=[]
    def mark(d):
        pv=0
        for s,q in pos.items():
            px=closes.get(s,{}).get(d)
            if px is not None:last[s]=px
            pv+=q["shares"]*last.get(s,q["entry"])
        return cash+pv,pv
    def rc(d,n):
        i=di[d]; return sum(signal_counts.get(dates[j],0) for j in range(max(0,i-n+1),i+1))
    for d in dates:
        for s in list(pos):
            px=closes.get(s,{}).get(d)
            if px is not None:last[s]=px
        for tr in sorted(xb.get(d,[]),key=lambda x:x["symbol"]):
            s=tr["symbol"]
            if s not in pos: continue
            q=pos.pop(s); proceeds=q["shares"]*tr["exit_price"]*(1-half); cash+=proceeds
            net=proceeds/q["budget"]-1; pnl=proceeds-q["budget"]
            real.append({**{k:q[k] for k in q if k not in {"shares"}},"symbol":s,"exit_date":d,"exit_price":tr["exit_price"],"exit_type":tr["exit_type"],"holding":tr["holding"],"net_return":net,"pnl_egp":pnl})
        for tr in eb.get(d,[]):
            if tr["symbol"] in pos: skipped.append({"date":d,"symbol":tr["symbol"],"reason":"duplicate_symbol"}); continue
            if len(pos)>=SLOTS: skipped.append({"date":d,"symbol":tr["symbol"],"reason":"max_positions"}); continue
            eq,_=mark(d); budget=min(eq*0.50,cash)
            if budget<=1: skipped.append({"date":d,"symbol":tr["symbol"],"reason":"cash"}); continue
            comp=None; comp_ret=None
            if pos:
                osym,oq=next(iter(pos.items())); comp=osym; px=closes.get(osym,{}).get(d,last.get(osym,oq["entry"])); comp_ret=px/oq["entry"]-1
            raw=raw_by_key[(tr["symbol"],d)]; invested=budget*(1-half); shares=invested/tr["entry"]; cash-=budget
            pos[tr["symbol"]]={"shares":shares,"entry":tr["entry"],"entry_date":d,"budget":budget,"entry_equity":eq,"slot_at_entry":len(pos)+1,"companion":comp,"companion_open_return":comp_ret,"recent_signals_3":rc(d,3),"recent_signals_5":rc(d,5),"market5":market["m5"].get(d),"market20":market["m20"].get(d),"breadth20":market["breadth20"].get(d),"quality":raw.get("quality"),"breakout_vol_ratio":raw.get("breakout_vol_ratio"),"clv":raw.get("clv"),"body":raw.get("body"),"rs20":raw.get("rs20"),"nearest_overhead":raw.get("nearest_overhead")}
            last[tr["symbol"]]=tr["entry"]
        eq,pv=mark(d); curve.append({"date":d,"equity":eq,"cash":cash,"exposure":pv/eq if eq else 0,"open":len(pos),"positions":[{"symbol":s,"entry_date":q["entry_date"],"open_return":closes.get(s,{}).get(d,last.get(s,q["entry"]))/q["entry"]-1} for s,q in pos.items()]})
    peak=-1; maxdd=0; pdate=tdate=None; peq=teq=None
    for r in curve:
        if r["equity"]>peak: peak=r["equity"]; last_peak=r["date"]
        dd=r["equity"]/peak-1
        if dd<maxdd: maxdd=dd; pdate=last_peak; tdate=r["date"]; peq=peak; teq=r["equity"]
    return {"curve":curve,"realized":real,"skipped":skipped,"dd_peak":pdate,"dd_trough":tdate,"dd_peak_equity":peq,"dd_trough_equity":teq,"max_drawdown":maxdd}

def stats(rows):
    if not rows:return {"n":0}
    out={"n":len(rows),"targets":sum(r["exit_type"]=="target" for r in rows),"stops":sum(r["exit_type"]=="stop" for r in rows),"timeouts":sum(r["exit_type"]=="timeout" for r in rows),"positive_rate":sum(r["net_return"]>0 for r in rows)/len(rows),"pnl_egp":sum(r["pnl_egp"] for r in rows)}
    for f in ["net_return","holding","quality","breakout_vol_ratio","clv","body","rs20","nearest_overhead","market5","market20","breadth20","recent_signals_3","recent_signals_5","companion_open_return"]:
        xs=[r[f] for r in rows if r.get(f) is not None]; out[f+"_avg"]=avg(xs)
    out["second_slot_rate"]=sum(r.get("slot_at_entry")==2 for r in rows)/len(rows)
    return out

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw"); data={}
    for fp in sorted(glob.glob(os.path.join(root,"*","*.csv"))):
        s=os.path.basename(fp).split(".")[0].upper(); rows=v3.load_csv_all(fp)
        if len(rows)>=100:data[s]=rows
    market=v3.build_market_maps(data); raw=[]
    for s,rows in data.items(): raw+=v51.collect(s,rows,market)
    raw_by_key={(x["symbol"],x["entry_date"]):x for x in raw}; alltr=[v51.finalize(x) for x in raw]
    tr24=[x for x in alltr if in_period(x["entry_date"],PERIOD) and x["exit_date"]<=PERIOD[1]]; signal_counts=Counter(x["entry_date"] for x in alltr)
    sim=simulate(tr24,raw_by_key,data,market,signal_counts); peak=sim["dd_peak"]; trough=sim["dd_trough"]; real=sim["realized"]
    overlap=[r for r in real if r["entry_date"]<=trough and r["exit_date"]>=peak]; entered=[r for r in real if peak<=r["entry_date"]<=trough]; exited=[r for r in real if peak<=r["exit_date"]<=trough]; pre=[r for r in real if r["exit_date"]<peak]; post=[r for r in real if r["entry_date"]>trough]
    for r in overlap:r["pnl_vs_peak_pct"]=r["pnl_egp"]/sim["dd_peak_equity"]
    ordered=sorted(real,key=lambda x:(x["exit_date"],x["symbol"])); runs=[]; cur=[]
    for r in ordered:
        if r["net_return"]<0:cur.append(r)
        else:
            if cur:runs.append(cur);cur=[]
    if cur:runs.append(cur)
    loss_runs=[{"n":len(run),"start":run[0]["exit_date"],"end":run[-1]["exit_date"],"pnl_egp":sum(x["pnl_egp"] for x in run),"trades":[{"symbol":x["symbol"],"entry_date":x["entry_date"],"exit_date":x["exit_date"],"net_return":x["net_return"],"exit_type":x["exit_type"],"slot":x["slot_at_entry"]} for x in run]} for run in runs]
    loss_runs.sort(key=lambda x:(-x["n"],x["pnl_egp"]))
    one_stop=0.50*((1-FRICTION/2)*(1-0.045)*(1-FRICTION/2)-1)
    cb={r["date"]:r for r in sim["curve"]}
    result={"analysis":"v3.2 2024 drawdown decomposition","fixed":{"target":0.12,"stop":0.045,"horizon":7,"slots":2,"nominal_slot":0.50,"roundtrip_friction":FRICTION},"summary":{"dd_peak":peak,"dd_peak_equity":sim["dd_peak_equity"],"dd_trough":trough,"dd_trough_equity":sim["dd_trough_equity"],"max_drawdown":sim["max_drawdown"],"absolute_drop_egp":sim["dd_trough_equity"]-sim["dd_peak_equity"],"accepted_trades_2024":len(real),"skipped_2024":len(sim["skipped"])},"snapshots":{"peak":cb[peak],"trough":cb[trough]},"drawdown_trade_sets":{"overlap_count":len(overlap),"entered_during_count":len(entered),"exited_during_count":len(exited),"overlap_trades":sorted(overlap,key=lambda x:x["pnl_egp"]),"entered_during":sorted(entered,key=lambda x:(x["entry_date"],x["symbol"])),"exited_during":sorted(exited,key=lambda x:(x["exit_date"],x["symbol"]))},"regime_comparison":{"pre_drawdown":stats(pre),"drawdown_overlap":stats(overlap),"post_drawdown":stats(post),"full_year":stats(real)},"loss_runs":loss_runs,"mechanics":{"one_full_stop_50pct_slot":one_stop,"three_full_stops_compounded":(1+one_stop)**3-1,"four_full_stops_compounded":(1+one_stop)**4-1},"skipped":sim["skipped"]}
    with open("tmp/egx_backtest/results_v32_2024_drawdown_analysis.json","w",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
