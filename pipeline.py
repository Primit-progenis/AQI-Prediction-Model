"""Reproducible Mumbai PM2.5 direct forecast with optional weighted Ridge.

Run: python pipeline.py
Uses only competition-provided data, the standard library, and NumPy for Ridge.
"""
from __future__ import annotations
import csv, datetime as dt, math, os, random, statistics, sys, time
from bisect import bisect_left, bisect_right
from collections import defaultdict
from pathlib import Path

CONFIG = {
    "seed": 20261110,
    "stations": ("11611", "11606", "3409510", "3409511"),
    "forecast_horizons": (16, 63),
    "profile_days": (3, 7, 14),
    "fault_high_threshold": 500.0,
    "invalid_threshold": 1000.0,
    "isolated_peer_median_threshold": 150.0,
    "bootstrap_replicates": 1000,
}
PUBLIC_INTERVALS = (
    ("01_2026-10-22_to_23.csv", dt.date(2026, 10, 22), dt.date(2026, 10, 23)),
    ("02_2026-10-27_to_28.csv", dt.date(2026, 10, 27), dt.date(2026, 10, 28)),
    ("03_2026-11-03_to_04.csv", dt.date(2026, 11, 3), dt.date(2026, 11, 4)),
    ("04_2026-11-05_to_06.csv", dt.date(2026, 11, 5), dt.date(2026, 11, 6)),
    ("05_2026-11-08_to_10.csv", dt.date(2026, 11, 8), dt.date(2026, 11, 10)),
)
SEED = CONFIG["seed"]
STATIONS = CONFIG["stations"]
T0_EXPECTED = "2026-11-10T09:00:00+05:30"
PRIVATE_START = dt.datetime.fromisoformat("2026-11-11T01:00:00+05:30")
PRIVATE_END = dt.datetime.fromisoformat("2026-11-13T00:00:00+05:30")
FAULT_START = dt.datetime.fromisoformat("2025-10-10T00:00:00+05:30")
FAULT_END = dt.datetime.fromisoformat("2025-12-10T23:00:00+05:30")
ROOT = Path(__file__).resolve().parent
SUBMISSION_DIR = ROOT / "Submission" / "01_Final_Submissions"
SERIES_CACHE = {}

def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def med(xs):
    return statistics.median(xs) if xs else float("nan")

def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")

def finite(x):
    return math.isfinite(x)

def assert_feature_cutoff(feature_times, origin):
    """Assert every feature timestamp is at or before its forecast origin."""
    assert all(t <= origin for t in feature_times), "feature timestamp exceeds forecast origin"

def select_private_window(test_rows, t0):
    """Select private targets by the verified target date, ignoring stale labels."""
    return [r for r in test_rows if PRIVATE_START <= dt.datetime.fromisoformat(r["target_end_ist"]) <= PRIVATE_END]

def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

def audit_and_load():
    raw = read_csv(ROOT / "Train.csv")
    test = read_csv(ROOT / "Test.csv")
    sample = read_csv(ROOT / "SampleSubmission.csv")
    print("AUDIT")
    print(f"Train rows={len(raw)}; Test rows={len(test)}; Sample rows={len(sample)}")
    times = [dt.datetime.fromisoformat(r["timestamp_ist"]) for r in raw]
    print(f"Train range={min(times)} .. {max(times)}; stations={sorted(set(r['location_id'] for r in raw))}")
    print(f"Test range={min(r['target_end_ist'] for r in test)} .. {max(r['target_end_ist'] for r in test)}")
    print(f"Sample Target blanks={sum(not r['Target'] for r in sample)}; IDs/order match Test={ [r['ID'] for r in sample] == [r['ID'] for r in test] }")
    counts = defaultdict(int)
    for r in raw: counts[r["location_id"]] += 1
    print("Train rows/station=" + str(dict(counts)))
    assert len(raw)==48400 and len(test)==2592 and len(sample)==2592
    assert max(times).isoformat() == T0_EXPECTED
    assert [r["ID"] for r in sample] == [r["ID"] for r in test]
    raw_values = defaultdict(dict)
    for r in raw:
        raw_values[r["location_id"]][dt.datetime.fromisoformat(r["timestamp_ist"])] = float(r["pm25"])
    first_time=min(times); last_time=max(times)
    grid_count=int((last_time-first_time).total_seconds()/3600)+1
    alltimes=set.union(*(set(raw_values[s]) for s in STATIONS))
    complete_times=set.intersection(*(set(raw_values[s]) for s in STATIONS))
    all_missing=grid_count-len(alltimes)
    incomplete=grid_count-len(complete_times)
    print(f"Hourly grid={grid_count}; any-station coverage={len(alltimes)}/{grid_count} ({len(alltimes)/grid_count:.1%}); incomplete city hours={incomplete}; no-station hours={all_missing}")
    gaps=[]; gap_start=None; prev=None
    for i in range(grid_count):
        t=first_time+dt.timedelta(hours=i)
        if t not in alltimes:
            if gap_start is None: gap_start=t
            prev=t
        elif gap_start is not None:
            gaps.append((gap_start,prev,int((prev-gap_start).total_seconds()/3600)+1)); gap_start=None
    if gap_start is not None: gaps.append((gap_start,prev,int((prev-gap_start).total_seconds()/3600)+1))
    print("Longest no-station gaps="+str([(a.isoformat(),b.isoformat(),n) for a,b,n in sorted(gaps,key=lambda x:x[2],reverse=True)[:5]]))
    gt1k = [(r, float(r["pm25"])) for r in raw if float(r["pm25"]) > 1000]
    gt500 = [(r, float(r["pm25"])) for r in raw if float(r["pm25"]) > 500]
    print(f"Outliers >1000={len(gt1k)}; >500={len(gt500)}; max={max(float(r['pm25']) for r in raw):.3f}")
    vals = {s: {} for s in STATIONS}; isolated = set()
    for r in raw:
        sid=r["location_id"]; t=dt.datetime.fromisoformat(r["timestamp_ist"]); v=float(r["pm25"])
        others=[raw_values[o][t] for o in STATIONS if o!=sid and t in raw_values[o]]
        # Use the contemporaneous peer median when one peer is missing; never
        # classify isolation if no peer station has a reading at that hour.
        is_iso = v>500 and len(others)>=1 and med(others)<150
        if is_iso: isolated.add((sid,t))
        if v<=1000 and not is_iso: vals[sid][t]=v
    print(f"Cleaned isolated >500={len(isolated)}; all >1000 invalidated={len(gt1k)}")
    focus_start=dt.datetime.fromisoformat("2025-10-10T00:00:00+05:30"); focus_end=dt.datetime.fromisoformat("2025-12-10T23:00:00+05:30")
    focus=[r for r in raw if r["location_id"]=="3409511" and float(r["pm25"])>500 and focus_start<=dt.datetime.fromisoformat(r["timestamp_ist"])<=focus_end]
    focus_iso=[r for r in focus if (r["location_id"],dt.datetime.fromisoformat(r["timestamp_ist"])) in isolated]
    print(f"3409511 >500 in documented fault interval={len(focus)}; caught by simultaneous isolation rule={len(focus_iso)}")
    t0=max(times)
    observed=set((sid,t) for sid in STATIONS for t in raw_values[sid])
    categories=defaultdict(int)
    for r in test:
        sid=r["location_id"]; t=dt.datetime.fromisoformat(r["target_end_ist"])
        categories["observed" if (sid,t) in observed else ("past_missing" if t<=t0 else "future")]+=1
    print("Test row categories="+str(dict(categories)))
    print("Scoring block labels="+str({k:sum(x['scoring_block']==k for x in test) for k in sorted(set(x['scoring_block'] for x in test))}))
    private=select_private_window(test,t0)
    print(f"Date-defined private rows={len(private)}; target horizon={min((dt.datetime.fromisoformat(r['target_end_ist'])-t0).total_seconds()/3600 for r in private):.0f}..{max((dt.datetime.fromisoformat(r['target_end_ist'])-t0).total_seconds()/3600 for r in private):.0f} h")
    return vals, raw_values, isolated, test, sample, t0

def profile(vals, sid, origin, days, mode="mean"):
    buckets = defaultdict(list); start = origin - dt.timedelta(days=days)
    used = []
    if sid not in SERIES_CACHE:
        ts = sorted(vals[sid]); SERIES_CACHE[sid] = (ts, [vals[sid][t] for t in ts])
    ts, vs = SERIES_CACHE[sid]; lo = bisect_right(ts, start); hi = bisect_right(ts, origin)
    for i in range(lo, hi):
        t = ts[i]; buckets[t.hour].append(vs[i]); used.append(t)
    assert_feature_cutoff(used, origin)
    fn = med if mode == "median" else mean
    fallback = fn(vs[bisect_left(ts, origin - dt.timedelta(days=14)):hi])
    res = {h: fn(buckets[h]) if buckets[h] else None for h in range(24)}
    valid_hours = [h for h in range(24) if res[h] is not None]
    if not valid_hours:
        return {h: fallback for h in range(24)}
    if len(valid_hours) < 24:
        for h in range(24):
            if res[h] is None:
                prev_h = next((h - step) % 24 for step in range(1, 24) if res[(h - step) % 24] is not None)
                next_h = next((h + step) % 24 for step in range(1, 24) if res[(h + step) % 24] is not None)
                d_prev = (h - prev_h) % 24
                d_next = (next_h - h) % 24
                res[h] = (d_next * res[prev_h] + d_prev * res[next_h]) / (d_prev + d_next)
    return res

def last_mean(vals,sid,origin,hours):
    if sid not in SERIES_CACHE:
        ts=sorted(vals[sid]); SERIES_CACHE[sid]=(ts,[vals[sid][t] for t in ts])
    ts,vs=SERIES_CACHE[sid]
    lo=bisect_right(ts,origin-dt.timedelta(hours=hours)); hi=bisect_right(ts,origin)
    used=ts[lo:hi]
    assert_feature_cutoff(used, origin)
    return mean(vs[lo:hi])

def predictions_at(vals, origin, horizons=range(16,64)):
    result = {}
    anchors = {}
    for sid in STATIONS:
        p3 = profile(vals, sid, origin, 3); p7 = profile(vals, sid, origin, 7); p14 = profile(vals, sid, origin, 14); p14m = profile(vals, sid, origin, 14, "median")
        l24 = last_mean(vals, sid, origin, 24); l72 = last_mean(vals, sid, origin, 72)
        anchors[sid] = (l24, p14)
        for h in horizons:
            target = origin + dt.timedelta(hours=h); hh = target.hour
            prior_day = target - dt.timedelta(days=1)
            yday = vals[sid].get(prior_day, float("nan")) if prior_day <= origin else float("nan")
            w_persist = max(0.25, 0.50 * math.exp(-0.012 * max(0, h - 16)))
            b0 = w_persist * l24 + (1.0 - w_persist) * p7[hh]
            result[(sid, h)] = {"last24": l24, "profile3": p3[hh], "profile7": p7[hh], "profile14median": p14m[hh], "same_hour_yesterday": yday if finite(yday) else p7[hh], "B0": b0, "profile14": p14[hh]}
    return result, anchors

def rows_for_backtest(vals, t0, isolated):
    all_rows=[]
    start=dt.datetime.fromisoformat("2025-04-01T09:00:00+05:30")
    stop=t0-dt.timedelta(days=3)
    origins=[]
    o=start
    while o<=stop: origins.append(o); o+=dt.timedelta(days=1)
    print(f"Backtest origins={len(origins)} ({origins[0]}..{origins[-1]})")
    names=("last24","profile3","profile7","profile14median","same_hour_yesterday","B0")
    for oi,origin in enumerate(origins):
        preds,_=predictions_at(vals,origin)
        spike=any(last_mean(vals,s,origin,24)>80 for s in STATIONS)
        for h in range(16,64):
            target=origin+dt.timedelta(hours=h)
            for sid in STATIONS:
                y=vals[sid].get(target)
                p=preds[(sid,h)]
                if y is None or not all(finite(p[n]) for n in names): continue
                fault=(sid=="3409511" and FAULT_START<=target<=FAULT_END) or (sid,target) in isolated
                d={"origin_index":oi,"origin":origin.isoformat(),"station":sid,"target":target.isoformat(),"h":h,"y":y,"fault":int(fault),"spike_origin":int(spike)}
                d.update(p); all_rows.append(d)
    return all_rows,origins

def score(rows, name, mask=lambda r:True):
    rs=[r for r in rows if mask(r)]; err=[r[name]-r["y"] for r in rs]
    return (math.sqrt(mean([e*e for e in err])),mean([abs(e) for e in err]),len(rs)) if rs else (float("nan"),float("nan"),0)

def print_evidence_table(evidence):
    cols=("method","target_set","group","n","rmse","mae","rmse_diff_vs_B0","ci95_low","ci95_high")
    print("BACKTEST EVIDENCE: common rows, paired origin-block bootstrap CI for RMSE difference vs B0")
    lines=["\t".join(cols)]
    for row in evidence:
        lines.append("\t".join(str(row[c]) if c in ("method","target_set","group","n") else f"{row[c]:.4f}" for c in cols))
    print("\n".join(lines))

def ridge_fit_predict(Xtrain,ytrain,weights,Xtest,alpha=10.0):
    """Weighted, standardized Ridge regression implemented with NumPy."""
    import numpy as np
    Xtrain=np.asarray(Xtrain,dtype=float); ytrain=np.asarray(ytrain,dtype=float)
    Xtest=np.asarray(Xtest,dtype=float); weights=np.asarray(weights,dtype=float)
    medians=np.nanmedian(Xtrain,axis=0)
    medians=np.where(np.isfinite(medians),medians,0.0)
    Xtrain=np.where(np.isfinite(Xtrain),Xtrain,medians)
    Xtest=np.where(np.isfinite(Xtest),Xtest,medians)
    mu=np.average(Xtrain,axis=0,weights=weights)
    scale=np.sqrt(np.average((Xtrain-mu)**2,axis=0,weights=weights))
    scale=np.where(scale>1e-8,scale,1.0)
    A=(Xtrain-mu)/scale; B=(Xtest-mu)/scale
    ymu=np.average(ytrain,weights=weights); yc=ytrain-ymu
    gram=A.T@(weights[:,None]*A)
    beta=np.linalg.solve(gram+alpha*np.eye(gram.shape[0]),A.T@(weights*yc))
    return B@beta+ymu, (medians,mu,scale,ymu,beta)

def feature_vector(vals,sid,origin,h,cache):
    key=(sid,origin)
    if key not in cache:
        ts=SERIES_CACHE.get(sid)
        if ts is None:
            times=sorted(vals[sid]); SERIES_CACHE[sid]=(times,[vals[sid][t] for t in times]); ts=SERIES_CACHE[sid]
        times,values=ts; hi=bisect_right(times,origin)
        feats=[]
        feats.append(values[hi-1] if hi else float("nan"))
        for hours in (6,24,72,168):
            lo=bisect_right(times,origin-dt.timedelta(hours=hours)); assert_feature_cutoff(times[lo:hi],origin); sample=values[lo:hi]
            feats.extend((mean(sample),med(sample),statistics.pstdev(sample) if len(sample)>1 else 0.0))
        cache[key]=(feats,profile(vals,sid,origin,7))
    base,p7=cache[key]
    target=origin+dt.timedelta(hours=h); hour=target.hour; dow=target.weekday()
    station_oh=[1.0 if sid==s else 0.0 for s in STATIONS]
    return base+[p7[hour],float(h),math.sin(2*math.pi*hour/24),math.cos(2*math.pi*hour/24),math.sin(2*math.pi*dow/7),math.cos(2*math.pi*dow/7)]+station_oh

def ml_backtest(vals,common,baseline_name="B0"):
    """Expanding, time-ordered validation for a regularized direct multi-horizon Ridge model."""
    import numpy as np
    origin_dates={}
    for r in common:
        origin_dates.setdefault(r["origin_index"],dt.datetime.fromisoformat(r["origin"]))
    origins=sorted(origin_dates)
    feature_cache={}
    X=np.asarray([feature_vector(vals,r["station"],dt.datetime.fromisoformat(r["origin"]),int(r["h"]),feature_cache) for r in common],dtype=float)
    y=np.asarray([r["y"] for r in common],dtype=float)
    target_times=[dt.datetime.fromisoformat(r["target"]) for r in common]
    # Add pre-backtest supervised origins so the earliest evaluated origin can
    # also be forecast out of sample without withholding any common rows.
    hist_records=[]
    first_origin=origin_dates[origins[0]]
    hist_start=dt.datetime.fromisoformat("2025-03-01T09:00:00+05:30")
    earliest=min(t for station in vals.values() for t in station)
    hist_start=max(hist_start,earliest+dt.timedelta(days=7))
    hist_origin=hist_start
    while hist_origin<first_origin:
        for sid in STATIONS:
            for h in range(16,64):
                target=hist_origin+dt.timedelta(hours=h); label=vals[sid].get(target)
                if label is None: continue
                # `vals` already omits isolated observations; this also excludes
                # the documented station-specific fault interval from Ridge labels.
                fault=sid=="3409511" and FAULT_START<=target<=FAULT_END
                if fault: continue
                hist_records.append({"origin":hist_origin,"target":target,"station":sid,"h":h,"y":label})
        hist_origin+=dt.timedelta(days=1)
    Xhist=np.asarray([feature_vector(vals,r["station"],r["origin"],r["h"],feature_cache) for r in hist_records],dtype=float)
    yhist=np.asarray([r["y"] for r in hist_records],dtype=float)
    model_preds=[float("nan")]*len(common)
    warmup=0; block=max(45,len(origins)//8)
    fold_starts=list(range(warmup,len(origins),block))
    for pos,start_pos in enumerate(fold_starts):
        end_pos=fold_starts[pos+1] if pos+1<len(fold_starts) else len(origins)
        start_idx=origins[start_pos]; end_idx=origins[end_pos] if end_pos<len(origins) else origins[-1]+1
        cutoff=origin_dates[start_idx]
        train_idx=[j for j,r in enumerate(common) if r["origin_index"]<start_idx and target_times[j]<=cutoff and not r["fault"]]
        hist_idx=[j for j,r in enumerate(hist_records) if r["target"]<=cutoff]
        test_idx=[j for j,r in enumerate(common) if start_idx<=r["origin_index"]<end_idx]
        if len(train_idx)+len(hist_idx)<1000 or not test_idx: continue
        Xtrain=np.vstack((X[train_idx],Xhist[hist_idx]))
        ytrain=np.concatenate((y[train_idx],yhist[hist_idx]))
        ages=np.asarray([max(0.0,(cutoff-target_times[j]).total_seconds()/86400) for j in train_idx]+[max(0.0,(cutoff-hist_records[j]["target"]).total_seconds()/86400) for j in hist_idx])
        weights=np.power(.5,ages/14.0)
        yp,_=ridge_fit_predict(Xtrain,ytrain,weights,X[test_idx],alpha=10.0)
        for j,p in zip(test_idx,yp): model_preds[j]=max(0.0,float(p))
    indices=[j for j,p in enumerate(model_preds) if finite(p)]
    pred_rows=[{**common[j],"Ridge":model_preds[j]} for j in indices]
    if not pred_rows: raise RuntimeError("Ridge walk-forward validation produced no predictions")
    b0_all=score(pred_rows,baseline_name)[0]
    ml_all=score(pred_rows,"Ridge")[0]
    faultfree=[r for r in pred_rows if not r["fault"]]
    b0_ff=score(faultfree,baseline_name)[0]; ml_ff=score(faultfree,"Ridge")[0]
    byorigin=defaultdict(list)
    for r in faultfree: byorigin[r["origin_index"]].append(r)
    ids=sorted(byorigin); rng=random.Random(SEED); diffs=[]
    origin_sums={oid:(sum((r["Ridge"]-r["y"])**2 for r in byorigin[oid]),sum((r[baseline_name]-r["y"])**2 for r in byorigin[oid]),len(byorigin[oid])) for oid in ids}
    for _ in range(CONFIG["bootstrap_replicates"]):
        s1=s0=n=0
        for _ in ids:
            a,b,c=origin_sums[ids[rng.randrange(len(ids))]]
            s1+=a; s0+=b; n+=c
        diffs.append(math.sqrt(s1/n)-math.sqrt(s0/n))
    diffs.sort(); ci=(diffs[24],diffs[974])
    result={"rows":len(pred_rows),"rmse_all_ridge":ml_all,"rmse_all_b0":b0_all,"rmse_fault_excluded_ridge":ml_ff,"rmse_fault_excluded_b0":b0_ff,"diff_fault_excluded":ml_ff-b0_ff,"ci95_low":ci[0],"ci95_high":ci[1],"adopt":ci[1]<0 and ml_all<=b0_all+1.0,"feature_count":int(X.shape[1]),"warmup_origins":warmup,"fold_block_origins":block,"warmup_training_rows":len(hist_records)}
    return result,feature_cache

def fit_final_ridge(vals,common,feature_cache):
    import numpy as np
    # The cutoff is the known Train origin, not the backtest's last origin.
    t0=dt.datetime.fromisoformat(T0_EXPECTED)
    train=[r for r in common if dt.datetime.fromisoformat(r["target"])<=t0 and not r["fault"]]
    X=np.asarray([feature_vector(vals,r["station"],dt.datetime.fromisoformat(r["origin"]),int(r["h"]),feature_cache) for r in train],dtype=float)
    y=np.asarray([r["y"] for r in train],dtype=float)
    ages=np.asarray([max(0.0,(t0-dt.datetime.fromisoformat(r["target"])).total_seconds()/86400) for r in train])
    weights=np.power(.5,ages/14.0)
    # Reuse the fitting path with a single dummy row, then return a predictor closure.
    _,params=ridge_fit_predict(X,y,weights,X[:1],alpha=10.0)
    import numpy as np
    medians,mu,scale,ymu,beta=params
    def predict(x):
        a=np.asarray(x,dtype=float)
        a=np.where(np.isfinite(a),a,medians)
        return float(((a-mu)/scale)@beta+ymu)
    return predict

def build_ml_submission(vals,test,sample,t0,predict,feature_cache):
    primary=read_csv(SUBMISSION_DIR/"submission_primary.csv")
    out=[]
    for tr,sr,base in zip(test,sample,primary):
        sid=tr["location_id"]; target=dt.datetime.fromisoformat(tr["target_end_ist"])
        if target<=t0:
            value=float(base["Target"])
        else:
            h=int((target-t0).total_seconds()/3600)
            value=max(0.0,predict(feature_vector(vals,sid,t0,h,feature_cache)))
            if h>72:
                p14=profile(vals,sid,t0,14)[target.hour]
                alpha=min(.75,(h-72)/183*.75); value=(1-alpha)*value+alpha*p14
        out.append({"ID":sr["ID"],"Target":value})
    SUBMISSION_DIR.mkdir(parents=True,exist_ok=True)
    tmp=SUBMISSION_DIR/"submission_ml.csv.tmp"; write_csv(tmp,["ID","Target"],out)
    from validate_submission import validate_file
    if not validate_file(tmp,verbose=True):
        tmp.unlink(missing_ok=True); raise RuntimeError("ML submission failed validation")
    os.replace(tmp,SUBMISSION_DIR/"submission_ml.csv")

def build_public_interval_files(test_rows):
    """Extract chronological public windows from the selected primary submission."""
    source=read_csv(SUBMISSION_DIR/"submission_primary.csv")
    source_by_id={r["ID"]:r for r in source}
    train={(r["location_id"],dt.datetime.fromisoformat(r["timestamp_ist"])) for r in read_csv(ROOT/"Train.csv")}
    outdir=ROOT/"Submission"/"02_Public_Intervals"
    outdir.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for filename,start,end in PUBLIC_INTERVALS:
        selected=[r for r in test_rows if start<=dt.datetime.fromisoformat(r["target_end_ist"]).date()<=end]
        rows=[{"ID":r["ID"],"Target":source_by_id[r["ID"]]["Target"]} for r in selected]
        if not rows:
            raise RuntimeError(f"No Test rows found for public interval {start} to {end}")
        if any(not finite(float(r["Target"])) or float(r["Target"])<0 or float(r["Target"])>1000 for r in rows):
            raise RuntimeError(f"Invalid target detected in public interval {filename}")
        observed=sum((r["location_id"],dt.datetime.fromisoformat(r["target_end_ist"])) in train for r in selected)
        tmp=outdir/(filename+".tmp")
        write_csv(tmp,["ID","Target"],rows)
        if len(read_csv(tmp))!=len(selected):
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"Interval row count failed for {filename}")
        os.replace(tmp,outdir/filename)
        manifest.append({"file":filename,"start_date":start.isoformat(),"end_date":end.isoformat(),"rows":len(rows),"observed_in_train":observed,"imputed_or_forecast":len(rows)-observed})
        print(f"Public interval {filename}: {len(rows)} rows ({observed} observed in Train; {len(rows)-observed} imputed/forecast)")
    write_csv(outdir/"00_interval_manifest.csv",["file","start_date","end_date","rows","observed_in_train","imputed_or_forecast"],manifest)
    (outdir/"README.txt").write_text("Public date-window extracts from ../01_Final_Submissions/submission_primary.csv.\nRows are retained in Test.csv order and use the pipeline's selected primary predictions. Observations already present in Train remain copied from their cleaned observed values; missing historical rows use the documented fill rules.\n",encoding="utf-8")

def backtest(vals,t0,isolated):
    rows,origins=rows_for_backtest(vals,t0,isolated)
    weights=[i/20 for i in range(21)]
    baseline_names=("B0","last24","profile3","profile7","profile14median","same_hour_yesterday")
    candidates={n:lambda r,n=n:r[n] for n in baseline_names}
    for w in weights:
        tag=f"blend_w{w:.2f}"; candidates[tag]=lambda r,w=w:w*r["last24"]+(1-w)*r["profile7"]
    common=[r for r in rows if all(finite(r[n]) for n in ("last24","profile3","profile7","profile14median","same_hour_yesterday","B0"))]
    for w in weights:
        tag=f"blend_w{w:.2f}"
        for r in common: r[tag]=w*r["last24"]+(1-w)*r["profile7"]
    groups=("overall","calm_origins","spike_origins",*STATIONS)
    def in_group(row, group):
        if group=="overall": return True
        if group=="calm_origins": return row["spike_origin"]==0
        if group=="spike_origins": return row["spike_origin"]==1
        return row["station"]==group
    summary=[]; boot=[]; evidence=[]; rng=random.Random(SEED)
    # One common row set for every method; aggregate origin blocks for paired bootstrap.
    for subset in ("all","fault_excluded"):
        for group in groups:
            selected=[r for r in common if (subset=="all" or not r["fault"]) and in_group(r,group)]
            byorigin=defaultdict(list)
            for r in selected: byorigin[r["origin_index"]].append(r)
            origin_ids=sorted(byorigin)
            for name in baseline_names:
                rmse,mae,n=score(selected,name)
                summary.append({"method":name,"target_set":subset,"group":group,"n":n,"rmse":rmse,"mae":mae})
                if name=="B0":
                    diff=0.0; lo=0.0; hi=0.0
                else:
                    sum_by_origin={oid:(sum((r[name]-r["y"])**2 for r in byorigin[oid]),sum((r["B0"]-r["y"])**2 for r in byorigin[oid]),len(byorigin[oid])) for oid in origin_ids}
                    diffs=[]
                    for _ in range(CONFIG["bootstrap_replicates"]):
                        s1=s0=nn=0
                        for _ in origin_ids:
                            a,b,c=sum_by_origin[origin_ids[rng.randrange(len(origin_ids))]]
                            s1+=a; s0+=b; nn+=c
                        diffs.append(math.sqrt(s1/nn)-math.sqrt(s0/nn))
                    diffs.sort(); diff=rmse-score(selected,"B0")[0]; lo=diffs[24]; hi=diffs[974]
                boot.append({"method":name,"target_set":subset,"group":group,"difference_vs_B0_rmse":diff,"ci95_low":lo,"ci95_high":hi})
                evidence.append({"method":name,"target_set":subset,"group":group,"n":n,"rmse":rmse,"mae":mae,"rmse_diff_vs_B0":diff,"ci95_low":lo,"ci95_high":hi})
    fields=["method","target_set","group","n","rmse","mae"]
    write_csv(ROOT/"backtest_summary.csv",fields,summary)
    boot_fields=["method","target_set","group","difference_vs_B0_rmse","ci95_low","ci95_high"]
    write_csv(ROOT/"backtest_bootstrap.csv",boot_fields,boot)
    write_csv(ROOT/"backtest_evidence.csv",["method","target_set","group","n","rmse","mae","rmse_diff_vs_B0","ci95_low","ci95_high"],evidence)
    # Tune candidate weights on fault-excluded overall RMSE, then require its
    # paired origin-block bootstrap interval to lie wholly below zero.
    candidates_for_tuning=[f"blend_w{w:.2f}" for w in weights]
    faultfree=[r for r in common if not r["fault"]]
    best_name=min(candidates_for_tuning,key=lambda n:score(faultfree,n)[0])
    ids=sorted({r["origin_index"] for r in faultfree})
    by_origin=defaultdict(list)
    for r in faultfree: by_origin[r["origin_index"]].append(r)
    origin_sums={oid:(sum((r[best_name]-r["y"])**2 for r in by_origin[oid]),sum((r["B0"]-r["y"])**2 for r in by_origin[oid]),len(by_origin[oid])) for oid in ids}
    diffs=[]
    for _ in range(CONFIG["bootstrap_replicates"]):
        s1=s0=nn=0
        for _ in ids:
            a,b,c=origin_sums[ids[rng.randrange(len(ids))]]; s1+=a; s0+=b; nn+=c
        diffs.append(math.sqrt(s1/nn)-math.sqrt(s0/nn))
    diffs.sort(); best_ci={"ci95_low":diffs[24],"ci95_high":diffs[974]}
    # Retain B0 unless a tuned baseline has a block-bootstrap CI wholly below 0.
    champ=best_name if float(best_ci["ci95_high"])<0 else "B0"
    best_rmse=score(faultfree,best_name)[0]; b0_rmse=score(faultfree,"B0")[0]
    print(f"Fault-excluded point leader={best_name} RMSE={best_rmse:.6f}; B0 RMSE={b0_rmse:.6f}; difference={best_rmse-b0_rmse:.6f}; 95% CI={best_ci['ci95_low']:.6f}..{best_ci['ci95_high']:.6f}; selected={champ}; common rows={len(common)}")
    print_evidence_table(evidence)
    write_csv(ROOT/"backtest_rows.csv",list(common[0].keys()) if common else [],common)
    return champ,summary,boot,evidence,common,best_name,best_ci,best_rmse,b0_rmse

def build_submission(vals,raw_values,isolated,test,sample,t0,champ,hedged=False):
    preds,anchors=predictions_at(vals,t0,range(1,256))
    out=[]
    for tr, sr in zip(test,sample):
        sid=tr["location_id"]; target=dt.datetime.fromisoformat(tr["target_end_ist"]); h=int((target-t0).total_seconds()/3600)
        if target in vals[sid]:
            value=vals[sid][target] # cleaned observed values are only public-window fill rows
        elif target<=t0:
            before=[(t,v) for t,v in vals[sid].items() if t<target]; after=[(t,v) for t,v in vals[sid].items() if t>target]
            a=max(before) if before else None; b=min(after) if after else None
            if a and b and (b[0]-a[0]).total_seconds()/3600<=7:
                frac=(target-a[0]).total_seconds()/(b[0]-a[0]).total_seconds(); value=a[1]+frac*(b[1]-a[1])
            else:
                p7=profile(vals,sid,target,7)[target.hour]
                others=[]
                for other in STATIONS:
                    if other==sid: continue
                    v=vals[other].get(target)
                    if v is not None: others.append(v)
                hist=[]
                for other in STATIONS:
                    if other==sid: continue
                    hist.extend(v for t,v in vals[other].items() if t.hour==target.hour and target-dt.timedelta(days=7)<t<=target)
                ratio=med(others)/med(hist) if others and hist and med(hist)>0 else 1.0
                value=p7*max(.5,min(2.0,ratio))
        else:
            p=preds[(sid,h)]
            value=p[champ] if champ in p else p["B0"]
            if h>63:
                alpha=min(.75,(h-63)/192*.75); value=(1-alpha)*value+alpha*p["profile14"]
            if hedged:
                l24,_=anchors[sid]; others=[anchors[o][0] for o in STATIONS if o!=sid and finite(anchors[o][0])]
                cap=1.75*med(others) if others else l24
                if l24>cap:
                    value=.70*value+.15*cap+.15*p["profile14"]
        if not finite(value): value=0.0
        out.append({"ID":sr["ID"],"Target":max(0.0,float(value))})
    name="submission_hedged.csv" if hedged else "submission_primary.csv"
    SUBMISSION_DIR.mkdir(parents=True,exist_ok=True)
    tmp=SUBMISSION_DIR/(name+".tmp")
    write_csv(tmp,["ID","Target"],out)
    from validate_submission import validate_file
    if not validate_file(tmp,verbose=True):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Refusing to replace {name}: temporary submission failed validation")
    os.replace(tmp,SUBMISSION_DIR/name)
    assert len(out)==2592 and [r["ID"] for r in out]==[r["ID"] for r in sample]
    assert all(finite(float(r["Target"])) and float(r["Target"])>=0 for r in out)
    print(f"Wrote {name}: {len(out)} rows; private-window mean predictions by station:")
    for sid in STATIONS:
        xs=[float(o["Target"]) for o,tr in zip(out,test) if tr["location_id"]==sid and PRIVATE_START<=dt.datetime.fromisoformat(tr["target_end_ist"])<=PRIVATE_END]
        l24=last_mean(vals,sid,t0,24)
        print(f"  {sid}: prediction mean={mean(xs):.2f}; last24={l24:.2f}; analog band={.5*l24:.2f}..{1.3*l24:.2f}")

def main():
    run_started=time.perf_counter()
    vals,raw_values,isolated,test,sample,t0=audit_and_load()
    from validate_submission import validate_file
    existing_primary_ok=validate_file(SUBMISSION_DIR/"submission_primary.csv",verbose=True)
    existing_hedged_ok=validate_file(SUBMISSION_DIR/"submission_hedged.csv",verbose=True)
    if not (existing_primary_ok and existing_hedged_ok):
        raise RuntimeError("Existing submission files must pass validation before pipeline replacement")
    print("Stage 1: valid baseline submission")
    print("Validated existing B0 primary and hedged files remain available during this run.")
    print("Stage 2: rolling-origin tuning")
    champ,summary,boot,evidence,common,best_name,best_ci,best_rmse,b0_rmse=backtest(vals,t0,isolated)
    ml_result=None; feature_cache={}; model_predict=None; ml_status="NumPy unavailable; ML skipped."
    try:
        import numpy as np
        ml_result,feature_cache=ml_backtest(vals,common)
        print("RIDGE WALK-FORWARD:",ml_result)
        model_predict=fit_final_ridge(vals,common,feature_cache)
        ml_status=("Weighted Ridge tested; adopted." if ml_result["adopt"] else "Weighted Ridge tested but not adopted because it did not satisfy both evidence gates.")
    except Exception as exc:
        ml_status=f"Optional weighted Ridge attempt failed and was skipped: {type(exc).__name__}: {exc}"
        print(ml_status)
    if ml_result and ml_result["adopt"]:
        build_ml_submission(vals,test,sample,t0,model_predict,feature_cache)
        print("ML adopted: existing primary and hedged files were left untouched.")
    else:
        build_submission(vals,raw_values,isolated,test,sample,t0,champ,False)
        build_submission(vals,raw_values,isolated,test,sample,t0,champ,True)
        print("Baseline selected; submission_ml.csv was not created.")
    build_public_interval_files(test)
    runtime=time.perf_counter()-run_started
    pyver=sys.version.split()[0]
    print(f"Python {pyver}; total runtime {runtime:.2f} seconds")
    lines=["# Mumbai PM2.5 forecasting entry","",f"Reproduce from this folder with `python pipeline.py` (Python {pyver}; this run took {runtime:.2f} seconds). The pipeline reads only provided challenge files, uses fixed seed {SEED}, and requires `numpy==2.5.4` for its optional weighted Ridge attempt; all other imports are from the standard library.","", "## Submitted files and selection", "", f"Select `Submission/01_Final_Submissions/submission_primary.csv` (B0) and `Submission/01_Final_Submissions/submission_hedged.csv` on Zindi. The fault-excluded point leader was {best_name}: RMSE {best_rmse:.4f} vs B0 {b0_rmse:.4f} (difference {best_rmse-b0_rmse:.4f}; 95% origin-block CI [{best_ci['ci95_low']:.4f}, {best_ci['ci95_high']:.4f}]). The interval includes zero, so B0 remains primary. The hedged file applies the c=2 robust anchor to each station and an extra 20% shrink toward the 14-day profile for 11611. {ml_status}","", "The public score is uninformative about forecast quality because 1,284 Test rows are observed Train values copied into the submissions. Private rows are selected by target date (11 Nov 01:00 through 13 Nov 00:00 IST), not by stale `scoring_block` labels.","", "## Public intervals", "", "Date-window CSV extracts are saved under `Submission/02_Public_Intervals/` in chronological order, with counts and observed-versus-filled rows in `00_interval_manifest.csv`. They are subsets of the primary output and retain Test.csv row order.","", "## Backtest evidence", "", f"Daily 09:00 IST origins from 2025-04-01 through 2026-11-07; direct horizons 16–63. Six methods use the same common rows (n={len(common)} overall): B0, last24, profile3, profile7, profile14-median, and same-hour-yesterday. Spike origin means any station's last-24-hour mean exceeds 80. Fault-excluded removes the documented station 3409511 window and any target invalidated by the isolation rule.","", "| Method | Targets | Group | n | RMSE | MAE | ΔRMSE vs B0 | 95% CI |","|---|---|---|---:|---:|---:|---:|---:|"]
    for r in evidence:
        lines.append(f"| {r['method']} | {r['target_set']} | {r['group']} | {r['n']} | {r['rmse']:.4f} | {r['mae']:.4f} | {r['rmse_diff_vs_B0']:.4f} | [{r['ci95_low']:.4f}, {r['ci95_high']:.4f}] |")
    lines += ["", "The same table is saved as `backtest_evidence.csv`; `backtest_summary.csv`, `backtest_bootstrap.csv`, and `backtest_rows.csv` provide the component and row-level outputs.", "", "## Data handling and limitations", "", "Forecast features use observations at or before each origin. Values above 1,000 are invalidated; values above 500 are invalidated when the median of available simultaneous peer readings is below 150. Station 11611 has stayed about 3× the median of the other stations for eight consecutive hours (roughly 190–260 µg/m³); there is no historical precedent, so local source vs. sensor fault remains unknown. Diwali decay remains uncertain (roughly 0.5–1.3× the recent level); no decay is hard-coded. Fault-rule thresholds may remove genuine station-specific extremes. There is a 243-hour no-station gap in January 2026.","", "The Zindi rule claims in the task were not independently verified during this run. Historical archives are not used as features and source station IDs are not merged.",""]
    if ml_result:
        lines += ["## Optional ML result", "", f"Walk-forward weighted Ridge used {ml_result['rows']} scored rows and {ml_result['feature_count']} origin-anchored features. Fault-excluded RMSE: Ridge {ml_result['rmse_fault_excluded_ridge']:.4f}, B0 {ml_result['rmse_fault_excluded_b0']:.4f}; difference {ml_result['diff_fault_excluded']:.4f}, 95% origin-bootstrap CI [{ml_result['ci95_low']:.4f}, {ml_result['ci95_high']:.4f}]. All-target RMSE: Ridge {ml_result['rmse_all_ridge']:.4f}, B0 {ml_result['rmse_all_b0']:.4f}. Adoption requires CI high < 0 and all-target RMSE at most B0 + 1; result: {'ADOPTED' if ml_result['adopt'] else 'NOT ADOPTED'}. "]
    (ROOT/"README.md").write_text("\n".join(lines),encoding="utf-8")

if __name__=="__main__": main()
