#!/usr/bin/env python3
"""
options_analysis.py  -  World Cup attention effect in SPY options.
Completed tournaments only: 2014 (taq only), 2018, 2022.

Reads raw AlgoSeek files pulled by ingest/pull_options.py into
  data/market/options/raw/{taq,greeks}/...
builds per-minute (taq) and per-day (greeks) panels, runs the Match regressions,
writes tidy parquets to data/market/options/ and a result table to analysis/out/options.csv.

TEST 1 (intraday, primary  -  fits the panel design):
  From 1min-taq, per-minute SPY total option Volume (call+put) and put/call volume
  ratio, restricted to US regular trading hours (ET 09:30-16:00). Regress
  log(option volume) and the put/call ratio on Match (any WC match in progress,
  [kickoff, kickoff+105min) in UTC), FE = weekday x minute-of-day + date,
  SE clustered by date. Years 2014/2018/2022.

TEST 2 (day-level, secondary  -  weaker, EOD resolution):
  From daily-greeks, per trade-date: ATM IV (|delta| nearest 0.50 interp), 25-delta
  call IV, 25-delta put IV, and 25-delta skew = put25 - call25, on the front expiry
  >= 20 DTE with the most converged contracts. Regress on a Match-day dummy (a WC
  match occurred that ET trade-date, optionally weighted by US-hours overlap),
  controlling for day-of-week, comparing match-days vs non-match weekdays in window.
  Years 2018/2022 only (no daily-greeks bucket before 2017). Lower power: one obs/day,
  weekend match-days have no trading (dropped), few treated date-clusters -> flagged.

No look-ahead: outcomes are contemporaneous market quantities; the Match indicator is
built from kickoff times only. SEs clustered by date. Nulls reported as nulls with
effect sizes and N.
"""
import os, sys, glob, gzip, csv, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np, pandas as pd
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.join(ROOT, "data", "market", "options", "raw")
MDIR = os.path.join(ROOT, "data", "matches")
OUTDATA = os.path.join(ROOT, "data", "market", "options")
OUTCSV = os.path.join(ROOT, "analysis", "out", "options.csv")
os.makedirs(OUTDATA, exist_ok=True)

from pyfixest.estimation import feols


# --------------------------------------------------------------------------- #
# Match spine: in-progress minutes (UTC) and per-day match metadata
# --------------------------------------------------------------------------- #
def match_spine():
    ma = pd.read_parquet(os.path.join(MDIR, "matches_all.parquet"))
    mh = pd.read_parquet(os.path.join(MDIR, "matches_hist.parquet"))
    a = ma[ma["tournament"].isin([2018, 2022])][["tournament", "kickoff_utc", "played"]].copy()
    h = mh[mh["tournament"] == 2014][["tournament", "kickoff_utc", "played"]].copy()
    m = pd.concat([h, a], ignore_index=True)
    m = m[m["played"] != False].copy()
    m["ko"] = pd.to_datetime(m["kickoff_utc"], utc=True)
    return m


def inmatch_minutes(m):
    """Set of UTC minute Timestamps with any WC match in progress [ko, ko+105m)."""
    s = set()
    for ko in m["ko"]:
        s.update(pd.date_range(ko, ko + pd.Timedelta(minutes=104), freq="1min"))
    return s


def match_day_meta(m):
    """Per ET trade-date: was there a match, and US-RTH overlap minutes (weighting)."""
    et = m["ko"].dt.tz_convert("America/New_York")
    rows = []
    for ko in m["ko"]:
        mins = pd.date_range(ko, ko + pd.Timedelta(minutes=104), freq="1min").tz_convert("America/New_York")
        mod = mins.hour * 60 + mins.minute
        rth = int(((mod >= 570) & (mod < 960)).sum())
        rows.append((mins[0].strftime("%Y-%m-%d"), rth))
    df = pd.DataFrame(rows, columns=["date", "rth_overlap"])
    return df.groupby("date", as_index=False)["rth_overlap"].max()


# --------------------------------------------------------------------------- #
# TEST 1  -  intraday option volume (1min-taq)
# --------------------------------------------------------------------------- #
def build_taq_panel(inmatch):
    """Per (trade_date, minute) SPY total option volume + put/call vol, summed across
    all pulled expiry files. RTH only. Match flag from in-progress UTC minutes."""
    rows = defaultdict(lambda: [0.0, 0.0])   # (date,tbar) -> [callvol, putvol]
    for t in (2014, 2018, 2022):
        for f in sorted(glob.glob(os.path.join(RAW, "taq", str(t), "*", "SPY.*.csv.gz"))):
            with gzip.open(f, "rt") as fh:
                rd = csv.reader(fh)
                header = next(rd)
                ci = {h: i for i, h in enumerate(header)}
                iD, iT, iCP, iV = ci["Date"], ci["TimeBarStart"], ci["CallPut"], ci["Volume"]
                for r in rd:
                    v = r[iV]
                    if not v or v == "0":
                        continue
                    key = (r[iD], r[iT])
                    vv = float(v)
                    if r[iCP] == "C":
                        rows[key][0] += vv
                    elif r[iCP] == "P":
                        rows[key][1] += vv
    recs = []
    for (d, tbar), (cv, pv) in rows.items():
        # TimeBarStart is "HH:MM" ET local clock; build UTC minute via ET tz
        ts_et = pd.Timestamp(f"{d[:4]}-{d[4:6]}-{d[6:8]} {tbar}", tz="America/New_York")
        recs.append((d, ts_et, cv, pv))
    df = pd.DataFrame(recs, columns=["date_ymd", "ts_et", "callvol", "putvol"])
    df["ts"] = df["ts_et"].dt.tz_convert("UTC")
    # RTH filter
    mod_et = df["ts_et"].dt.hour * 60 + df["ts_et"].dt.minute
    df = df[(mod_et >= 570) & (mod_et < 960)].copy()
    df["totvol"] = df["callvol"] + df["putvol"]
    df = df[df["totvol"] > 0].copy()
    df["lvol"] = np.log(df["totvol"])
    df["pcr"] = df["putvol"] / df["callvol"].where(df["callvol"] > 0)
    df["lpcr"] = np.log(df["pcr"].where(df["pcr"] > 0))
    df["match"] = df["ts"].isin(inmatch).astype(int)
    df["date"] = df["ts_et"].dt.strftime("%Y-%m-%d")
    df["weekday"] = df["ts_et"].dt.weekday
    df["minute_of_day"] = mod_et[df.index]
    df["wd_mod"] = df["weekday"].astype(str) + "_" + df["minute_of_day"].astype(str)
    df["year"] = df["ts_et"].dt.year
    return df.sort_values("ts").reset_index(drop=True)


def reg_minute(df, y):
    sub = df.dropna(subset=[y]); sub = sub[np.isfinite(sub[y])]
    m = feols(f"{y} ~ match | wd_mod + date", data=sub, vcov={"CRV1": "date"})
    r = m.tidy().loc["match"]
    return dict(coef=r["Estimate"], se=r["Std. Error"], p=r["Pr(>|t|)"], n=int(m._N),
                treated_dates=int(sub.loc[sub.match == 1, "date"].nunique()),
                total_dates=int(sub["date"].nunique()))


# --------------------------------------------------------------------------- #
# TEST 2  -  day-level IV / skew (daily-greeks)
# --------------------------------------------------------------------------- #
def _interp_iv(rows, callput, target_delta):
    pts = sorted((float(r["MidDelta"]), float(r["MidImpliedVol"])) for r in rows
                 if r["CallPut"] == callput and r["ImpliedVolConvergence"] == "Converged"
                 and r["MidImpliedVol"] not in ("", "0") and r["MidDelta"] not in ("",))
    if len(pts) < 2:
        return None
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        lo, hi = min(d0, d1), max(d0, d1)
        if lo <= target_delta <= hi and d1 != d0:
            return v0 + (v1 - v0) * (target_delta - d0) / (d1 - d0)
    return None


def build_greeks_panel():
    recs = []
    for t in (2018, 2022):
        for f in sorted(glob.glob(os.path.join(RAW, "greeks", str(t), "SPY.*.csv.gz"))):
            with gzip.open(f, "rt") as fh:
                rows = list(csv.DictReader(fh))
            if not rows:
                continue
            day = rows[0]["TradeDate"]
            byexp = defaultdict(list)
            for r in rows:
                byexp[r["Expiration"]].append(r)
            cand = [(e, rs) for e, rs in byexp.items()
                    if rs and rs[0].get("DaysToMaturity") and int(float(rs[0]["DaysToMaturity"])) >= 20]
            if not cand:
                continue
            cand.sort(key=lambda kv: -sum(1 for r in kv[1] if r["ImpliedVolConvergence"] == "Converged"))
            exp, ers = cand[0]
            atm = _interp_iv(ers, "C", 0.50)
            c25 = _interp_iv(ers, "C", 0.25)
            p25 = _interp_iv(ers, "P", -0.25)
            skew = (p25 - c25) if (p25 is not None and c25 is not None) else None
            recs.append(dict(tournament=t, date=f"{day[:4]}-{day[4:6]}-{day[6:8]}", expiry=exp,
                             dte=int(float(ers[0]["DaysToMaturity"])),
                             atm_iv=atm, call25_iv=c25, put25_iv=p25, skew=skew))
    return pd.DataFrame(recs)


def reg_day(df, y, mday_meta):
    d = df.copy()
    d["dt"] = pd.to_datetime(d["date"])
    d["weekday"] = d["dt"].dt.weekday
    d["dow"] = d["weekday"].astype(str)
    d["year"] = d["dt"].dt.year.astype(str)
    mset = set(mday_meta["date"])
    ov = dict(zip(mday_meta["date"], mday_meta["rth_overlap"]))
    d["match_day"] = d["date"].isin(mset).astype(int)
    d["match_overlap"] = d["date"].map(ov).fillna(0) / 105.0  # fraction of a match in RTH
    sub = d.dropna(subset=[y]); sub = sub[np.isfinite(sub[y])]
    out = {}
    # unweighted dummy with day-of-week + year FE
    m = feols(f"{y} ~ match_day | dow + year", data=sub, vcov={"CRV1": "date"})
    r = m.tidy().loc["match_day"]
    out["dummy"] = dict(coef=r["Estimate"], se=r["Std. Error"], p=r["Pr(>|t|)"], n=int(m._N),
                        treated=int(sub.match_day.sum()))
    # US-hours-overlap-weighted treatment intensity. NOTE: for 2018/2022 every weekday
    # match-day has at least one match fully inside RTH, so max-overlap saturates at 105min
    # for all treated days and this collapses to the dummy -> we only keep the dummy.
    if sub["match_overlap"].gt(0).sum() >= 2 and sub["match_overlap"].nunique() > 2:
        m2 = feols(f"{y} ~ match_overlap | dow + year", data=sub, vcov={"CRV1": "date"})
        r2 = m2.tidy().loc["match_overlap"]
        out["overlap"] = dict(coef=r2["Estimate"], se=r2["Std. Error"], p=r2["Pr(>|t|)"], n=int(m2._N),
                              treated=int(sub.match_overlap.gt(0).sum()))
    return out


# --------------------------------------------------------------------------- #
def main():
    m = match_spine()
    inmatch = inmatch_minutes(m)
    mday = match_day_meta(m)

    results = []

    # ---- TEST 1: intraday volume ----
    taq = build_taq_panel(inmatch)
    taq.to_parquet(os.path.join(OUTDATA, "taq_minute_panel.parquet"), index=False)
    print(f"[taq] {len(taq):,} RTH minute-rows, {taq['date'].nunique()} trade-dates, "
          f"{taq.loc[taq.match==1,'date'].nunique()} with in-RTH match minutes, "
          f"{int(taq['match'].sum()):,} treated minute-rows")
    for y, lbl in [("lvol", "log(option volume)"), ("pcr", "put/call vol ratio"),
                   ("lpcr", "log(put/call ratio)")]:
        s = reg_minute(taq, y)
        results.append(dict(test="intraday (1min-taq, 2014/18/22)", outcome=lbl,
                            **{k: s[k] for k in ("coef", "se", "p", "n")},
                            treated_clusters=s["treated_dates"], total_clusters=s["total_dates"]))
    # per-year fragility on log volume
    for yr in (2014, 2018, 2022):
        sub = taq[taq["year"] == yr]
        if sub["match"].sum() == 0:
            continue
        s = reg_minute(sub, "lvol")
        results.append(dict(test=f"intraday lvol {yr}-only", outcome="log(option volume)",
                            **{k: s[k] for k in ("coef", "se", "p", "n")},
                            treated_clusters=s["treated_dates"], total_clusters=s["total_dates"]))

    # ---- TEST 2: day-level IV/skew ----
    gk = build_greeks_panel()
    gk.to_parquet(os.path.join(OUTDATA, "greeks_daily_panel.parquet"), index=False)
    print(f"[greeks] {len(gk)} trading-days, "
          f"{gk['date'].isin(set(mday['date'])).sum()} are match-days (weekday w/ trading)")
    for y, lbl in [("atm_iv", "ATM IV"), ("skew", "25d skew (put-call)"),
                   ("put25_iv", "25d put IV"), ("call25_iv", "25d call IV")]:
        d = reg_day(gk, y, mday)
        results.append(dict(test="day-level (daily-greeks, 2018/22)", outcome=lbl + " [dummy]",
                            **d["dummy"], treated_clusters=d["dummy"]["treated"],
                            total_clusters=int(gk[y].notna().sum())))
        if "overlap" in d:
            o = d["overlap"]
            results.append(dict(test="day-level (daily-greeks, 2018/22)", outcome=lbl + " [overlap-wt]",
                                **{k: o[k] for k in ("coef", "se", "p", "n")},
                                treated_clusters=o["treated"], total_clusters=int(gk[y].notna().sum())))

    res = pd.DataFrame(results)
    for c in ("coef", "se", "p"):
        res[c] = res[c].astype(float).round(5)
    res.to_csv(OUTCSV, index=False)
    pd.set_option("display.width", 200, "display.max_columns", 30)
    print("\n" + res.to_string(index=False))
    print(f"\nwrote {OUTCSV}")
    return res


if __name__ == "__main__":
    main()
