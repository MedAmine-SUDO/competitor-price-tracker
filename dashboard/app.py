"""Streamlit dashboard: streamlit run dashboard/app.py  (DASHBOARD_DEMO=1 for the demo data)"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import DEMO, open_source  # noqa: E402

st.set_page_config(page_title="Suivi des prix concurrents", page_icon="📊", layout="wide")


def dt(v) -> str:
    """1099.5 -> '1 099,500 DT'; empty -> '—'"""
    return "—" if pd.isna(v) else f"{v:,.3f} DT".replace(",", " ").replace(".", ",")


@st.cache_resource
def source():
    return open_source()


@st.cache_data(ttl=300)
def load(what: str, *args) -> pd.DataFrame:
    return getattr(source(), what)(*args)


SITES = source().sites
PALETTE = ["#2a78d6", "#e8762c", "#1baf7a", "#8e5bd0", "#d4447c", "#c49a12"]
COLORS = {name: PALETTE[i % len(PALETTE)] for i, name in enumerate(SITES.values())} | {"Égalité": "#98a2b3"}

runs = load("runs")
if runs.empty:
    st.info("Aucun relevé pour l'instant. Lancez `python -m tracker run`.")
    st.stop()

last = runs.iloc[0]
latest = load("latest", int(last["id"]))
latest["Site"] = latest["site"].map(SITES)

# --- header & KPIs ------------------------------------------------------------------------
st.title("Suivi des prix concurrents")
if DEMO:
    st.info("**Démo** · boutiques fictives et prix générés : la même application que le vrai tableau de bord, "
            "sans republier de données collectées. [Code source sur GitHub]"
            "(https://github.com/MedAmine-SUDO/competitor-price-tracker)", icon="🧪")
status_icon = {"ok": "✅", "degraded": "⚠️", "failed": "❌"}.get(last["status"], "")
st.caption(f"Dernier relevé : {pd.Timestamp(last['started_at']).tz_convert('Africa/Tunis'):%d/%m/%Y %H:%M} "
           f"· {status_icon} {last['status'].upper()} · {last['report'].get('duration_s', 0) / 60:.1f} min")

drops = load("drops")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Produits suivis", f"{len(latest):,}".replace(",", " "))
c2.metric("Sites", latest["site"].nunique())
c3.metric("Produits comparables", int(latest["group_id"].nunique()))
c4.metric("Baisses > 10 % (dernier relevé)", int((drops["started_at"] == last["started_at"]).sum()) if len(drops) else 0)

tab_cmp, tab_hist, tab_drops, tab_runs = st.tabs(
    ["Comparatif", "Historique d'un produit", "Baisses de prix", "Fiabilité des relevés"])

# --- comparison ---------------------------------------------------------------------------
with tab_cmp:
    m = latest[latest["group_id"].notna()]
    if m.empty:
        st.write("Aucun produit commun pour l'instant.")
    else:
        pivot = m.pivot_table(index="group_id", columns="Site", values="effective_price", aggfunc="min")
        names = m.groupby("group_id")["name"].first()
        table = pd.DataFrame({"Produit": names}).join(pivot)
        cols = list(pivot.columns)
        ties = table[cols].eq(table[cols].min(axis=1), axis=0).sum(axis=1) > 1
        table["Moins cher"] = table[cols].idxmin(axis=1).where(~ties, "Égalité")
        table["Écart %"] = ((table[cols].max(axis=1) - table[cols].min(axis=1)) / table[cols].min(axis=1) * 100).round(1)
        search = st.text_input("Filtrer", placeholder="ex. lenovo, redmi, 512")
        if search:
            table = table[table["Produit"].str.contains(search, case=False, na=False)]
        wins = (table["Moins cher"].value_counts().rename_axis("Site").reset_index(name="produits")
                .sort_values("produits"))
        fig = px.bar(wins, x="produits", y="Site", orientation="h", color="Site", color_discrete_map=COLORS,
                     text="produits", title="Qui est le moins cher, sur les produits communs")
        fig.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig.update_layout(showlegend=False, height=300, yaxis_title="", xaxis_title=""),
                        width="stretch")
        table = table.sort_values("Écart %", ascending=False)
        prices = table[cols]
        cheapest = prices.eq(prices.min(axis=1), axis=0)
        shown = table.assign(**{c: prices[c].map(dt) for c in cols},
                             **{"Écart %": table["Écart %"].map(lambda v: f"{v:.1f} %".replace(".", ","))})
        st.dataframe(
            shown.style.apply(lambda _: cheapest.reindex(columns=shown.columns, fill_value=False)
                              .map(lambda b: "background-color: #d9f2e3" if b else ""), axis=None),
            width="stretch", hide_index=True, height=520)

# --- product history ----------------------------------------------------------------------
with tab_hist:
    options = latest.sort_values("name")
    groups = options[options["group_id"].notna()].drop_duplicates("group_id")
    choice = st.selectbox("Produit (comparé entre sites)", groups["name"].tolist()) if len(groups) else None
    if choice:
        gid = int(groups.loc[groups["name"] == choice, "group_id"].iloc[0])
        hist = load("history", gid)
        hist["Site"] = hist["site"].map(SITES)
        hist["scraped_at"] = pd.to_datetime(hist["scraped_at"], utc=True).dt.tz_convert("Africa/Tunis")
        fig = px.line(hist, x="scraped_at", y="prix", color="Site", markers=True, line_shape="hv",
                      color_discrete_map=COLORS, labels={"scraped_at": "", "prix": "Prix payé (DT)"})
        fig.update_layout(height=420, legend_title_text="", hovermode="x unified")
        st.plotly_chart(fig, width="stretch")
        st.caption("Prix payé = prix promo s'il y en a un, sinon prix normal. Un point par relevé quotidien.")

# --- drops ------------------------------------------------------------------------------
with tab_drops:
    if drops.empty:
        st.write("Aucune baisse de plus de 10 % détectée pour l'instant.")
    else:
        d = drops.assign(Site=drops["site"].map(SITES), Date=pd.to_datetime(drops["started_at"]).dt.strftime("%d/%m/%Y"))
        st.dataframe(d[["Date", "Site", "name", "old_price", "new_price", "drop_pct", "url"]]
                     .rename(columns={"name": "Produit", "old_price": "Ancien prix", "new_price": "Nouveau prix",
                                      "drop_pct": "Baisse %", "url": "Lien"}),
                     column_config={"Lien": st.column_config.LinkColumn(display_text="ouvrir")},
                     width="stretch", hide_index=True)

# --- run reliability ----------------------------------------------------------------------
with tab_runs:
    rows = []
    for r in runs.itertuples():
        for site, s in (r.report or {}).get("sites", {}).items():
            rows.append({"Relevé": f"#{r.id}", "date": r.started_at, "Site": SITES.get(site, site),
                         "Produits": s.get("products", 0), "Pages": s.get("pages", 0),
                         "Relances": s.get("retries", 0), "Erreurs": s.get("errors", 0)})
    per_site = pd.DataFrame(rows)
    if len(per_site):
        per_site = per_site.sort_values("date")
        fig = px.bar(per_site, x="Relevé", y="Produits", color="Site", barmode="group",
                     color_discrete_map=COLORS, title="Produits récupérés par relevé", labels={"Relevé": ""})
        st.plotly_chart(fig.update_layout(height=320, legend_title_text="").update_xaxes(type="category"),
                        width="stretch")
    st.dataframe(
        runs.assign(started_at=pd.to_datetime(runs["started_at"], utc=True).dt.tz_convert("Africa/Tunis")
                    .dt.strftime("%d/%m/%Y %H:%M"),
                    Durée=runs["report"].map(lambda r: f"{r.get('duration_s', 0) / 60:.1f} min"),
                    Alertes=runs["report"].map(lambda r: r.get("price_drops", 0)))
            [["id", "started_at", "status", "products_seen", "pages_fetched", "errors", "Durée", "Alertes"]]
            .rename(columns={"id": "Relevé", "started_at": "Début", "status": "Statut",
                             "products_seen": "Produits", "pages_fetched": "Pages", "errors": "Erreurs"}),
        width="stretch", hide_index=True)
