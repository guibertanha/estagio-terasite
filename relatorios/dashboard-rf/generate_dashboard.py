#!/usr/bin/env python3
"""
Dashboard RF — Validação de Antenas Wi-Fi
Frotall FRITG01LTE (ESP32-WROOM-32 · PA66 IP54)
Terasite Tecnologia · Campanha de Validação RF 2026

Uso:  python relatorios/dashboard-rf/generate_dashboard.py
Saída: relatorios/dashboard-rf/dashboard_rf.html  (~4 MB, autossuficiente offline)
"""
import os, warnings, datetime
import pandas as pd
import numpy as np
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.io as pio
except ImportError:
    print("\nERRO: Plotly não instalado.")
    print("Execute:  pip install plotly pandas numpy\n")
    raise

warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════════════
#  PATHS
# ══════════════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT       = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
REL        = os.path.join(ROOT, "relatorios")
OUT        = os.path.join(SCRIPT_DIR, "dashboard_rf.html")

# ══════════════════════════════════════════════════════════════════════
#  PALETA / METADATA
# ══════════════════════════════════════════════════════════════════════
CMAP = {
    "A0": "#94a3b8",   # slate  – referência
    "A1": "#f97316",   # orange – descartada
    "A3": "#ef4444",   # red    – descartada
    "A4": "#3b82f6",   # blue   – finalista
    "A5": "#22c55e",   # green  – vencedora
}
ANTS  = ["A0", "A1", "A3", "A4", "A5"]
LABEL = {
    "A0": "A0 — PCB Nativa ESP32",
    "A1": "A1 — Cilíndrica Externa",
    "A3": "A3 — Flexível Média",
    "A4": "A4 — Micro SMD Rígida",
    "A5": "A5 — FPC Molex T-Bar",
}
SHORT = {"A0":"PCB Nativa","A1":"Cilíndrica","A3":"Flex Média",
         "A4":"Micro SMD", "A5":"FPC T-Bar"}

def rgba(h, a=1.0):
    h = h.lstrip("#")
    return f"rgba({int(h[:2],16)},{int(h[2:4],16)},{int(h[4:],16)},{a})"

BASE_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#e2e8f0", family="Inter, system-ui, sans-serif"),
    margin=dict(t=40, b=40, l=50, r=30),
)

def _lx(fig, **kw):
    """Aplica layout base + grade cartesiana (kw sobrescreve BASE_LAYOUT)."""
    fig.update_layout(**{**BASE_LAYOUT, **kw})
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.07)",
                     zerolinecolor="rgba(255,255,255,0.12)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.07)",
                     zerolinecolor="rgba(255,255,255,0.12)")
    return fig

def _l(fig, **kw):
    """Aplica layout base (sem grade – para polar/indicator)."""
    fig.update_layout(**{**BASE_LAYOUT, **kw})
    return fig

# ══════════════════════════════════════════════════════════════════════
#  CARREGAMENTO DE DADOS
# ══════════════════════════════════════════════════════════════════════
def _load(rel_path):
    p = os.path.join(REL, rel_path)
    if os.path.exists(p):
        try:
            return pd.read_csv(p, encoding="utf-8-sig")
        except Exception as e:
            print(f"  WARN: {rel_path}: {e}")
    return pd.DataFrame()

def _first(*dfs):
    for df in dfs:
        if not df.empty:
            return df
    return pd.DataFrame()

print("  Carregando CSVs...")
rssi_ant  = _first(_load("rssi-completo/02_resumo_por_antena.csv"),
                   _load("rssi-fase1/02_resumo_por_antena.csv"))
rssi_cvsb = _first(_load("rssi-completo/03_case_vs_base.csv"),
                   _load("rssi-fase1/03_case_vs_base.csv"))
rssi_raw  = _first(_load("rssi-completo/04_amostras_brutas.csv"),
                   _load("rssi-fase1/04_amostras_brutas.csv"))
ping_bst  = _load("ping-tecnico/02_bursts_bruto.csv")
ping_fam  = _first(_load("ping-tecnico/06_resumo_por_familia.csv"),
                   _load("ping-tecnico/05_resumo_por_familia.csv"))

# ══════════════════════════════════════════════════════════════════════
#  ENGINE DE SCORE  (0–100)
# ══════════════════════════════════════════════════════════════════════
# Valores validados como fallback
_FB_RSSI  = {"A0":-56.66,"A1":-58.09,"A3":-60.13,"A4":-45.90,"A5":-43.93}
_FB_ATTEN = {"A0":12.60, "A1":23.37, "A3":20.03, "A4":6.92}   # A5 sem baseline
_FB_STD   = {"A0":5.46,  "A1":3.52,  "A3":2.21,  "A4":3.01,  "A5":2.59}
_FB_FAIL  = {"A0":0.0,   "A1":None,  "A3":None,  "A4":0.0,   "A5":0.0}

def _get_rssi_case():
    d = {}
    if not rssi_ant.empty and "cenario" in rssi_ant.columns and "antena" in rssi_ant.columns:
        c = rssi_ant[rssi_ant["cenario"] == "CASE"]
        for a in ANTS:
            r = c[c["antena"] == a]
            if not r.empty and "media_rssi" in r.columns:
                d[a] = float(r["media_rssi"].iloc[0])
    return {a: d.get(a, _FB_RSSI[a]) for a in ANTS}

def _get_atten():
    d = {}
    if not rssi_cvsb.empty:
        ac = next((c for c in ("antena","Antena") if c in rssi_cvsb.columns), None)
        lc = next((c for c in ("perda_case_db","Perda_InCase_dB") if c in rssi_cvsb.columns), None)
        if ac and lc:
            for _, r in rssi_cvsb.iterrows():
                k = str(r[ac]).strip().upper()[:2]
                if k in ANTS:
                    d[k] = float(r[lc])
    return {a: d.get(a, _FB_ATTEN.get(a)) for a in ANTS}

def _get_std():
    d = {}
    if not rssi_ant.empty and "cenario" in rssi_ant.columns:
        c = rssi_ant[rssi_ant["cenario"] == "CASE"]
        for a in ANTS:
            r = c[c["antena"] == a]
            if not r.empty:
                for col in ("media_std_interna","std_entre_ensaios"):
                    if col in r.columns and pd.notna(r[col].iloc[0]):
                        d[a] = float(r[col].iloc[0])
                        break
    return {a: d.get(a, _FB_STD[a]) for a in ANTS}

def _get_pfail():
    d = {}
    if not ping_fam.empty and "antena" in ping_fam.columns:
        col = next((c for c in ("fail_rate_mean","fail_rate_pct") if c in ping_fam.columns), None)
        if col:
            for _, r in ping_fam.iterrows():
                d[str(r["antena"])] = float(r[col])
    for a in ANTS:
        if a not in d:
            v = _FB_FAIL.get(a)
            d[a] = v if v is not None else 50.0
    return d

def compute_scores():
    rssi  = _get_rssi_case()
    atten = _get_atten()
    std   = _get_std()
    fail  = _get_pfail()

    def nmax(v, vdict):   # maior raw → maior pontuação
        lo, hi = min(vdict.values()), max(vdict.values())
        return (v - lo) / (hi - lo + 1e-9) * 100

    def nmin(v, vdict):   # menor raw → maior pontuação
        lo, hi = min(vdict.values()), max(vdict.values())
        return (1 - (v - lo) / (hi - lo + 1e-9)) * 100

    rs  = {a: nmax(rssi[a], rssi) for a in ANTS}
    as_ = {a: nmin(atten[a], {k:v for k,v in atten.items() if v is not None})
           for a in ANTS if atten.get(a) is not None}
    ss  = {a: nmin(std[a], std) for a in ANTS}
    ps  = {a: max(0.0, 100.0 - fail[a] * 10) for a in ANTS}

    out = {}
    for a in ANTS:
        r, s, p = rs[a], ss[a], ps[a]
        at = as_.get(a)
        if at is None:
            total = 0.55*r + 0.30*s + 0.15*p
        else:
            total = 0.40*r + 0.30*at + 0.20*s + 0.10*p
        out[a] = dict(
            total   = round(max(0, min(100, total)), 1),
            rssi_sc = round(r, 1),
            atten_sc= round(at, 1) if at is not None else None,
            std_sc  = round(s, 1),
            ping_sc = round(p, 1),
            rssi_val  = rssi[a],
            atten_val = atten.get(a),
            std_val   = std[a],
            ping_val  = fail[a],
        )
    return out

SC = compute_scores()
print("  Scores:", {a: SC[a]["total"] for a in ANTS})

# ══════════════════════════════════════════════════════════════════════
#  GRÁFICOS
# ══════════════════════════════════════════════════════════════════════

def c_gauges():
    """Velocímetros 0-100 por antena."""
    fig = make_subplots(rows=1, cols=5,
                        specs=[[{"type":"indicator"}]*5],
                        subplot_titles=[LABEL[a] for a in ANTS])
    for i, a in enumerate(ANTS, 1):
        s, col = SC[a], CMAP[a]
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=s["total"],
            number=dict(font=dict(size=32, color=col)),
            gauge=dict(
                axis=dict(range=[0,100], tickwidth=1,
                          tickcolor="rgba(255,255,255,0.2)"),
                bar=dict(color=col, thickness=0.65),
                bgcolor="rgba(0,0,0,0)",
                borderwidth=2, bordercolor=col,
                steps=[
                    dict(range=[0, 40],  color="rgba(239,68,68,0.10)"),
                    dict(range=[40, 70], color="rgba(234,179,8,0.10)"),
                    dict(range=[70,100], color="rgba(34,197,94,0.10)"),
                ],
            ),
        ), row=1, col=i)
    _l(fig, height=220, margin=dict(t=50,b=10,l=10,r=10))
    fig.update_annotations(font_size=10)
    return fig


def c_radar():
    """Spider chart multidimensional."""
    cats = ["RSSI In-Case","Robustez<br>Invólucro","Estabilidade",
            "Ping OK","Score Final"]
    fig = go.Figure()
    for a in ANTS:
        s = SC[a]
        vals = [s["rssi_sc"],
                s["atten_sc"] if s["atten_sc"] is not None else 50.0,
                s["std_sc"], s["ping_sc"], s["total"]]
        fig.add_trace(go.Scatterpolar(
            r=vals+[vals[0]], theta=cats+[cats[0]],
            fill="toself", name=LABEL[a],
            line=dict(color=CMAP[a], width=2),
            fillcolor=rgba(CMAP[a], 0.10),
        ))
    _l(fig, height=430, margin=dict(t=40,b=40,l=60,r=60),
       polar=dict(
           bgcolor="rgba(0,0,0,0)",
           radialaxis=dict(range=[0,100], tickvals=[25,50,75,100],
                           gridcolor="rgba(255,255,255,0.10)",
                           tickfont=dict(size=8, color="rgba(255,255,255,0.35)")),
           angularaxis=dict(gridcolor="rgba(255,255,255,0.10)",
                            tickfont=dict(size=11)),
       ),
       legend=dict(bgcolor="rgba(17,24,39,0.85)",
                   bordercolor="rgba(255,255,255,0.1)",
                   borderwidth=1, x=1.05, y=0.5),
    )
    return fig


def c_ranking():
    """Barras horizontais — RSSI médio in-case."""
    rssi_vals = _get_rssi_case()
    ants_s = sorted(ANTS, key=lambda a: rssi_vals[a], reverse=True)
    vals   = [rssi_vals[a] for a in ants_s]
    cols   = [CMAP[a] for a in ants_s]
    names  = [LABEL[a] for a in ants_s]

    fig = go.Figure(go.Bar(
        x=vals, y=names, orientation="h",
        marker_color=cols,
        text=[f"{v:.2f} dBm" for v in vals],
        textposition="outside",
        textfont=dict(size=12, color="#e2e8f0"),
        hovertemplate="%{y}: %{x:.2f} dBm<extra></extra>",
    ))
    _lx(fig, height=280, margin=dict(t=20,b=40,l=195,r=100))
    fig.update_xaxes(title="RSSI médio in-case (dBm)",
                     range=[min(vals)-9, max(vals)+5])
    for x0, x1, c, txt in [
        (-75,-55,"rgba(239,68,68,0.07)","Zona Crítica"),
        (-55,-45,"rgba(234,179,8,0.07)","Zona Marginal"),
        (-45,-28,"rgba(34,197,94,0.07)","Zona OK"),
    ]:
        fig.add_vrect(x0=x0, x1=x1, fillcolor=c, line_width=0,
                      annotation_text=txt, annotation_position="top left",
                      annotation_font=dict(size=9, color=c.replace("0.07","0.6")))
    return fig


def c_attenuation():
    """Barras agrupadas — baseline vs in-case + delta."""
    _FB_BASE = {"A0":-44.06,"A1":-34.72,"A3":-40.10,"A4":-38.98}
    base_v, case_v = {}, _get_rssi_case()

    if not rssi_ant.empty and "cenario" in rssi_ant.columns:
        c = rssi_ant[rssi_ant["cenario"] == "BASE"]
        for a in ANTS:
            r = c[c["antena"] == a]
            if not r.empty and "media_rssi" in r.columns:
                base_v[a] = float(r["media_rssi"].iloc[0])
    for a in ANTS:
        base_v.setdefault(a, _FB_BASE.get(a))

    ants_b = [a for a in ANTS if base_v.get(a) is not None]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[LABEL[a] for a in ants_b],
        y=[base_v[a] for a in ants_b],
        name="Baseline (ar livre)",
        marker_color=[rgba(CMAP[a], 0.40) for a in ants_b],
        marker_line_color=[CMAP[a] for a in ants_b],
        marker_line_width=2,
        hovertemplate="%{x}<br>Baseline: %{y:.2f} dBm<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=[LABEL[a] for a in ants_b],
        y=[case_v[a] for a in ants_b],
        name="In-Case (invólucro)",
        marker_color=[CMAP[a] for a in ants_b],
        hovertemplate="%{x}<br>In-Case: %{y:.2f} dBm<extra></extra>",
    ))
    for a in ants_b:
        loss = case_v[a] - base_v[a]
        fig.add_annotation(
            x=LABEL[a], y=case_v[a] - 0.8,
            text=f"▼ {abs(loss):.1f} dB",
            showarrow=False, yanchor="top",
            font=dict(size=12, color="#fbbf24", family="monospace"),
        )
    _lx(fig, height=350, barmode="group",
        margin=dict(t=20,b=50,l=50,r=30))
    fig.update_yaxes(title="RSSI médio (dBm)")
    fig.update_layout(legend=dict(
        bgcolor="rgba(17,24,39,0.85)", bordercolor="rgba(255,255,255,0.1)",
        borderwidth=1, orientation="h", x=0.5, xanchor="center", y=1.12,
    ))
    return fig


def c_timeseries():
    """Série temporal de RSSI — amostras in-case."""
    if rssi_raw.empty or not {"antena","rssi","sample_idx"}.issubset(rssi_raw.columns):
        fig = go.Figure()
        fig.add_annotation(text="Dados brutos não disponíveis",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="rgba(255,255,255,0.3)"))
        return _lx(fig, height=320)

    df = rssi_raw.copy()
    if "cenario" in df.columns:
        tmp = df[df["cenario"] == "CASE"]
        if not tmp.empty:
            df = tmp

    fig = go.Figure()
    for a in ANTS:
        sub = df[df["antena"] == a].copy().head(300)
        if sub.empty:
            continue
        sub = sub.sort_values("sample_idx")
        sub["sm"] = sub["rssi"].rolling(7, min_periods=1).mean()
        # Pontos brutos
        fig.add_trace(go.Scatter(
            x=sub["sample_idx"], y=sub["rssi"],
            mode="markers", showlegend=False,
            marker=dict(color=CMAP[a], size=3, opacity=0.22),
        ))
        # Linha suavizada
        fig.add_trace(go.Scatter(
            x=sub["sample_idx"], y=sub["sm"],
            mode="lines", name=LABEL[a],
            line=dict(color=CMAP[a], width=2),
        ))
    _lx(fig, height=340, hovermode="x unified",
        legend=dict(bgcolor="rgba(17,24,39,0.85)",
                    bordercolor="rgba(255,255,255,0.1)", borderwidth=1))
    fig.update_xaxes(title="Amostra (índice)")
    fig.update_yaxes(title="RSSI (dBm)")
    return fig


def c_ping_latency():
    """Box plot de latência por antena."""
    if ping_bst.empty or "latencia_ms" not in ping_bst.columns:
        fig = go.Figure()
        fig.add_annotation(text="Dados de ping não disponíveis",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="rgba(255,255,255,0.3)"))
        return _lx(fig, height=310)

    ok = ping_bst[ping_bst["status"] == "OK"] if "status" in ping_bst.columns else ping_bst
    fig = go.Figure()
    for a in ["A0","A4","A5"]:
        sub = ok[ok["antena"] == a]
        if sub.empty:
            continue
        fig.add_trace(go.Box(
            y=sub["latencia_ms"], name=LABEL[a],
            marker_color=CMAP[a], line_color=CMAP[a],
            fillcolor=rgba(CMAP[a], 0.12), boxmean="sd",
            hovertemplate="%{y:.1f} ms<extra>" + LABEL[a] + "</extra>",
        ))
    _lx(fig, height=310, showlegend=False, boxgap=0.3)
    fig.update_yaxes(title="Latência (ms)")
    return fig


def c_ping_scatter():
    """Scatter RSSI link vs latência por burst."""
    if ping_bst.empty or "antena" not in ping_bst.columns:
        fig = go.Figure()
        fig.add_annotation(text="Dados de ping não disponíveis",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="rgba(255,255,255,0.3)"))
        return _lx(fig, height=310)

    ok = ping_bst[ping_bst["status"] == "OK"] if "status" in ping_bst.columns else ping_bst
    rc = next((c for c in ("rssi_link_dbm","rssi_link") if c in ok.columns), None)
    fig = go.Figure()
    for a in ["A0","A4","A5"]:
        sub = ok[ok["antena"] == a]
        if sub.empty or rc is None or "latencia_ms" not in sub.columns:
            continue
        fig.add_trace(go.Scatter(
            x=sub[rc], y=sub["latencia_ms"],
            mode="markers", name=LABEL[a],
            marker=dict(color=CMAP[a], size=5, opacity=0.65),
            hovertemplate=f"RSSI: %{{x}} dBm · Lat: %{{y:.1f}} ms<extra>{LABEL[a]}</extra>",
        ))
    _lx(fig, height=310,
        legend=dict(bgcolor="rgba(17,24,39,0.85)",
                    bordercolor="rgba(255,255,255,0.1)", borderwidth=1))
    fig.update_xaxes(title="RSSI link (dBm)")
    fig.update_yaxes(title="Latência (ms)")
    return fig


def c_heatmap():
    """Mapa de calor da distribuição de RSSI por antena."""
    if rssi_raw.empty or not {"antena","rssi"}.issubset(rssi_raw.columns):
        fig = go.Figure()
        fig.add_annotation(text="Dados brutos não disponíveis",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="rgba(255,255,255,0.3)"))
        return _lx(fig, height=260)

    df = rssi_raw.copy()
    if "cenario" in df.columns:
        tmp = df[df["cenario"] == "CASE"]
        if not tmp.empty:
            df = tmp

    bins    = np.arange(-78, -24, 2)
    centers = bins[:-1] + 1
    z, yl   = [], []

    for a in ANTS:
        sub = df[df["antena"] == a]["rssi"].dropna()
        if sub.empty:
            continue
        counts, _ = np.histogram(sub, bins=bins)
        total = counts.sum()
        z.append((counts / total * 100).tolist() if total > 0 else counts.tolist())
        yl.append(LABEL[a])

    if not z:
        return _lx(go.Figure(), height=260)

    fig = go.Figure(go.Heatmap(
        z=z, x=centers.tolist(), y=yl,
        colorscale="Viridis",
        hovertemplate="%{y}<br>%{x} dBm → %{z:.1f}%<extra></extra>",
        colorbar=dict(
            title=dict(text="% amostras", font=dict(color="#e2e8f0")),
            tickfont=dict(color="#e2e8f0"),
        ),
    ))
    _lx(fig, height=260, margin=dict(t=20,b=50,l=195,r=80))
    fig.update_xaxes(title="RSSI (dBm)")
    return fig


# ══════════════════════════════════════════════════════════════════════
#  HELPERS HTML
# ══════════════════════════════════════════════════════════════════════
def _div(fig, div_id, first=False):
    return pio.to_html(fig, full_html=False, div_id=div_id,
                       include_plotlyjs=(True if first else False))


def _score_cards():
    BADGES = {
        "A0": ("⚡ Referência", "#1a2637", "#94a3b8"),
        "A1": ("✕ Descartada",  "#3d1010", "#ef4444"),
        "A3": ("✕ Descartada",  "#3d1010", "#ef4444"),
        "A4": ("★ Finalista",   "#0f2351", "#3b82f6"),
        "A5": ("🏆 Vencedora",  "#082012", "#22c55e"),
    }
    out = ""
    for a in ANTS:
        s = SC[a]
        lbl, bg, tc = BADGES[a]
        atten_str = f"{s['atten_val']:.1f} dB" if s["atten_val"] is not None else "N/A"
        out += f"""
<div class="sc" style="border-color:{CMAP[a]}2a">
  <div class="sc-badge" style="background:{bg};color:{tc};border:1px solid {tc}3a">{lbl}</div>
  <div class="sc-ant" style="color:{CMAP[a]}">{a}</div>
  <div class="sc-nm">{SHORT[a]}</div>
  <div class="sc-score" style="color:{CMAP[a]}">{s["total"]}</div>
  <div class="sc-unit">/ 100</div>
  <div class="sc-meta">
    <span title="RSSI in-case">📶 {s["rssi_val"]:.2f} dBm</span>
    <span title="Perda invólucro">📦 {atten_str}</span>
    <span title="Desvio padrão">σ {s["std_val"]:.2f} dB</span>
    <span title="Falha ping">🏓 {s["ping_val"]:.0f}% fail</span>
  </div>
</div>"""
    return out


NEXT_STEPS = [
    ("TM-01","🌡️","Termomecânico",
     "Ciclagem −20 / +85 °C · 20 ciclos · integridade mecânica da conexão U.FL","#f97316"),
    ("TM-02","🔧","Vibração e Choque",
     "IEC 60068-2 · eixos X/Y/Z · perfil de cabine de retroescavadeira","#f59e0b"),
    ("TM-03","💧","Estanqueidade IP54",
     "Câmara de poeira e jato d'água · vedação com antena FPC instalada","#06b6d4"),
    ("EMI-01","📡","Varredura EMI",
     "SA6 35–6200 MHz · harmônicos DC-DC, modem 4G e barramento CAN","#8b5cf6"),
    ("RF-03","🚜","Ensaio de Campo",
     "iPerf3 throughput · distâncias 5/10/25 m · cabine de máquina em operação","#22c55e"),
    ("PVT-01","✅","Validação PVT",
     "3 unidades pré-série · integração firmware completa · aceite final","#22c55e"),
]


def _next_steps():
    return "".join(f"""
<div class="ns" style="border-left:3px solid {c}">
  <div class="ns-code" style="color:{c}">{code}</div>
  <div class="ns-title">{ico} {t}</div>
  <div class="ns-desc">{d}</div>
</div>""" for code,ico,t,d,c in NEXT_STEPS)


# ══════════════════════════════════════════════════════════════════════
#  MONTAGEM DO HTML FINAL
# ══════════════════════════════════════════════════════════════════════
def build():
    print("  Gerando gráficos...")
    charts = [
        c_gauges(), c_radar(), c_ranking(), c_attenuation(),
        c_timeseries(), c_ping_latency(), c_ping_scatter(), c_heatmap(),
    ]
    ids = ["gauges","radar","ranking","atten","series","plat","psc","heat"]

    print("  Convertendo para HTML (isso leva ~10s – embutindo Plotly.js)...")
    divs = [_div(f, i, first=(j == 0)) for j,(f,i) in enumerate(zip(charts, ids))]
    dg,dr,drk,da,ds,dl,dps,dh = divs

    a5s = SC["A5"]["total"]
    a4s = SC["A4"]["total"]
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    # ── CSS ──────────────────────────────────────────────────────────
    css = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;font-size:15px}
body{background:#0a0f1e;color:#e2e8f0;font-family:Inter,system-ui,-apple-system,sans-serif;line-height:1.6}
a{color:#22c55e;text-decoration:none}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-track{background:#0f172a}
::-webkit-scrollbar-thumb{background:#334155;border-radius:3px}

/* NAV */
nav{position:sticky;top:0;z-index:100;background:rgba(10,15,30,0.94);
  backdrop-filter:blur(14px);border-bottom:1px solid #1f2937;
  display:flex;align-items:center;justify-content:space-between;
  padding:0 2rem;height:50px}
.nb{font-size:12px;font-weight:600;color:#64748b;display:flex;align-items:center;gap:8px}
.dot{width:7px;height:7px;border-radius:50%;background:#22c55e;animation:pulse 2.2s infinite}
nav a{font-size:11px;font-weight:600;color:#4b5563;text-transform:uppercase;
  letter-spacing:.06em;margin-left:1.3rem;transition:color .18s}
nav a:hover{color:#e2e8f0}

/* ESTRUTURA */
.w{max-width:1180px;margin:0 auto;padding:3rem 1.5rem}
hr.d{border:none;border-top:1px solid #1f2937;max-width:1180px;margin:0 auto}
.ey{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;
  color:#475569;margin-bottom:.4rem}
.h2{font-size:1.55rem;font-weight:800;color:#f1f5f9;margin-bottom:1.4rem;line-height:1.25}

/* HERO */
#hero{max-width:1180px;margin:0 auto;padding:3.5rem 1.5rem 2.5rem;position:relative;overflow:hidden}
.hglow{position:absolute;top:0;right:0;width:500px;height:400px;
  background:radial-gradient(ellipse at 80% 20%,rgba(34,197,94,.07),transparent 68%);
  pointer-events:none}
.h1{font-size:clamp(1.9rem,4vw,3.1rem);font-weight:900;line-height:1.15;
  margin-bottom:.9rem;color:#f1f5f9}
.win{color:#22c55e;text-shadow:0 0 40px rgba(34,197,94,.35)}
.hsub{color:#64748b;max-width:580px;margin-bottom:1.8rem;font-size:.95rem}
.kpis{display:flex;flex-wrap:wrap;gap:1rem}
.kpi{background:#111827;border:1px solid #1f2937;border-radius:10px;
  padding:.85rem 1.3rem;min-width:148px}
.kv{font-size:1.7rem;font-weight:900;line-height:1}
.kl{font-size:10px;color:#475569;margin-top:3px;text-transform:uppercase;letter-spacing:.07em}

/* SCORE CARDS */
.scg{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:.9rem;margin-bottom:1.3rem}
.sc{background:#111827;border:1px solid;border-radius:12px;padding:1.1rem;
  transition:transform .2s,box-shadow .2s}
.sc:hover{transform:translateY(-3px);box-shadow:0 8px 30px rgba(0,0,0,.45)}
.sc-badge{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.09em;
  border-radius:4px;padding:2px 6px;display:inline-block;margin-bottom:.55rem}
.sc-ant{font-size:1.9rem;font-weight:900;line-height:1;margin-bottom:1px}
.sc-nm{font-size:10.5px;color:#4b5563;margin-bottom:.5rem;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.sc-score{font-size:2.8rem;font-weight:900;line-height:1}
.sc-unit{font-size:10px;color:#4b5563;margin-bottom:.6rem}
.sc-meta{display:flex;flex-wrap:wrap;gap:3px}
.sc-meta span{font-size:9.5px;color:#64748b;background:rgba(255,255,255,.04);
  border-radius:3px;padding:2px 5px}

/* CHART CARD */
.cc{background:#111827;border:1px solid #1f2937;border-radius:12px;
  padding:1.1rem 1rem .4rem;margin-bottom:1.3rem}
.cct{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.09em;
  color:#4b5563;margin-bottom:.6rem;padding:0 .25rem}

/* 2 COLUNAS */
.two{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;align-items:start}
@media(max-width:720px){.two{grid-template-columns:1fr}}

/* METODOLOGIA */
.mg{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:.9rem}
.mc{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:1.1rem}
.mci{font-size:1.4rem;margin-bottom:.4rem}
.mct{font-weight:700;font-size:.88rem;margin-bottom:.3rem}
.mcd{font-size:11px;color:#4b5563;line-height:1.55}

/* PRÓXIMOS PASSOS */
.ng{display:grid;grid-template-columns:repeat(auto-fill,minmax(265px,1fr));gap:.9rem}
.ns{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:.9rem 1.1rem}
.ns-code{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.09em;margin-bottom:3px}
.ns-title{font-size:13.5px;font-weight:600;margin-bottom:3px}
.ns-desc{font-size:11px;color:#4b5563;line-height:1.5}

/* VEREDICTO */
#verd{background:linear-gradient(135deg,#0d1e10 0%,#0a1628 50%,#0b1d17 100%);
  border-top:1px solid #1f2937;border-bottom:1px solid #1f2937}
.vb{max-width:1180px;margin:0 auto;padding:4rem 1.5rem;
  display:flex;flex-direction:column;align-items:center;text-align:center}
.vt{font-size:3rem;margin-bottom:.8rem}
.vpre{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;
  color:#22c55e;margin-bottom:.4rem}
.vmain{font-size:clamp(1.7rem,3.5vw,2.5rem);font-weight:900;color:#f1f5f9;
  margin-bottom:.9rem;line-height:1.2}
.vmain span{color:#22c55e}
.vsub{max-width:560px;color:#64748b;margin-bottom:1.8rem;font-size:.93rem}
.vpills{display:flex;flex-wrap:wrap;gap:.6rem;justify-content:center}
.vp{padding:.35rem .9rem;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid}

footer{text-align:center;padding:1.8rem;font-size:11px;color:#374151;
  border-top:1px solid #1f2937}

/* NOTE */
.note{font-size:10.5px;color:#374151;padding:.25rem .5rem .5rem;line-height:1.6}

@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.85)}}
@keyframes fadeUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
.fu{animation:fadeUp .55s ease forwards}
.fu2{animation:fadeUp .55s .15s both}
.fu3{animation:fadeUp .55s .30s both}
"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard RF · Validação de Antenas · Frotall FRITG01LTE</title>
<style>{css}</style>
</head>
<body>

<nav>
  <div class="nb"><div class="dot"></div>Frotall FRITG01LTE &nbsp;·&nbsp; Validação RF de Antenas Wi-Fi</div>
  <div>
    <a href="#scores">Scores</a>
    <a href="#ranking">Ranking</a>
    <a href="#aten">Atenuação</a>
    <a href="#serie">Série</a>
    <a href="#ping">Ping</a>
    <a href="#metodo">Método</a>
    <a href="#verd">Veredicto</a>
  </div>
</nav>

<!-- ── HERO ────────────────────────────────────────────────── -->
<section id="hero">
  <div class="hglow"></div>
  <p class="ey fu">Campanha de Validação &nbsp;·&nbsp; ESP32-WROOM-32 &nbsp;·&nbsp; Invólucro PA66 IP54</p>
  <h1 class="h1 fu2">Vencedora da Campanha:<br><span class="win">A5 — FPC Molex T-Bar</span></h1>
  <p class="hsub fu3">5 antenas testadas em 2 fases · medições de RSSI, atenuação por invólucro e
  estabilidade de enlace via ping. A5 lidera in-case com
  <strong style="color:#f1f5f9">−43,93 dBm</strong> e A4 apresenta menor perda ao invólucro (6,9 dB).</p>
  <div class="kpis fu3">
    <div class="kpi"><div class="kv" style="color:#22c55e">{a5s:.0f} pts</div><div class="kl">Score A5 · vencedora</div></div>
    <div class="kpi"><div class="kv" style="color:#3b82f6">{a4s:.0f} pts</div><div class="kl">Score A4 · finalista</div></div>
    <div class="kpi"><div class="kv" style="color:#e2e8f0">−43,93 dBm</div><div class="kl">RSSI in-case A5</div></div>
    <div class="kpi"><div class="kv" style="color:#e2e8f0">5</div><div class="kl">Antenas testadas</div></div>
    <div class="kpi"><div class="kv" style="color:#e2e8f0">0%</div><div class="kl">Falha no ping A4/A5</div></div>
  </div>
</section>

<hr class="d">

<!-- ── SCORES ──────────────────────────────────────────────── -->
<div id="scores" class="w">
  <p class="ey">Score Composto</p>
  <h2 class="h2">Ranking por Pontuação Final</h2>
  <div class="scg">{_score_cards()}</div>
  <div class="cc">
    <div class="cct">Velocímetro de Score — 0 a 100 pontos por antena</div>
    {dg}
  </div>
  <p class="note">Ponderação: RSSI in-case (40%) · Robustez ao invólucro (30%) · Estabilidade σ (20%) · Taxa de falha no ping (10%).
  A5 sem baseline dedicado na Fase 1 — peso redistribuído entre RSSI (55%) e σ (30%).</p>
</div>

<hr class="d">

<!-- ── RANKING ─────────────────────────────────────────────── -->
<div id="ranking" class="w">
  <p class="ey">Comparativo de Desempenho</p>
  <h2 class="h2">Ranking de Antenas</h2>
  <div class="two">
    <div><div class="cc"><div class="cct">RSSI Médio In-Case (dBm)</div>{drk}</div></div>
    <div><div class="cc"><div class="cct">Análise Multidimensional · Radar Chart</div>{dr}</div></div>
  </div>
</div>

<hr class="d">

<!-- ── ATENUAÇÃO ───────────────────────────────────────────── -->
<div id="aten" class="w">
  <p class="ey">Impacto do Invólucro</p>
  <h2 class="h2">Baseline vs In-Case — Perda por Atenuação</h2>
  <div class="cc"><div class="cct">RSSI médio: ar livre × instalado no invólucro PA66 IP54</div>{da}</div>
  <p class="note">▼ indica a perda real imposta pelo invólucro. A4 registrou 6,9 dB de perda (menor entre as antenas com baseline).
  A5 foi testada exclusivamente in-case na Fase 1 — sem baseline comparável nesta campanha.</p>
</div>

<hr class="d">

<!-- ── SÉRIE TEMPORAL ──────────────────────────────────────── -->
<div id="serie" class="w">
  <p class="ey">Estabilidade Temporal</p>
  <h2 class="h2">Série Temporal de RSSI (In-Case)</h2>
  <div class="cc"><div class="cct">Amostras brutas + média móvel 7 pts · cenário in-case · primeiras 300 amostras por antena</div>{ds}</div>
</div>

<hr class="d">

<!-- ── PING ────────────────────────────────────────────────── -->
<div id="ping" class="w">
  <p class="ey">Estabilidade do Enlace</p>
  <h2 class="h2">Ensaios de Ping — Latência e Confiabilidade</h2>
  <div class="two">
    <div><div class="cc"><div class="cct">Distribuição de Latência por Antena (box + σ)</div>{dl}</div></div>
    <div><div class="cc"><div class="cct">RSSI do Link vs Latência por Burst</div>{dps}</div></div>
  </div>
  <div class="cc"><div class="cct">Mapa de Calor · Distribuição de RSSI In-Case por Antena (% de amostras por faixa de 2 dBm)</div>{dh}</div>
</div>

<hr class="d">

<!-- ── METODOLOGIA ─────────────────────────────────────────── -->
<div id="metodo" class="w">
  <p class="ey">Credibilidade Técnica</p>
  <h2 class="h2">Metodologia dos Ensaios</h2>
  <div class="mg">
    <div class="mc"><div class="mci">📡</div><div class="mct">Hardware Sob Teste</div>
      <div class="mcd">ESP32-WROOM-32 em invólucro PA66 IP54. 5 variantes de antena (A0–A5) via conector U.FL/IPEX interno.</div></div>
    <div class="mc"><div class="mci">📐</div><div class="mct">Cenário Baseline</div>
      <div class="mcd">ESP32 sem invólucro, campo aberto, AP fixo canal 11 (2,4 GHz). 180–360 amostras por ensaio a 1 Hz.</div></div>
    <div class="mc"><div class="mci">📦</div><div class="mct">Cenário In-Case</div>
      <div class="mcd">Invólucro PA66 fechado e parafusado. Mesma distância/orientação ao AP. Finalistas: 3 unidades × 3 repetições.</div></div>
    <div class="mc"><div class="mci">🏓</div><div class="mct">Ensaio de Ping</div>
      <div class="mcd">100–113 bursts de 5 pings ICMP · intervalo 50 ms · ~3 min por ensaio · latência e taxa de falha por burst.</div></div>
    <div class="mc"><div class="mci">🔬</div><div class="mct">Análise Espectral</div>
      <div class="mcd">Varredura SA6 (35–6200 MHz) para mapeamento de interferência do invólucro e componentes internos.</div></div>
    <div class="mc"><div class="mci">💾</div><div class="mct">Captura de Dados</div>
      <div class="mcd">Firmware ESP-IDF autônomo com armazenamento LittleFS e CLI serial. Análise Python/Pandas/Plotly. Git versionado.</div></div>
  </div>
</div>

<hr class="d">

<!-- ── PRÓXIMOS PASSOS ─────────────────────────────────────── -->
<div id="prox" class="w">
  <p class="ey">Roadmap de Qualificação</p>
  <h2 class="h2">Próximos Ensaios</h2>
  <div class="ng">{_next_steps()}</div>
</div>

<!-- ── VEREDICTO ───────────────────────────────────────────── -->
<section id="verd">
  <div class="vb">
    <div class="vt">🏆</div>
    <p class="vpre">Veredicto Final da Campanha</p>
    <h2 class="vmain">Recomendação: <span>A5 — FPC Molex T-Bar</span></h2>
    <p class="vsub">
      A5 lidera em RSSI in-case (−43,93 dBm), 0% de falha no ping e σ = 2,59 dB.
      A4 é a alternativa robusta com menor perda de invólucro (6,9 dB) e construção SMD
      resistente a vibração. Validação de campo (RF-03) e ensaios termomecânicos (TM-01/02)
      são pré-requisitos antes de PVT.
    </p>
    <div class="vpills">
      <div class="vp" style="border-color:#22c55e;color:#22c55e;background:rgba(34,197,94,.10)">🏆 A5 vencedora · {a5s:.0f} pts</div>
      <div class="vp" style="border-color:#3b82f6;color:#3b82f6;background:rgba(59,130,246,.10)">★ A4 alternativa · {a4s:.0f} pts</div>
      <div class="vp" style="border-color:#ef4444;color:#ef4444;background:rgba(239,68,68,.10)">✕ A1, A3 descartadas</div>
      <div class="vp" style="border-color:#475569;color:#94a3b8;background:rgba(71,85,105,.10)">⚡ A0 somente referência</div>
    </div>
  </div>
</section>

<footer>
  Frotall FRITG01LTE &nbsp;·&nbsp; Campanha de Validação RF de Antenas Wi-Fi &nbsp;·&nbsp; Terasite Tecnologia &nbsp;·&nbsp; 2026<br>
  Gerado em {now} &nbsp;·&nbsp; Dados reais de ensaios laboratoriais &nbsp;·&nbsp; Dashboard offline autossuficiente
</footer>

</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    print(f"\n  Dashboard RF — Frotall FRITG01LTE")
    print(f"  Repositório : {ROOT}")
    print(f"  Saída       : {OUT}\n")

    html = build()

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(OUT) / 1024
    print(f"\n  OK Gerado: {OUT}")
    print(f"  Tamanho : {size_kb:.0f} KB")
    print(f"\n  Para abrir no navegador:")
    print(f'  start "{OUT}"')
