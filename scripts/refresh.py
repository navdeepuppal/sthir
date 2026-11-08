"""Daily refresh for Sthir: downloads Nifty 200 + Nifty 50 daily OHLCV from Yahoo and writes data/."""
import io, json, math, os, sys, datetime as dt
import pandas as pd, requests, yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "..", "data")
START, PART_LIMIT = "2012-01-01", 12_000_000

def constituents():
    try:
        r = requests.get("https://niftyindices.com/IndexConstituent/ind_nifty200list.csv", headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status(); df = pd.read_csv(io.StringIO(r.text)); df.columns = [c.strip() for c in df.columns]
        df = df[["Symbol", "Industry"]]; df.to_csv(os.path.join(HERE, "nifty200_fallback.csv"), index=False); print("constituents: niftyindices.com")
    except Exception as e:
        print("niftyindices unreachable (", e, ") — using saved list"); df = pd.read_csv(os.path.join(HERE, "nifty200_fallback.csv"))
    df["Symbol"] = df["Symbol"].astype(str).str.strip(); return dict(zip(df.Symbol, df.Industry.astype(str).str.strip()))

def r2(x): return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 2)

def main():
    sect = constituents(); tickers = [s + ".NS" for s in sect] + ["^NSEI"]
    data = yf.download(tickers, start=START, auto_adjust=True, group_by="ticker", threads=True, progress=False)
    frames, missing = [], []
    for t in tickers:
        try: df = data[t].dropna(how="all")
        except KeyError: missing.append(t); continue
        if df.empty: missing.append(t); continue
        df = df.reset_index()[["Date", "Open", "High", "Low", "Close", "Volume"]]; df["Symbol"] = "NIFTY50" if t == "^NSEI" else t[:-3]; frames.append(df)
    px = pd.concat(frames); px["Date"] = pd.to_datetime(px["Date"]).dt.strftime("%Y-%m-%d"); px = px[px.Close > 0]
    n_ok = px.Symbol.nunique(); print(f"{n_ok} series, missing: {missing}")
    if "NIFTY50" not in set(px.Symbol) or n_ok < 150: sys.exit("Too few series — keeping previous data")
    dates = sorted(set(px[px.Symbol == "NIFTY50"].Date)); pos = {d: i for i, d in enumerate(dates)}; px = px[px.Date.isin(pos)]
    parts, cur, size = [], {"syms": {}}, 0
    for sym, g in px.sort_values("Date").groupby("Symbol"):
        g = g.drop_duplicates("Date"); f, l = pos[g.Date.iloc[0]], pos[g.Date.iloc[-1]]; n = l - f + 1
        o = {"f": f, "o": [None]*n, "h": [None]*n, "l": [None]*n, "c": [None]*n, "v": [None]*n}
        for r in g.itertuples(index=False):
            j = pos[r.Date] - f; o["o"][j], o["h"][j], o["l"][j], o["c"][j] = r2(r.Open), r2(r.High), r2(r.Low), r2(r.Close)
            o["v"][j] = None if pd.isna(r.Volume) else int(r.Volume)
        js = len(json.dumps(o, separators=(",", ":")))
        if size + js > PART_LIMIT and size: parts.append(cur); cur, size = {"syms": {}}, 0
        cur["syms"][sym] = o; size += js
    parts.append(cur); parts[0]["head"] = {"dates": dates, "sectors": sect, "membership": {}, "synthetic": False}
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.startswith("part-"): os.remove(os.path.join(OUT, f))
    names = []
    for i, p in enumerate(parts):
        names.append(f"part-{i}.json"); json.dump(p, open(os.path.join(OUT, names[-1]), "w"), separators=(",", ":"))
    man = {"parts": names, "lastDate": dates[-1], "firstDate": dates[0], "nSyms": int(n_ok), "built": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z", "source": "Yahoo Finance (adjusted)"}
    json.dump(man, open(os.path.join(OUT, "manifest.json"), "w")); print("data to", man["lastDate"])

if __name__ == "__main__": main()
