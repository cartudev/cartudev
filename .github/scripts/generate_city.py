#!/usr/bin/env python3
"""cartudev.city — isometric futuristic city of GitHub contributions (v2).

Fetches the user's contributionsCollection (GraphQL; private contributions
included when METRICS_TOKEN belongs to the owner) and renders an isometric
city: 4 districts of 13 weekly blocks, building height proportional to the
week's contributions, robots patrolling the avenues (SMIL + CSS — the only
animation layers that run inside GitHub README <img> SVGs).

Output: SVG written to argv[1] (default city.svg).
"""

import datetime as dt
import json
import os
import sys
from urllib import request

USER = os.environ.get("CITY_USER", "cartudev")
TODAY = dt.date.today()
# rolling 365-day window: exactly 52 contribution weeks ending this week
FROM_DATE = TODAY - dt.timedelta(days=364)

# ---- palette (matches README banner: dark purple + orange/pink drops) ----
BG_TOP, BG_BOT = "#0a0614", "#131034"
GRID_LINE = "#33206b"
SIDE_L, SIDE_R = "#241452", "#160b34"
PAVE = "#170d31"
LVL = [(0, "#22d3ee"), (3, "#7c3aed"), (6, "#ec4899"), (12, "#f97316"), (22, "#fde047")]
NEON = "#e879f9"
NEON2 = "#67e8f9"
ORANGE = "#fb7185"
TXT = "#cdd6f4"
MUT = "#9b8fd0"

# ---- isometric constants (higher camera: ~1.56:1) ----
W, H = 1200, 800
HW, HH = 32.0, 20.5
OX, OY = 450.0, 215.0  # iso origin: screen coords of tile (0,0)
COLS, ROWS = 13, 4     # 13 weekly blocks x 4 district rows = 52 weeks
BW, BD = 1.34, 1.10    # block footprint in tile units
GX_STEP = BW + 0.08    # gap (street) between blocks in a row
ROW_DY = 2.45          # gy pitch between district rows (block depth + avenue)


def iso(gx: float, gy: float, z: float = 0.0):
    x = OX + (gx - gy) * HW
    y = OY + (gx + gy) * HH - z
    return round(x, 1), round(y, 1)


def level_color(v: int, peak: int = 1) -> str:
    """relative thresholds so the ramp reads as a gradient"""
    t = v / max(peak, 1)
    if t == 0:
        return LVL[0][1]          # cyan (pavement day)
    if t < 0.08:
        return "#22d3ee"          # cyan
    if t < 0.25:
        return "#7c3aed"          # violet
    if t < 0.5:
        return "#ec4899"          # magenta
    if t < 0.8:
        return "#f97316"          # orange
    return "#fde047"              # yellow hot


def darken(hex_color: str, f: float) -> str:
    r = int(hex_color[1:3], 16) * f
    g = int(hex_color[3:5], 16) * f
    b = int(hex_color[5:7], 16) * f
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


# ---------------------------------------------------------------- data
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
    }
  }
}
"""


def fetch_stats(token: str) -> dict:
    body = json.dumps({
        "query": QUERY,
        "variables": {
            "login": USER,
            "from": f"{FROM_DATE.isoformat()}T00:00:00Z",
            "to": f"{TODAY.isoformat()}T23:59:59Z",
        },
    }).encode()
    req = request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "city-generator",
        },
    )
    with request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if data.get("errors"):
        raise SystemExit(f"GraphQL errors: {data['errors']}")
    return data["data"]["user"]["contributionsCollection"]


def days_flat(c: dict):
    out = []
    for w in c["contributionCalendar"]["weeks"]:
        for d in w["contributionDays"]:
            out.append(d["contributionCount"])
    return out


def weeks_and_starts(c: dict, need: int = 52):
    """weekly totals + the date of each week's monday (rolling tail)."""
    weekly, starts = [], []
    for w in c["contributionCalendar"]["weeks"]:
        counts = [d["contributionCount"] for d in w["contributionDays"]]
        dates = [d["date"] for d in w["contributionDays"]]
        weekly.append(sum(counts))
        starts.append(dt.date.fromisoformat(dates[0]) if dates else TODAY)
    # keep the LAST `need` weeks (drop oldest overflow), pad front if short
    if len(weekly) > need:
        weekly, starts = weekly[-need:], starts[-need:]
    while len(weekly) < need:
        first = starts[0] if starts else TODAY
        weekly.insert(0, 0)
        starts.insert(0, first - dt.timedelta(days=7))
    return weekly, starts


def longest_streak(flat):
    best = run = 0
    for v in flat:
        run = run + 1 if v > 0 else 0
        best = max(best, run)
    return best


# ---------------------------------------------------------------- svg helpers
def poly(pts, fill, stroke="none", sw=0.6, op=1.0, extra="", cls=None):
    s = " ".join(f"{x},{y}" for x, y in pts)
    c = f' class="{cls}"' if cls else ""
    o = f' opacity="{op}"' if op != 1 else ""
    return (f'<polygon points="{s}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}"{c}{o}{extra}/>')


def txt(x, y, s, size=13, fill=TXT, weight="normal", spacing="1", anchor="start",
        op=1.0, filter_="", family="ui-monospace,Menlo,monospace"):
    o = f' opacity="{op}"' if op != 1 else ""
    flt = f' filter="{filter_}"' if filter_ else ""
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" letter-spacing="{spacing}" '
            f'text-anchor="{anchor}"{o}{flt}>{s}</text>')


def block_outline(gx, gy, w, d, z):
    """corners of a block footprint diamond at height z."""
    N = iso(gx, gy, z)
    E = iso(gx + w, gy, z)
    S = iso(gx + w, gy + d, z)
    Wp = iso(gx, gy + d, z)
    return N, E, S, Wp


def tower(gx, gy, w, d, h, base_color, tip="", week=None, val=None, label=None):
    """One tower: side faces, glowing top; returns svg string."""
    N, E, S, Wp = block_outline(gx, gy, w, d, h)
    Nb, Eb, Sb, Wb = block_outline(gx, gy, w, d, 0)
    out = []
    out.append(poly([Wp, S, Sb, Wb], darken(base_color, 0.32), sw=0.3))
    out.append(poly([S, E, Eb, Sb], darken(base_color, 0.48), sw=0.3))
    out.append(poly([N, E, S, Wp], base_color, sw=0.8,
                    extra=' filter="url(#glow)"' if h >= 120 else ""))
    # lit windows on the two visible faces
    rnd = (gx * 7 + gy * 13) * 37 % 101
    n_win = max(2, int(h) // 26)
    for i in range(n_win):
        t = 0.22 + 0.6 * (((rnd * (i + 3)) % 97) / 97.0)
        if i % 2:
            p = iso(gx + w, gy + d - t * d, h * (0.2 + 0.55 * ((rnd * (i * 7 + 1)) % 83) / 83))
        else:
            p = iso(gx + w - t * w, gy + d, h * (0.2 + 0.55 * ((rnd * (i * 5 + 2)) % 79) / 79))
        delay = round(1.5 + ((rnd * (i * 11 + 5)) % 80) / 26.0, 2)
        out.append(f'<rect x="{p[0] - 3}" y="{p[1] - 3}" width="4" height="4.5" fill="#fde047" opacity="0.9">'
                   f'<animate attributeName="opacity" values="0.9;0.9;0.12;0.9" keyTimes="0;0.55;0.7;1" '
                   f'dur="{round(2.8 + (i % 4) * 1.15, 2)}s" begin="{delay}s" repeatCount="indefinite"/></rect>')
    if tip:
        parts_tip = [f'<g>{tip}</g>']
    seen = "".join(out)
    if label:
        # small hover tooltip (works when SVG opened as document)
        seen += f'<title>week of {label}: {val} contributions</title>'
    return seen + f'<title>week of {label}: {val} contributions</title>' if label else seen


def pad(gx, gy, w, d, stroke=GRID_LINE, sw=0.8, fill=PAVE):
    N, E, S, W = block_outline(gx, gy, w, d, 0)
    return poly([N, E, S, W], fill, stroke=stroke, sw=sw)


def bot(name, route_id, dur, begin, body, scale=2.9):
    return f'''<g>
  <animateMotion dur="{dur}" begin="{begin}" repeatCount="indefinite" rotate="0">
    <mpath href="#{route_id}"/>
  </animateMotion>
  <g transform="scale({scale})">
  <ellipse cx="0" cy="3.4" rx="7.5" ry="2.6" fill="#000" opacity="0.4"/>
  <rect x="-6.5" y="-9" width="13" height="10" rx="3" fill="{body}" stroke="#0a0614" stroke-width="1"/>
  <rect x="-4.8" y="-7.6" width="9.6" height="4" rx="1.8" fill="#0c0821" opacity="0.9"/>
  <circle cx="-2.2" cy="-5.6" r="1.1" fill="#fde047"><animate attributeName="opacity" values="1;0.1;1" dur="{dur}" repeatCount="indefinite"/></circle>
  <circle cx="2.2" cy="-5.6" r="1.1" fill="#fde047"><animate attributeName="opacity" values="1;0.1;1" dur="{dur}" repeatCount="indefinite"/></circle>
  <line x1="0" y1="-9" x2="0" y2="-13" stroke="{body}" stroke-width="1.3"/>
  <circle cx="0" cy="-14" r="1.7" fill="{NEON}"><animate attributeName="opacity" values="1;0.25;1" dur="1.05s" repeatCount="indefinite"/></circle>
  </g>
  <animateTransform attributeName="transform" type="translate" values="0 0;0 -1.8;0 0" dur="0.4s" repeatCount="indefinite" additive="sum"/>
</g>'''


# ---------------------------------------------------------------- build
def main():
    token = os.environ.get("METRICS_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("METRICS_TOKEN / GH_TOKEN not set")
    c = fetch_stats(token)
    weekly, starts = weeks_and_starts(c)
    flat = days_flat(c)
    today = TODAY
    shown_days = len(flat)
    cal_total = c["contributionCalendar"]["totalContributions"]
    prs = c["totalPullRequestContributions"]
    issues = c["totalIssueContributions"]
    reviews = c["totalPullRequestReviewContributions"]
    peak_week = max(weekly)
    peak_day = max(flat)
    best_streak = longest_streak(flat)

    # district totals: 13-week buckets over the rolling window, labeled
    # by the actual months each bucket covers (cross-year aware)
    q_tot, q_labels = [], []
    for b in range(ROWS):
        lo, hi = b * COLS, min((b + 1) * COLS, len(weekly))
        q_tot.append(sum(weekly[lo:hi]))
        s, e = starts[lo], starts[hi - 1]
        mn = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

        def tag(d):
            return f"{mn[d.month - 1]}{'' if d.year == today.year else str(d.year)[2:]}"
        q_labels.append(f"{tag(s)}–{tag(e)}")

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']
    parts.append(
        '<defs>'
        f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{BG_TOP}"/><stop offset="1" stop-color="{BG_BOT}"/></linearGradient>'
        '<filter id="glow" x="-40%" y="-40%" width="180%" height="180%">'
        '<feGaussianBlur stdDeviation="3.2" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
        '<filter id="glow2" x="-60%" y="-60%" width="220%" height="220%">'
        '<feGaussianBlur stdDeviation="6" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
        f'<radialGradient id="bean" cx="0.5" cy="0.7" r="0.75">'
        '<stop offset="0" stop-color="#7c3aed" stop-opacity="0.5"/>'
        '<stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>'
        '<style>'
        '  .tw { animation: twinkle 3s ease-in-out infinite; }'
        '  @keyframes twinkle { 0%,100% { opacity: 0.15; } 50% { opacity: 0.9; } }'
        '  .sweep { animation: sweep 12s linear infinite; }'
        f'  @keyframes sweep {{ from {{ transform: translateY(-50px); }}'
        f'  to {{ transform: translateY({H * 0.75}px); }} }}'
        '  .ticker { animation: ticker 26s linear infinite; }'
        '  @keyframes ticker { from { transform: translateX(0); } to { transform: translateX(-50%); } }'
        '</style></defs>'
    )

    # sky, stars, horizon
    parts.append(f'<rect width="{W}" height="{H}" fill="url(#sky)"/>')
    for i in range(64):
        x = (i * 21947) % (W - 20) + 10
        y = (i * 931) % 200 + 8
        r = 0.6 + (i % 3) * 0.35
        dly = round(0.4 + ((i * 13) % 90) / 30.0, 2)
        parts.append(f'<circle class="tw" cx="{x}" cy="{y}" r="{r}" fill="#e9d5ff" '
                     f'style="animation-delay:{dly}s"/>')
    parts.append(f'<ellipse cx="{W // 2}" cy="{int(OY + 180)}" rx="580" ry="160" fill="url(#bean)"/>')
    parts.append(poly([(0, 262), (150, 214), (330, 258), (520, 196), (700, 250),
                       (900, 205), (1090, 246), (1200, 220), (1200, 700), (0, 700)],
                      "#140a28", op=0.95))
    parts.append(poly([(0, 296), (220, 262), (430, 300), (700, 268), (960, 298),
                       (1200, 276), (1200, 720), (0, 720)], "#190e38", op=0.95))

    # ---- ground network: avenues + robot routes (drawn before towers) ----
    routes = {}
    for rid, row_av, direction in (("route-a", 1, "west"), ("route-b", 2, "east"), ("route-c", 3, "west")):
        gy_mid = row_av * ROW_DY - (ROW_DY - BD) / 2.0
        x1 = iso(-1.6, gy_mid)
        x2 = iso(COLS - 0.4 + 1.0, gy_mid)
        if direction == "east":
            pts = [x1, x2]
        else:
            pts = [x2, x1]
        d = f"M {pts[0][0]},{pts[0][1]} L {pts[1][0]},{pts[1][1]}"
        routes[rid] = d
        parts.append(f'<path id="{rid}" d="{d}" fill="none"/>')
        parts.append(f'<path d="{d}" fill="none" stroke="#4c1d95" stroke-width="2.4" opacity="0.5"/>')
        parts.append(f'<path d="{d}" fill="none" stroke="#22d3ee" stroke-width="0.5" stroke-dasharray="3 7" opacity="0.8"/>')
    # street compass: month labels at the true iso ends (rolling-aware)
    mn = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    start_lb = mn[starts[0].month - 1] + ("" if starts[0].year == TODAY.year else str(starts[0].year)[2:])
    end_lb = mn[starts[-1].month - 1] + ("" if starts[-1].year == TODAY.year else str(starts[-1].year)[2:])
    jan_p = iso(-1.05, 0.3)
    dec_col = (51 % COLS)
    dec_row = 51 // COLS
    dec_p = iso(dec_col * GX_STEP - 0.9 + BW + 0.12, dec_row * ROW_DY + BD * 0.5)
    parts.append(txt(jan_p[0] - 8, jan_p[1] + 4, start_lb, 8, MUT, "bold", "1", anchor="end", op=0.7))
    parts.append(txt(dec_p[0] + 8, dec_p[1] + 4, end_lb, 8, MUT, "bold", "1", anchor="start", op=0.7))

    # ---- districts (rows) & weekly blocks ----
    peak = max(max(weekly), 1)
    tags = []  # week value tags: drawn after all geometry so nothing covers them
    for idx, val in enumerate(weekly):
        row, col = divmod(idx, COLS)
        gy = row * ROW_DY
        gx = col * GX_STEP - 0.9
        if val == 0:
            parts.append(pad(gx, gy, BW, BD, stroke="#241651", sw=0.7, fill="#120a29"))
            a = iso(gx + BW / 2, gy + BD / 2)
            parts.append(f'<line x1="{a[0]}" y1="{a[1]}" x2="{a[0]}" y2="{a[1] - 8}" stroke="#241651" stroke-width="1"/>')
        else:
            parts.append(pad(gx, gy, BW, BD))
            h = 12 + ((val / peak) ** 0.5) * 285
            col_top = level_color(val, peak)
            wdate = starts[idx].isoformat()
            parts.append(tower(gx, gy, BW, BD, h, col_top, week=None, val=val, label=wdate))
            if val >= 0.4 * peak:
                t = iso(gx + BW / 2, gy + BD / 2, h + 18)
                c = level_color(val, peak)
                tags.append(
                    f'<text x="{t[0]}" y="{t[1] + 3}" font-family="ui-monospace,Menlo,monospace" '
                    f'font-size="12" font-weight="bold" fill="{c}" letter-spacing="0" '
                    f'text-anchor="middle" opacity="0.95" stroke="#05030e" '
                    f'stroke-width="2.6" paint-order="stroke">{val}</text>'
                )
    parts.extend(tags)
    # bot fleet: two to three units per avenue, staggered like real traffic
    fleet = [
        ("alpha", "route-a", "34s", "-9s", "#5eead4"),
        ("alpha2", "route-a", "34s", "-26s", "#f1f5f9"),
        ("alpha3", "route-a", "34s", "-31s", "#bef264"),
        ("beta", "route-b", "41s", "-23s", "#fb7185"),
        ("beta2", "route-b", "41s", "-37s", "#fcd34d"),
        ("gamma", "route-c", "38s", "-4s", "#7dd3fc"),
        ("gamma2", "route-c", "38s", "-19s", "#fda4af"),
        ("gamma3", "route-c", "38s", "-33s", "#c4b5fd"),
    ]
    for name, route_id, dur, begin, body in fleet:
        parts.append(bot(name, route_id, dur, begin, body))
    n_bots = len(fleet)

    # courier drone in the sky
    parts.append(
        '<g>'
        '<animateMotion dur="18s" repeatCount="indefinite" rotate="0" '
        'path="M 90,190 C 320,120 760,110 1120,150"/>'
        '<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.08;0.9;1" dur="18s" repeatCount="indefinite"/>'
        '<ellipse cx="0" cy="6" rx="9" ry="2" fill="#000" opacity="0.3"/>'
        '<path d="M -8,0 Q 0,-7 8,0 L 4,3 L -4,3 Z" fill="#e2e8f0" opacity="0.95"/>'
        '<circle cx="0" cy="0.5" r="2.2" fill="#22d3ee"><animate attributeName="opacity" values="1;0.3;1" dur="0.7s" repeatCount="indefinite"/></circle>'
        '</g>'
    )

    # scanning beam + scanlines
    parts.append(
        '<linearGradient id="beam" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#ec4899" stop-opacity="0"/>'
        '<stop offset="0.5" stop-color="#ec4899" stop-opacity="0.9"/>'
        '<stop offset="1" stop-color="#ec4899" stop-opacity="0"/></linearGradient>'
    )
    parts.append(f'<rect class="sweep" x="0" y="0" width="{W}" height="22" fill="url(#beam)" opacity="0.05"/>')
    parts.append(
        '<pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">'
        '<rect width="4" height="2" fill="#ffffff" opacity="0.016"/></pattern>'
        f'<rect width="{W}" height="{H}" fill="url(#scan)"/>'
    )

    # ---------------- HUD ----------------
    G2 = ' filter="url(#glow2)"'
    # top-left
    parts.append(f'<rect x="28" y="26" width="330" height="64" rx="10" fill="#0c0821" opacity="0.86" stroke="{NEON}" stroke-width="1"/>')
    parts.append(txt(44, 52, f"{USER}.city", 16, NEON, "bold", "2", filter_="url(#glow2)"))
    parts.append(txt(44, 74, f"rolling 365-day skyline · client + open source", 10.5, MUT, spacing="0.5"))
    # top-right: signals
    signals = [
        ("CONTRIBUTIONS 365D", cal_total),
        ("PRS OPENED", prs),
        ("ISSUES", issues),
        ("REVIEWS", reviews),
        ("BEST STREAK", f"{best_streak} days"),
    ]
    panels_h = len(signals) * 20 + 36
    nx = W - 300
    parts.append(f'<rect x="{nx - 16}" y="26" width="284" height="{panels_h}" rx="10" fill="#0c0821" opacity="0.86" stroke="{NEON2}" stroke-width="1"/>')
    parts.append(txt(nx, 50, "SIGNALS", 11, NEON2, "bold", "3"))
    yy = 68
    for label, v in signals:
        parts.append(txt(nx, yy, label, 10, MUT, spacing="0.5"))
        parts.append(txt(W - 36, yy, str(v), 12, "#f8fafc", "bold", "0", anchor="end"))
        yy += 20
    # bottom-left: districts (quarterly ramp)
    px, py, pw, ph = 28, H - 122, 332, 96
    parts.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="10" fill="#0c0821" opacity="0.86" stroke="{ORANGE}" stroke-width="1"/>')
    pt_label = "DISTRICTS — LAST 52 WKS"
    parts.append(txt(px + 16, py + 20, pt_label, 10, ORANGE, "bold", "2"))
    maxq = max(max(q_tot), 1)
    bx = px + 16
    qcols = ["#22d3ee", "#7c3aed", "#ec4899", "#f97316"]
    bar_top = py + 34
    bar_h = 36
    for i, qv in enumerate(q_tot):
        bh = max((qv / maxq) * bar_h, 3)
        parts.append(f'<rect x="{bx}" y="{bar_top + bar_h - bh}" width="34" height="{bh}" fill="{qcols[i]}" opacity="0.92"/>')
        parts.append(txt(bx + 17, py + ph - 10, q_labels[i], 7.5, MUT, anchor="middle", spacing="0.5"))
        parts.append(txt(bx + 17, bar_top + bar_h - bh - 4, f"{qv}", 9, "#f8fafc", "bold", "0", anchor="middle"))
        bx += 54
    # bottom-right: peak info
    rx = W - 302
    parts.append(f'<rect x="{rx - 16}" y="{py}" width="284" height="96" rx="10" fill="#0c0821" opacity="0.86" stroke="{NEON}" stroke-width="1"/>')
    parts.append(txt(rx, py + 22, "RUNTIME", 10, NEON, "bold", "2"))
    for j, (k, v) in enumerate([("PEAK DAY", peak_day), ("PEAK WEEK", peak_week), ("CITY BOTS", n_bots)]):
        parts.append(txt(rx, py + 42 + j * 20, k, 10, MUT, spacing="0.5"))
        parts.append(txt(W - 36, py + 42 + j * 20, str(v), 12, "#f8fafc", "bold", "0", anchor="end"))

    # ticker
    tick = (f"{USER}@metrics:~$ rebuilt-the-team-workflow → everyone ships through the pipeline · "
            f"{cal_total:,} contributions in the last 365 days · refresh daily by github actions · ")
    parts.append(
        f'<rect x="0" y="{H - 20}" width="{W}" height="20" fill="#0a0614" opacity="0.88"/>'
        f'<g class="ticker"><text x="0" y="{H - 6}" font-family="monospace" font-size="11" '
        f'fill="#8f7ad6">{tick}{tick}</text></g>'
    )
    parts.append('</svg>')

    svg = "".join(parts)
    out = sys.argv[1] if len(sys.argv) > 1 else "city.svg"
    with open(out, "w") as f:
        f.write(svg)
    print(f"wrote {out} ({len(svg)} bytes) — total {cal_total}, peak wk {peak_week}, "
          f"peak day {peak_day}, quarters {q_tot}")


if __name__ == "__main__":
    main()
