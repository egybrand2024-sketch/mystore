import os, glob, json, sys
sys.path.insert(0, "tmp/egx_backtest")
import backtest_v2 as b

# Robust v2 research:
# - Candidate universe remains frozen v1 signals.
# - Configs are NOT selected on 2025+.
# - Require robustness across two separate validation years (2023 and 2024).
# - 2025-2026 is shown only after selection.

FOLD1 = ("2023-01-01", "2023-12-31")
FOLD2 = ("2024-01-01", "2024-12-31")
FINAL = ("2025-01-01", "2026-02-28")
MIN_FOLD_SIGNALS = 25
MIN_FOLD_SYMBOLS = 15


def in_period(s, period):
    return period[0] <= s["date"] <= period[1]


def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw")
    files=sorted(glob.glob(os.path.join(root,"*","*.csv")))
    all_sigs=[]; tested=0
    for path in files:
        symbol=os.path.basename(path).split(".")[0].upper()
        rows=b.load_csv(path)
        if len(rows)<b.MAX_BASE+b.HORIZON+20: continue
        tested+=1
        all_sigs.extend(b.collect_signals(symbol,rows))

    f1=[s for s in all_sigs if in_period(s,FOLD1)]
    f2=[s for s in all_sigs if in_period(s,FOLD2)]
    final=[s for s in all_sigs if in_period(s,FINAL)]

    v1_f1=b.summary(f1); v1_f2=b.summary(f2); v1_final=b.summary(final)

    ranked=[]
    for cfg in b.generate_grid():
        a=[s for s in f1 if b.passes(s,cfg)]
        c=[s for s in f2 if b.passes(s,cfg)]
        if len(a)<MIN_FOLD_SIGNALS or len(c)<MIN_FOLD_SIGNALS: continue
        if len(set(x["symbol"] for x in a))<MIN_FOLD_SYMBOLS: continue
        if len(set(x["symbol"] for x in c))<MIN_FOLD_SYMBOLS: continue
        wa=sum(x["success"] for x in a); wc=sum(x["success"] for x in c)
        wra=wa/len(a); wrc=wc/len(c)
        la=b.wilson_lower(wa,len(a),z=1.0); lc=b.wilson_lower(wc,len(c),z=1.0)
        # Maximize the weaker validation fold, then average lower bound, then sample size.
        score_min=min(la,lc)
        score_avg=(la+lc)/2
        ranked.append({
            "config":cfg,
            "fold1":b.summary(a),
            "fold2":b.summary(c),
            "score_min_wilson":score_min,
            "score_avg_wilson":score_avg,
            "combined_signals":len(a)+len(c),
        })

    ranked.sort(key=lambda x:(x["score_min_wilson"],x["score_avg_wilson"],x["combined_signals"]),reverse=True)
    best=ranked[0]
    cfg=best["config"]
    fs=[s for s in final if b.passes(s,cfg)]

    # Also create a consensus rule profile from top 20 configs so we can see stable thresholds.
    top=ranked[:20]
    consensus={}
    for key in cfg:
        vals=[x["config"][key] for x in top]
        counts={str(v):vals.count(v) for v in sorted(set(vals))}
        consensus[key]=counts

    result={
        "pattern":"Defensive Lift v2 robust research",
        "dataset":{"stocks_tested":tested,"files_found":len(files),"start":b.START,"end":b.END},
        "selection_protocol":{
            "validation_fold_1":FOLD1,
            "validation_fold_2":FOLD2,
            "final_evaluation":FINAL,
            "final_period_not_used_in_algorithmic_selection":True,
            "minimum_signals_per_validation_fold":MIN_FOLD_SIGNALS,
            "minimum_unique_symbols_per_validation_fold":MIN_FOLD_SYMBOLS,
            "ranking":"maximize the weaker fold's 1-sigma Wilson lower bound, then average lower bound, then sample size",
            "target":b.TARGET,"stop":b.STOP,"horizon":b.HORIZON,
        },
        "v1_benchmark":{"2023":v1_f1,"2024":v1_f2,"final_2025_2026":v1_final},
        "eligible_configs":len(ranked),
        "selected_config":cfg,
        "selected_validation_2023":best["fold1"],
        "selected_validation_2024":best["fold2"],
        "final_2025_2026":b.summary(fs),
        "final_win_rate_change_vs_v1":(b.summary(fs)["win_rate"]-v1_final["win_rate"]) if fs else None,
        "top20_threshold_consensus":consensus,
        "top10_configs":ranked[:10],
        "final_signals":fs,
    }
    with open("tmp/egx_backtest/results_v2_robust.json","w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ["pattern","selection_protocol","v1_benchmark","eligible_configs","selected_config","selected_validation_2023","selected_validation_2024","final_2025_2026","final_win_rate_change_vs_v1","top20_threshold_consensus"]},indent=2))

if __name__=="__main__": main()
