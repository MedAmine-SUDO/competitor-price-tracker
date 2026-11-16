"""Streamlit dashboard: streamlit run dashboard/app.py  (DASHBOARD_DEMO=1 for the demo data)"""
from __future__ import annotations

import sys
from datetime import timedelta, timezone
from pathlib import Path

import altair as alt  # ships with Streamlit: no extra install, so the browser demo loads faster
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import DEMO, open_source  # noqa: E402

st.set_page_config(page_title="Competitor prices · Suivi des prix", page_icon="📊", layout="wide")

TUNIS = timezone(timedelta(hours=1))  # Tunisia: UTC+1 all year, no daylight saving

TEXT = {
    "fr": {
        "title": "Suivi des prix concurrents",
        "demo": "**Démo** · boutiques fictives et prix générés : la même application que le vrai tableau de bord, "
                "sans republier de données collectées. [Code source sur GitHub]",
        "demo_sample": "Échantillon figé de {n} relevés quotidiens ({first} → {last}), généré une fois : "
                       "le vrai outil, lui, tourne chaque matin.",
        "no_runs": "Aucun relevé pour l'instant. Lancez `python -m tracker run`.",
        "last_run": "Dernier relevé", "status": {"ok": "OK", "degraded": "INCOMPLET", "failed": "ÉCHEC"},
        "tracked": "Produits suivis", "sites": "Sites", "comparable": "Produits comparables",
        "drops_kpi": "Baisses > 10 % (dernier relevé)",
        "tabs": ["Comparatif", "Historique d'un produit", "Baisses de prix", "Fiabilité des relevés"],
        "no_common": "Aucun produit commun pour l'instant.",
        "filter": "Filtrer", "filter_ph": "ex. lenovo, redmi, 512",
        "product": "Produit", "cheapest": "Moins cher", "gap": "Écart %", "tie": "Égalité",
        "who_cheapest": "Qui est le moins cher, sur les produits communs", "products": "produits",
        "pick": "Produit (comparé entre sites)", "paid": "Prix payé (DT)",
        "paid_note": "Prix payé = prix promo s'il y en a un, sinon prix normal. Un point par relevé quotidien.",
        "duration_note": "Durée : surtout des pauses voulues. Les sites sont lus en parallèle, chacun à son rythme, "
                         "et le plus lent fixe la durée (jusqu'à 90 s entre deux pages pour un site qui limite "
                         "les robots). Le rapport est prêt avant 8 h.",
        "no_drops": "Aucune baisse de plus de 10 % détectée pour l'instant.",
        "date": "Date", "old": "Ancien prix", "new": "Nouveau prix", "drop": "Baisse %", "link": "Lien",
        "open": "ouvrir", "per_run": "Produits récupérés par relevé", "run": "Relevé", "start": "Début",
        "state": "Statut", "pages": "Pages", "errors": "Erreurs", "duration": "Durée", "alerts": "Alertes",
    },
    "en": {
        "title": "Competitor price tracker",
        "demo": "**Demo** · fictional shops and generated prices: the same app as the real dashboard, "
                "without republishing any scraped data. [Source code on GitHub]",
        "demo_sample": "Fixed sample of {n} daily runs ({first} → {last}), generated once: "
                       "the real tracker runs every morning.",
        "no_runs": "No run yet. Start one with `python -m tracker run`.",
        "last_run": "Last run", "status": {"ok": "OK", "degraded": "INCOMPLETE", "failed": "FAILED"},
        "tracked": "Products tracked", "sites": "Shops", "comparable": "Comparable products",
        "drops_kpi": "Drops > 10% (last run)",
        "tabs": ["Comparison", "Product history", "Price drops", "Run reliability"],
        "no_common": "No product sold by several shops yet.",
        "filter": "Filter", "filter_ph": "e.g. lenovo, redmi, 512",
        "product": "Product", "cheapest": "Cheapest", "gap": "Gap %", "tie": "Tie",
        "who_cheapest": "Who is cheapest, on products sold by several shops", "products": "products",
        "pick": "Product (compared across shops)", "paid": "Price paid (TND)",
        "paid_note": "Price paid = promo price when there is one, otherwise the regular price. One point per daily run.",
        "duration_note": "Duration: mostly deliberate pauses. Shops are read in parallel, each at its own pace, "
                         "and the slowest one sets the total (up to 90 s between pages for a shop that limits "
                         "bots). The report is ready before 8:00.",
        "no_drops": "No drop above 10% detected yet.",
        "date": "Date", "old": "Old price", "new": "New price", "drop": "Drop %", "link": "Link",
        "open": "open", "per_run": "Products collected per run", "run": "Run", "start": "Started",
        "state": "Status", "pages": "Pages", "errors": "Errors", "duration": "Duration", "alerts": "Alerts",
    },
}

head, switch = st.columns([6, 1], vertical_alignment="bottom")
lang = switch.segmented_control("Language", ["FR", "EN"], default="EN" if DEMO else "FR",
                                label_visibility="collapsed", key="lang") or ("EN" if DEMO else "FR")
L = TEXT[lang.lower()]


def money(v) -> str:
    """1099.5 -> '1 099,500 DT' (FR) or '1,099.500 DT' (EN); empty -> '—'"""
    if pd.isna(v):
        return "—"
    s = f"{v:,.3f} DT"
    return s.replace(",", " ").replace(".", ",") if lang == "FR" else s


def pct(v) -> str:
    return f"{v:.1f} %".replace(".", ",") if lang == "FR" else f"{v:.1f}%"


def local(ts) -> pd.Series:
    return pd.to_datetime(ts, utc=True).dt.tz_convert(TUNIS)


@st.cache_resource
def source():
    return open_source()


@st.cache_data(ttl=300)
def load(what: str, *args) -> pd.DataFrame:
    return getattr(source(), what)(*args)


SITES = source().sites
PALETTE = ["#2a78d6", "#e8762c", "#1baf7a", "#8e5bd0", "#d4447c", "#c49a12"]
COLORS = {name: PALETTE[i % len(PALETTE)] for i, name in enumerate(SITES.values())} | {L["tie"]: "#98a2b3"}


def site_colors(names) -> alt.Scale:
    names = [n for n in COLORS if n in set(names)]
    return alt.Scale(domain=names, range=[COLORS[n] for n in names])


runs = load("runs")
if runs.empty:
    st.info(L["no_runs"])
    st.stop()

last = runs.iloc[0]
latest = load("latest", int(last["id"]))
latest["Site"] = latest["site"].map(SITES)

# --- header & KPIs ------------------------------------------------------------------------
head.title(L["title"])
if DEMO:
    span = pd.to_datetime(runs["started_at"]).dt.tz_convert(TUNIS)
    sample = L["demo_sample"].format(n=len(runs), first=f"{span.min():%d/%m/%Y}", last=f"{span.max():%d/%m/%Y}")
    st.info(L["demo"] + "(https://github.com/MedAmine-SUDO/competitor-price-tracker)  \n" + sample, icon="🧪")
status_icon = {"ok": "✅", "degraded": "⚠️", "failed": "❌"}.get(last["status"], "")
started = pd.Timestamp(last["started_at"]).tz_convert(TUNIS)
st.caption(f"{L['last_run']} : {started:%d/%m/%Y %H:%M} · {status_icon} "
           f"{L['status'].get(last['status'], last['status'].upper())}")

drops = load("drops")
c1, c2, c3, c4 = st.columns(4)
c1.metric(L["tracked"], f"{len(latest):,}".replace(",", " " if lang == "FR" else ","))
c2.metric(L["sites"], latest["site"].nunique())
c3.metric(L["comparable"], int(latest["group_id"].nunique()))
c4.metric(L["drops_kpi"], int((drops["started_at"] == last["started_at"]).sum()) if len(drops) else 0)

tab_cmp, tab_hist, tab_drops, tab_runs = st.tabs(L["tabs"])

# --- comparison ---------------------------------------------------------------------------
with tab_cmp:
    m = latest[latest["group_id"].notna()]
    if m.empty:
        st.write(L["no_common"])
    else:
        pivot = m.pivot_table(index="group_id", columns="Site", values="effective_price", aggfunc="min")
        names = m.groupby("group_id")["name"].first()
        table = pd.DataFrame({L["product"]: names}).join(pivot)
        cols = list(pivot.columns)
        ties = table[cols].eq(table[cols].min(axis=1), axis=0).sum(axis=1) > 1
        table[L["cheapest"]] = table[cols].idxmin(axis=1).where(~ties, L["tie"])
        table[L["gap"]] = ((table[cols].max(axis=1) - table[cols].min(axis=1)) / table[cols].min(axis=1) * 100).round(1)
        search = st.text_input(L["filter"], placeholder=L["filter_ph"])
        if search:
            table = table[table[L["product"]].str.contains(search, case=False, na=False)]
        wins = table[L["cheapest"]].value_counts().rename_axis("Site").reset_index(name="n")
        bars = alt.Chart(wins, title=L["who_cheapest"]).encode(
            x=alt.X("n:Q", title=None),
            y=alt.Y("Site:N", sort=wins.sort_values("n", ascending=False)["Site"].tolist(), title=None),
            color=alt.Color("Site:N", scale=site_colors(wins["Site"]), legend=None),
            tooltip=["Site", alt.Tooltip("n:Q", title=L["products"])],
        )
        st.altair_chart((bars.mark_bar() + bars.mark_text(align="left", dx=4).encode(text="n:Q"))
                        .properties(height=230), width="stretch")
        table = table.sort_values(L["gap"], ascending=False)
        prices = table[cols]
        cheapest = prices.eq(prices.min(axis=1), axis=0)
        shown = table.assign(**{c: prices[c].map(money) for c in cols}, **{L["gap"]: table[L["gap"]].map(pct)})
        st.dataframe(
            shown.style.apply(lambda _: cheapest.reindex(columns=shown.columns, fill_value=False)
                              .map(lambda b: "background-color: #d9f2e3" if b else ""), axis=None),
            width="stretch", hide_index=True, height=520)

# --- product history ----------------------------------------------------------------------
with tab_hist:
    options = latest.sort_values("name")
    groups = options[options["group_id"].notna()].drop_duplicates("group_id")
    choice = st.selectbox(L["pick"], groups["name"].tolist()) if len(groups) else None
    if choice:
        gid = int(groups.loc[groups["name"] == choice, "group_id"].iloc[0])
        hist = load("history", gid)
        hist["Site"] = hist["site"].map(SITES)
        hist["scraped_at"] = local(hist["scraped_at"]).dt.tz_localize(None)
        line = alt.Chart(hist).mark_line(interpolate="step-after", point=True).encode(
            x=alt.X("scraped_at:T", title=None, axis=alt.Axis(format="%d/%m", labelAngle=0, tickCount="day")),
            y=alt.Y("prix:Q", title=L["paid"], scale=alt.Scale(zero=False)),
            color=alt.Color("Site:N", scale=site_colors(hist["Site"]), legend=alt.Legend(title=None, orient="top")),
            tooltip=["Site", alt.Tooltip("scraped_at:T", title=L["date"], format="%d/%m/%Y"),
                     alt.Tooltip("prix:Q", title=L["paid"], format=",.3f")],
        )
        st.altair_chart(line.properties(height=420), width="stretch")
        st.caption(L["paid_note"])

# --- drops ------------------------------------------------------------------------------
with tab_drops:
    if drops.empty:
        st.write(L["no_drops"])
    else:
        d = drops.assign(Site=drops["site"].map(SITES), Date=local(drops["started_at"]).dt.strftime("%d/%m/%Y"))
        st.dataframe(d[["Date", "Site", "name", "old_price", "new_price", "drop_pct", "url"]]
                     .rename(columns={"Date": L["date"], "name": L["product"], "old_price": L["old"],
                                      "new_price": L["new"], "drop_pct": L["drop"], "url": L["link"]}),
                     column_config={L["link"]: st.column_config.LinkColumn(display_text=L["open"])},
                     width="stretch", hide_index=True)

# --- run reliability ----------------------------------------------------------------------
with tab_runs:
    rows = []
    for r in runs.itertuples():
        for site, s in (r.report or {}).get("sites", {}).items():
            rows.append({"run": f"#{r.id}", "date": r.started_at, "Site": SITES.get(site, site),
                         "n": s.get("products", 0)})
    per_site = pd.DataFrame(rows)
    if len(per_site):
        order = per_site.sort_values("date")["run"].unique().tolist()
        grouped = alt.Chart(per_site, title=L["per_run"]).mark_bar().encode(
            x=alt.X("run:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("Site:N"),
            y=alt.Y("n:Q", title=L["products"]),
            color=alt.Color("Site:N", scale=site_colors(per_site["Site"]), legend=alt.Legend(title=None, orient="top")),
            tooltip=["Site", alt.Tooltip("run:N", title=L["run"]), alt.Tooltip("n:Q", title=L["products"])],
        )
        st.altair_chart(grouped.properties(height=320), width="stretch")
    st.dataframe(
        runs.assign(started_at=local(runs["started_at"]).dt.strftime("%d/%m/%Y %H:%M"),
                    status=runs["status"].map(lambda s: L["status"].get(s, s)),
                    duration=runs["report"].map(lambda r: f"{r.get('duration_s', 0) / 60:.1f} min"),
                    alerts=runs["report"].map(lambda r: r.get("price_drops", 0)))
            [["id", "started_at", "status", "products_seen", "pages_fetched", "errors", "duration", "alerts"]]
            .rename(columns={"id": L["run"], "started_at": L["start"], "status": L["state"],
                             "products_seen": L["tracked"], "pages_fetched": L["pages"], "errors": L["errors"],
                             "duration": L["duration"], "alerts": L["alerts"]}),
        width="stretch", hide_index=True)
    st.caption(L["duration_note"])
