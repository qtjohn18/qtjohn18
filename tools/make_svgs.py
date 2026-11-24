"""Generate the animated SVG panels used by the profile README.

Usage:  python tools/make_svgs.py        (writes into ./assets)

Animations use CSS and SMIL, both of which render in GitHub READMEs. Every
animated element also has a sensible static fallback.
"""
import colorsys
import html
import math
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "assets")

BG = "#0a0e14"
PANEL = "#0f151d"
PANEL2 = "#18222e"
BORDER = "#223040"
GRID = "#18232f"
TEXT = "#d6dfe9"
DIM = "#728196"
AMBER = "#ffb02e"
GREEN = "#1fd48c"
RED = "#ff5a6e"
CYAN = "#4cc9f0"
BLUE = "#82aaff"
PURPLE = "#c792ea"
FONT = ("ui-monospace,'JetBrains Mono','Fira Code','Cascadia Code',"
        "Consolas,Menlo,'Courier New',monospace")
CW = 0.602  # monospace advance width, in em

BASE_CSS = """
text{font-family:FONT}
.o{animation:show .25s ease-out both}
.f{animation:show .35s ease-out both}
@keyframes show{from{opacity:0}to{opacity:1}}
.pulse{animation:pulse 1.6s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
.blink{animation:blink 1.05s step-end infinite}
@keyframes blink{0%{opacity:1}50%{opacity:0}}
.grow{animation:grow .7s cubic-bezier(.2,.8,.2,1) both;transform-box:fill-box;transform-origin:0 50%}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.pop{animation:pop .5s ease-out both;transform-box:fill-box;transform-origin:50% 50%}
@keyframes pop{0%{transform:scale(0)}70%{transform:scale(1.25)}100%{transform:scale(1)}}
""".replace("FONT", FONT)

GLOW = ('<filter id="glow2" x="-30%" y="-80%" width="160%" height="260%">'
        '<feGaussianBlur stdDeviation="2.2" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')


def esc(s):
    # SVG collapses runs of spaces; non-breaking spaces keep the column layout.
    return html.escape(s, quote=True).replace("  ", "  ")


def text(x, y, s, size=13, fill=TEXT, weight=None, anchor=None, ls=None,
         cls=None, style=None, opacity=None, extra=""):
    a = [f'x="{x:.1f}"', f'y="{y:.1f}"', f'font-size="{size}"', f'fill="{fill}"']
    if weight:
        a.append(f'font-weight="{weight}"')
    if anchor:
        a.append(f'text-anchor="{anchor}"')
    if ls:
        a.append(f'letter-spacing="{ls}"')
    if cls:
        a.append(f'class="{cls}"')
    if style:
        a.append(f'style="{style}"')
    if opacity is not None:
        a.append(f'opacity="{opacity}"')
    if extra:
        a.append(extra)
    return f'<text {" ".join(a)}>{esc(s)}</text>'


def pts_str(pts):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def hsl_lerp(c1, c2, t):
    def to_hls(c):
        return colorsys.rgb_to_hls(*(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)))
    h1, l1, s1 = to_hls(c1)
    h2, l2, s2 = to_hls(c2)
    r, g, b = colorsys.hls_to_rgb(h1 + (h2 - h1) * t, l1 + (l2 - l1) * t, s1 + (s2 - s1) * t)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def doc(w, h, title, css, defs, body, rx=10, scan=True):
    if scan:  # faint CRT scanlines over everything
        defs = defs + ['<pattern id="scan" width="4" height="3" patternUnits="userSpaceOnUse">'
                       '<rect width="4" height="1" fill="#000" opacity=".22"/></pattern>']
        body = body + [f'<rect width="{w}" height="{h}" rx="{rx}" fill="url(#scan)"/>']
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">\n'
        f"<title>{esc(title)}</title>\n"
        f"<style>{BASE_CSS}{css}</style>\n"
        f"<defs>{''.join(defs)}</defs>\n" + "\n".join(body) + "\n</svg>\n"
    )


def window(w, h, left=None, right=None, right_fill=DIM, bar=30):
    """Rounded terminal window with a title bar. Returns (defs, body)."""
    defs = [f'<clipPath id="win"><rect width="{w}" height="{h}" rx="10"/></clipPath>']
    body = [
        '<g clip-path="url(#win)">',
        f'<rect width="{w}" height="{h}" fill="{BG}"/>',
        f'<rect width="{w}" height="{bar}" fill="{PANEL}"/>',
        f'<line x1="0" y1="{bar + .5}" x2="{w}" y2="{bar + .5}" stroke="{BORDER}"/>',
        "</g>",
        f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="10" fill="none" stroke="{BORDER}"/>',
    ]
    if left:
        body.append(text(16, 19.5, left, 11.5, AMBER, 700, ls=1.6))
    if right:
        body.append(text(w - 16, 19.5, right, 11, right_fill, anchor="end", ls=1.2))
    return defs, body


def typing_clip(cid, x, y, s, size, start, per):
    """clipPath that reveals `s` one character at a time (SMIL, discrete).

    The rect's base width is the full text width, so a renderer without SMIL
    simply shows the whole text. The animation runs from t=0 and holds the
    width at 0 until `start`, so nothing flashes before typing begins.
    """
    n, cw = len(s), size * CW
    full = n * cw + 10
    total = start + (n + 1) * per + 0.05
    vals, kts = [0.0], [0.0]
    for k in range(1, n + 1):
        vals.append(k * cw)
        kts.append((start + k * per) / total)
    vals.append(full)
    kts.append((start + (n + 1) * per) / total)
    v = ";".join(f"{a:.1f}" for a in vals)
    t = ";".join(f"{a:.4f}" for a in kts)
    clip = (
        f'<clipPath id="{cid}"><rect x="{x - 2}" y="{y - size}" height="{size * 1.6}" '
        f'width="{full:.1f}"><animate attributeName="width" dur="{total:.2f}s" '
        f'calcMode="discrete" values="{v}" keyTimes="{t}" fill="freeze"/></rect></clipPath>'
    )
    return clip, start + (n + 1) * per


def digit_strip(cid, x, y, seq, unit, fs, fill, weight=700):
    """One odometer digit that steps through `seq`, `unit` seconds per step."""
    LH = round(fs * 1.25)
    n = len(seq)
    vals = ";".join(f"0 {-k * LH}" for k in range(n))
    kts = ";".join(f"{k / n:.4f}" for k in range(n))
    clip = (f'<clipPath id="{cid}"><rect x="{x - 1:.1f}" y="{y - fs * 0.95:.1f}" '
            f'width="{fs * CW + 2:.1f}" height="{LH - 1}"/></clipPath>')
    strip = "".join(text(x, y + k * LH, str(d), fs, fill, weight) for k, d in enumerate(seq))
    body = (f'<g clip-path="url(#{cid})"><g><animateTransform attributeName="transform" '
            f'type="translate" calcMode="discrete" values="{vals}" keyTimes="{kts}" '
            f'dur="{n * unit}s" repeatCount="indefinite"/>{strip}</g></g>')
    return clip, body


def cycle_texts(states_text, x, y, size, fill, weight=None, anchor=None, kt=None, dur=12):
    """Several texts in one spot, each shown during its own keyframe window."""
    n = len(states_text)
    kt = kt or [i / n for i in range(n)] + [1]
    kts = ";".join(f"{k:.3f}" for k in kt)
    out = []
    for s, t in enumerate(states_text):
        vals = ";".join(["1" if i == s else "0" for i in range(n)] + ["1" if s == 0 else "0"])
        a = [f'x="{x:.1f}"', f'y="{y:.1f}"', f'font-size="{size}"', f'fill="{fill}"',
             f'opacity="{1 if s == 0 else 0}"']  # static fallback shows the first state
        if weight:
            a.append(f'font-weight="{weight}"')
        if anchor:
            a.append(f'text-anchor="{anchor}"')
        out.append(f'<text {" ".join(a)}><animate attributeName="opacity" calcMode="discrete" '
                   f'values="{vals}" keyTimes="{kts}" dur="{dur}s" repeatCount="indefinite"/>'
                   f"{esc(t)}</text>")
    return out


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_price(S, K, T, sig, call=True):
    if T <= 0:
        return max(S - K, 0.0) if call else max(K - S, 0.0)
    d1 = (math.log(S / K) + 0.5 * sig * sig * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    return S * ncdf(d1) - K * ncdf(d2) if call else K * ncdf(-d2) - S * ncdf(-d1)


def nice_tick(span, n=5):
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    return min(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)


# --------------------------------------------------------------------------
def header():
    W, H = 840, 336
    NAME, NX, NY, NS = "ALEXANDRU BUCUR", 32, 84, 38
    css = """
.cur{animation:show .01s linear both,blink 1.05s step-end infinite}
.nm{animation:nm 6s steps(1,end) .9s infinite}
@keyframes nm{0%{opacity:1}11%{opacity:.55}13%{opacity:1}100%{opacity:1}}
.g1,.g2,.g3,.g4{opacity:0}
.g1{animation:g1 6s steps(1,end) .9s infinite}
.g2{animation:g2 6s steps(1,end) .9s infinite}
.g3{animation:g3 6s steps(1,end) .9s infinite}
.g4{animation:g4 6s steps(1,end) .9s infinite}
@keyframes g1{0%{opacity:0;transform:none}10%{opacity:.85;transform:translate(-5px,1px)}12%{transform:translate(3px,-1px)}14%{transform:translate(-2px,0)}16%{opacity:0;transform:none}100%{opacity:0;transform:none}}
@keyframes g2{0%{opacity:0;transform:none}10%{opacity:.85;transform:translate(5px,-1px)}12%{transform:translate(-3px,1px)}14%{transform:translate(2px,0)}16%{opacity:0;transform:none}100%{opacity:0;transform:none}}
@keyframes g3{0%{opacity:0;transform:none}11%{opacity:1;transform:translate(11px,0)}13%{transform:translate(-8px,0)}15%{opacity:0;transform:none}100%{opacity:0;transform:none}}
@keyframes g4{0%{opacity:0;transform:none}12%{opacity:1;transform:translate(-9px,0)}14%{opacity:0;transform:none}100%{opacity:0;transform:none}}
.sweep{animation:sweep 7s linear infinite}
@keyframes sweep{from{transform:translateY(0)}to{transform:translateY(SWEEPpx)}}
.ekg{animation:ekg 16s linear infinite}
@keyframes ekg{from{transform:translateX(0)}to{transform:translateX(-EKGpx)}}
""".replace("SWEEP", str(H + 90)).replace("EKG", str(W))
    defs, b = window(W, H)
    defs += [
        '<filter id="glow" x="-10%" y="-60%" width="120%" height="220%">'
        '<feGaussianBlur stdDeviation="5" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
        GLOW,
        f'<clipPath id="sl1"><rect y="{NY - 19}" width="{W}" height="7"/></clipPath>',
        f'<clipPath id="sl2"><rect y="{NY - 9}" width="{W}" height="4"/></clipPath>',
        f'<clipPath id="ek"><rect x="24" y="116" width="{W - 48}" height="40"/></clipPath>',
        '<linearGradient id="sw" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset=".5" stop-color="#fff" stop-opacity=".045"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>',
        '<radialGradient id="vig" cx=".5" cy=".45" r=".75">'
        '<stop offset=".6" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#000" stop-opacity=".45"/></radialGradient>',
        f'<linearGradient id="fl"><stop offset="0" stop-color="{BG}"/>'
        f'<stop offset="1" stop-color="{BG}" stop-opacity="0"/></linearGradient>',
        f'<linearGradient id="fr"><stop offset="0" stop-color="{BG}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{BG}"/></linearGradient>',
    ]
    for i, c in enumerate((RED, AMBER, GREEN)):
        b.append(f'<circle cx="{20 + i * 18}" cy="15" r="5.5" fill="{c}"/>')
    b.append(text(W / 2, 19.5, "qtjohn18@qt-terminal: ~", 12, DIM, anchor="middle"))

    # name: glow + periodic RGB-split glitch with displaced slices
    name_attrs = dict(size=NS, weight=700, ls=4)
    b.append(f'<g filter="url(#glow)">{text(NX, NY, NAME, fill=AMBER, cls="nm", **name_attrs)}</g>')
    b.append(text(NX, NY, NAME, fill=RED, cls="g1", **name_attrs))
    b.append(text(NX, NY, NAME, fill=CYAN, cls="g2", **name_attrs))
    b.append(f'<g clip-path="url(#sl1)">{text(NX, NY, NAME, fill=TEXT, cls="g3", **name_attrs)}</g>')
    b.append(f'<g clip-path="url(#sl2)">{text(NX, NY, NAME, fill=AMBER, cls="g4", **name_attrs)}</g>')
    b.append(text(34, 111, "QUANT TRADER  /  QUANT DEVELOPER", 12.5, DIM, ls=2.5))

    b.append(f'<line x1="556.5" y1="52" x2="556.5" y2="114" stroke="{BORDER}"/>')
    rx, vx = 576, 662
    for y, lab in ((64, "SESSION"), (87, "VENUES"), (110, "STACK")):
        b.append(text(rx, y, lab, 11.5, DIM, ls=1.5))
    b.append(f'<g filter="url(#glow2)"><circle class="pulse" cx="{vx + 4}" cy="59.8" r="4" fill="{GREEN}"/>'
             + text(vx + 14, 64, "LIVE", 12, GREEN, 700, ls=2) + "</g>")
    b.append(text(vx, 87, "IBKR · NinjaTrader 8", 12, TEXT))
    b.append(text(vx, 110, "PY · C++ · RUST · C#", 12, TEXT))

    # heartbeat line as the divider: a periodic random walk scrolling left
    rnd = random.Random(3)
    n, yc = 84, 136
    ys, v = [], 0.0
    for _ in range(n):
        v = v * 0.7 + rnd.gauss(0, 2.0)
        ys.append(v)
    for k in rnd.sample(range(4, n - 4), 5):
        ys[k] += rnd.choice((-1, 1)) * rnd.uniform(6, 9)
    ys.append(ys[0])
    d = "M" + " L".join(f"{k * W / n:.1f},{yc + max(-14, min(14, y)):.1f}" for k, y in enumerate(ys))
    b.append(f'<line x1="24" y1="{yc + .5}" x2="{W - 24}" y2="{yc + .5}" stroke="{GRID}"/>')
    b.append(f'<g clip-path="url(#ek)"><g class="ekg" filter="url(#glow2)">'
             f'<path d="{d}" fill="none" stroke="{CYAN}" stroke-width="1.2" opacity=".6"/>'
             f'<path d="{d}" transform="translate({W},0)" fill="none" stroke="{CYAN}" stroke-width="1.2" opacity=".6"/>'
             "</g></g>")
    b.append(f'<rect x="24" y="116" width="70" height="40" fill="url(#fl)"/>')
    b.append(f'<rect x="{W - 94}" y="116" width="70" height="40" fill="url(#fr)"/>')

    fs, per, x0 = 14, 0.06, 54
    script = [
        ("whoami", 0.6,
         "quant trader & developer — building my own trading infrastructure", TEXT),
        ("cat markets.txt", 1.8, "options · futures · crypto · stocks", AMBER),
        ("ls ~/desks", 3.4,
         "options/  hft/  market-making/  prop-firm-cycling/  macro-news/", CYAN),
    ]
    y, done = 172, 0.0
    for i, (cmd, start, out, col) in enumerate(script):
        b.append(text(32, y, "❯", fs, GREEN, 700, cls="o",
                      style=f"animation-delay:{0 if i == 0 else start - 0.3:.2f}s"))
        clip, done = typing_clip(f"ty{i}", x0, y, cmd, fs, start, per)
        defs.append(clip)
        b.append(f'<text x="{x0}" y="{y}" font-size="{fs}" fill="{TEXT}" font-weight="600" '
                 f'clip-path="url(#ty{i})">{esc(cmd)}</text>')
        b.append(text(x0, y + 23, out, 13.5, col, cls="o",
                      style=f"animation-delay:{done + 0.15:.2f}s"))
        y += 50
    last = done + 0.5
    b.append(text(32, y, "❯", fs, GREEN, 700, cls="o", style=f"animation-delay:{last:.2f}s"))
    b.append(f'<rect class="cur" style="animation-delay:{last:.2f}s,{last:.2f}s" '
             f'x="{x0}" y="{y - 12}" width="8.5" height="15" fill="{GREEN}" filter="url(#glow2)"/>')

    # CRT sweep + vignette
    b.append(f'<g clip-path="url(#win)"><rect class="sweep" y="-90" width="{W}" height="90" fill="url(#sw)"/>'
             f'<rect width="{W}" height="{H}" fill="url(#vig)"/></g>')
    return doc(W, H, "Terminal: Alexandru Bucur, quant trader and quant developer",
               css, defs, b)


# --------------------------------------------------------------------------
def ticker():
    W, H, L = 840, 40, 104
    items = [
        ("PY", "python", "▲", GREEN), ("CPP", "c++", "▲", GREEN),
        ("RS", "rust", "▲", GREEN), ("CS", "c#", "▲", GREEN),
        ("IBKR", "broker api", "▲", GREEN), ("NT8", "ninjatrader", "▲", GREEN),
        ("LAT", "latency", "▼", RED), ("OPT", "options", "▲", GREEN),
        ("FUT", "futures", "▲", GREEN), ("BTC", "crypto", "▲", GREEN),
        ("EQ", "stocks", "▲", GREEN), ("SLIP", "slippage", "▼", RED),
        ("HFT", "low-latency", "▲", GREEN), ("MM", "bid/ask", "▲", GREEN),
        ("PROP", "cycling", "▲", GREEN), ("MACRO", "news", "▲", GREEN),
        ("DD", "drawdown", "▼", RED), ("BT", "backtest", "▲", GREEN),
        ("EXEC", "execution", "▲", GREEN), ("FLOW", "options flow", "▲", GREEN),
    ]
    fs = 13
    cw = fs * CW
    parts, x = [], 0.0
    for sym, lab, arr, col in items:
        parts.append(text(x, 25, sym, fs, AMBER, 700))
        x2 = x + len(sym) * cw + 7
        parts.append(text(x2, 24.5, arr, fs - 2, col))
        x3 = x2 + cw + 6
        parts.append(text(x3, 25, lab.upper(), fs, TEXT, ls=0.5))
        x = x3 + len(lab) * (cw + 0.5) + 22
        parts.append(text(x - 13, 25, "·", fs, DIM))
        x += 4
    P = x
    copy = "".join(parts)
    defs = [
        f'<clipPath id="strip"><rect width="{W}" height="{H}" rx="8"/></clipPath>',
        f'<clipPath id="tape"><rect x="{L}" width="{W - L}" height="{H}"/></clipPath>',
        f'<linearGradient id="fl"><stop offset="0" stop-color="{BG}"/>'
        f'<stop offset="1" stop-color="{BG}" stop-opacity="0"/></linearGradient>',
        f'<linearGradient id="fr"><stop offset="0" stop-color="{BG}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{BG}"/></linearGradient>',
    ]
    b = [
        '<g clip-path="url(#strip)">',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        f'<g clip-path="url(#tape)"><g transform="translate({L + 16},0)"><g>'
        f'<animateTransform attributeName="transform" type="translate" from="0 0" '
        f'to="{-P:.1f} 0" dur="{P / 45:.1f}s" repeatCount="indefinite"/>'
        f'{copy}<g transform="translate({P:.1f},0)">{copy}</g></g></g></g>',
        f'<rect x="{L}" width="30" height="{H}" fill="url(#fl)"/>',
        f'<rect x="{W - 50}" width="50" height="{H}" fill="url(#fr)"/>',
        f'<rect width="{L}" height="{H}" fill="{AMBER}"/>',
        text(L / 2, 24.5, "◆ TAPE", 12, BG, 700, anchor="middle", ls=2),
        "</g>",
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="8" fill="none" stroke="{BORDER}"/>',
    ]
    return doc(W, H, "Scrolling ticker tape of skills and markets", "", defs, b, rx=8, scan=False)


# --------------------------------------------------------------------------
AS_GAMMA, AS_K, AS_SIGMA, AS_TAU, AS_QMAX = 0.3, 1.0, 1.0, 1.0, 4


def as_quotes(s, q, sigma=AS_SIGMA, gamma=AS_GAMMA, k=AS_K, tau=AS_TAU):
    """Avellaneda-Stoikov reservation price and optimal bid/ask."""
    r = s - q * gamma * sigma ** 2 * tau
    spread = gamma * sigma ** 2 * tau + (2 / gamma) * math.log(1 + gamma / k)
    return r, r - spread / 2, r + spread / 2


def market():
    """Candles with an Avellaneda-Stoikov market maker running on them."""
    W, H = 840, 332
    rnd = random.Random(206)  # price path picked so the market maker's run is a clean one
    N = 46
    o, cs = 104.0, []
    for _ in range(N):
        c = o + rnd.gauss(0.16, 0.95)
        h = max(o, c) + abs(rnd.gauss(0, 0.5))
        lo_ = min(o, c) - abs(rnd.gauss(0, 0.5))
        cs.append((o, h, lo_, c))
        o = c

    # run the market maker bar by bar: quote around the open, fill on the range
    q, cash, nfill = 0, 0.0, 0
    quotes, fills, inv, pnl = [], [], [], []
    for i, (o, h, l, c) in enumerate(cs):
        r, bid, ask = as_quotes(o, q)
        quotes.append((r, bid, ask))
        if q < AS_QMAX and l <= bid:
            q += 1
            cash -= bid
            fills.append((i, 1, bid))
        if q > -AS_QMAX and h >= ask:
            q -= 1
            cash += ask
            fills.append((i, -1, ask))
        inv.append(q)
        pnl.append(cash + q * c)
    nfill = len(fills)
    lc = cs[-1][3]
    r_now, bid_now, ask_now = as_quotes(lc, q)

    x0, x1, y0, y1 = 18.0, 514.0, 62.0, 222.0
    lo = min(min(c[2] for c in cs), min(qq[1] for qq in quotes), bid_now)
    hi = max(max(c[1] for c in cs), max(qq[2] for qq in quotes), ask_now)
    pad = (hi - lo) * 0.04
    lo, hi = lo - pad, hi + pad

    def py(p):
        return y1 - (p - lo) / (hi - lo) * (y1 - y0)

    step = (x1 - x0) / N
    bw = step * 0.5

    def cx_(i):
        return x0 + step * (i + 0.5)

    d_all = N * 0.045  # time for the bars + quotes to sweep in
    css = """
.knob{animation:knob .45s cubic-bezier(.3,1.4,.5,1) .25s both}
@keyframes knob{from{transform:translateX(-15px)}to{transform:none}}
.pill{animation:show .3s ease-out .35s both}
"""
    defs, b = window(W, H, "MARKET ▸ QT/ALPHA · 5m")
    defs.append(GLOW)
    # A-S switch in the title bar, flipping on at load
    px0 = W - 128
    b.append(f'<rect x="{px0}" y="8" width="30" height="15" rx="7.5" fill="{PANEL2}" stroke="{BORDER}"/>')
    b.append(f'<rect class="pill" x="{px0}" y="8" width="30" height="15" rx="7.5" fill="{GREEN}" '
             f'fill-opacity=".28" stroke="{GREEN}"/>')
    b.append(f'<circle class="knob" cx="{px0 + 22.5}" cy="15.5" r="5" fill="{GREEN}" filter="url(#glow2)"/>')
    b.append(text(px0 + 38, 19.5, "A-S MM", 11, TEXT, 700, ls=1))
    b.append(f'<g filter="url(#glow2)">{text(W - 16, 19.5, "ON", 11, GREEN, 700, anchor="end", ls=1.5, cls="o", style="animation-delay:.5s")}</g>')

    # grid + price axis
    tick = nice_tick(hi - lo)
    p = math.ceil(lo / tick) * tick
    while p < hi:
        yy = py(p)
        b.append(f'<line x1="{x0}" y1="{yy:.1f}" x2="{x1}" y2="{yy:.1f}" stroke="{GRID}"/>')
        b.append(text(x1 + 8, yy + 4, f"{p:.2f}", 10.5, DIM))
        p += tick
    for i in range(0, N + 1, 8):
        xx = x0 + i * step
        b.append(f'<line x1="{xx:.1f}" y1="{y0 - 6}" x2="{xx:.1f}" y2="312" stroke="{GRID}"/>')

    # legend
    b.append(text(x0, 49, "◆ AVELLANEDA–STOIKOV", 10.5, AMBER, 700, ls=1))
    b.append(text(x0 + 160, 49, f"γ {AS_GAMMA}  k {AS_K}  σ {AS_SIGMA}", 10.5, DIM))
    b.append(text(x1, 49, f"r {r_now:.2f}  δ {ask_now - bid_now:.2f}  q {q:+d}", 10.5, TEXT,
                  anchor="end"))

    # quotes: band between bid/ask, step lines, reservation price
    def steps(vals):
        out = []
        for i, v in enumerate(vals):
            out += [(x0 + i * step, py(v)), (x0 + (i + 1) * step, py(v))]
        return out

    ask_pts = steps([qq[2] for qq in quotes])
    bid_pts = steps([qq[1] for qq in quotes])
    res_pts = steps([qq[0] for qq in quotes])
    defs.append(
        f'<clipPath id="sweep"><rect x="{x0}" y="30" width="{x1 - x0 + 60}" height="{H - 30}">'
        f'<animate attributeName="width" values="0;{x1 - x0 + 60}" keyTimes="0;1" '
        f'dur="{d_all + 0.5:.2f}s" fill="freeze"/></rect></clipPath>'
    )
    b.append(
        '<g clip-path="url(#sweep)">'
        f'<polygon points="{pts_str(ask_pts + bid_pts[::-1])}" fill="{CYAN}" opacity=".07"/>'
        f'<polyline points="{pts_str(ask_pts)}" fill="none" stroke="{RED}" stroke-width="1.2" opacity=".6"/>'
        f'<polyline points="{pts_str(bid_pts)}" fill="none" stroke="{GREEN}" stroke-width="1.2" opacity=".6"/>'
        f'<polyline points="{pts_str(res_pts)}" fill="none" stroke="{AMBER}" stroke-width="1.3" '
        f'stroke-dasharray="4 3" opacity=".9"/>'
    )
    # live quotes reaching out to the axis
    xe = x0 + N * step
    for v, col in ((ask_now, RED), (bid_now, GREEN), (r_now, AMBER)):
        dash = ' stroke-dasharray="4 3"' if col == AMBER else ""
        b.append(f'<line x1="{xe:.1f}" y1="{py(v):.1f}" x2="{x1 + 4}" y2="{py(v):.1f}" '
                 f'stroke="{col}" stroke-width="1.2"{dash}/>')
    b.append("</g>")

    # candles
    for i, (o, h, l, c) in enumerate(cs):
        cx = cx_(i)
        col = GREEN if c >= o else RED
        top, bot = py(max(o, c)), py(min(o, c))
        b.append(
            f'<g class="f" style="animation-delay:{i * 0.045:.3f}s">'
            f'<line x1="{cx:.1f}" y1="{py(h):.1f}" x2="{cx:.1f}" y2="{py(l):.1f}" stroke="{col}" opacity=".85"/>'
            f'<rect x="{cx - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(bot - top, 1.3):.1f}" '
            f'fill="{col}" opacity=".85"/></g>'
        )

    # fills: buys at the bid (green, pointing up), sells at the ask (red, down)
    for i, side, price in fills:
        cx, yy = cx_(i), py(price)
        if side > 0:
            tri = f"{cx - 4:.1f},{yy + 7:.1f} {cx + 4:.1f},{yy + 7:.1f} {cx:.1f},{yy + 1:.1f}"
            col = GREEN
        else:
            tri = f"{cx - 4:.1f},{yy - 7:.1f} {cx + 4:.1f},{yy - 7:.1f} {cx:.1f},{yy - 1:.1f}"
            col = RED
        b.append(f'<polygon class="pop" style="animation-delay:{i * 0.045 + 0.2:.3f}s" '
                 f'points="{tri}" fill="{col}" stroke="{BG}" stroke-width=".8"/>')

    # tags for the live quotes on the axis (pushed apart so they never overlap)
    tags = sorted([(py(ask_now), RED, ask_now, "A"), (py(bid_now), GREEN, bid_now, "B")])
    if tags[1][0] - tags[0][0] < 15:
        mid = (tags[0][0] + tags[1][0]) / 2
        tags = [(mid - 7.5,) + tags[0][1:], (mid + 7.5,) + tags[1][1:]]
    for ty, col, v, lab in tags:
        b.append(
            f'<g class="o" style="animation-delay:{d_all:.2f}s">'
            f'<rect x="{x1 + 4}" y="{ty - 7:.1f}" width="54" height="14" rx="2" fill="{col}"/>'
            + text(x1 + 31, ty + 3.6, f"{lab} {v:.2f}", 9.5, BG, 700, anchor="middle") + "</g>"
        )

    # ---- inventory + PnL pane ---------------------------------------------
    sy0, sy1, zy, u = 238.0, 312.0, 276.0, 6.0
    b.append(f'<line x1="{x0}" y1="{sy0 - 7}" x2="{x1}" y2="{sy0 - 7}" stroke="{BORDER}" stroke-dasharray="2 3"/>')
    b.append(text(x0, sy0 + 6, "INVENTORY q", 9.5, DIM, ls=1))
    b.append(text(x0 + 96, sy0 + 6, f"FILLS {nfill}  ·  |q| ≤ {AS_QMAX}", 9.5, DIM, ls=0.5))
    b.append(text(x1, sy0 + 6, "━ PnL", 9.5, CYAN, 700, anchor="end", ls=1))
    b.append(f'<line x1="{x0}" y1="{zy}" x2="{x1}" y2="{zy}" stroke="{BORDER}"/>')
    for sgn in (1, -1):
        yy = zy - sgn * AS_QMAX * u
        b.append(f'<line x1="{x0}" y1="{yy}" x2="{x1}" y2="{yy}" stroke="{GRID}" stroke-dasharray="2 3"/>')
        b.append(text(x1 + 8, yy + 3.5, f"{sgn * AS_QMAX:+d}", 9.5, DIM))
    for i, qi in enumerate(inv):
        if qi == 0:
            continue
        col = GREEN if qi > 0 else RED
        y_top = zy - max(qi, 0) * u
        b.append(f'<rect class="f" style="animation-delay:{i * 0.045:.3f}s" x="{cx_(i) - bw / 2:.1f}" '
                 f'y="{y_top:.1f}" width="{bw:.1f}" height="{abs(qi) * u:.1f}" fill="{col}" fill-opacity=".5"/>')
    pmin, pmax = min(min(pnl), 0), max(pnl)
    ppts = [(cx_(i), sy1 - 4 - (v - pmin) / (pmax - pmin) * (sy1 - sy0 - 16)) for i, v in enumerate(pnl)]
    plen = sum(math.dist(ppts[i], ppts[i + 1]) for i in range(len(ppts) - 1))
    css += (".pnl{animation:draw %.2fs linear both}"
            "@keyframes draw{from{stroke-dashoffset:%.0f}to{stroke-dashoffset:0}}" % (d_all, plen))
    b.append(f'<polyline class="pnl" points="{pts_str(ppts)}" fill="none" stroke="{CYAN}" '
             f'stroke-width="1.6" stroke-linejoin="round" stroke-dasharray="{plen:.0f}" filter="url(#glow2)"/>')
    ex, ey = ppts[-1]
    b.append(f'<circle class="pulse" cx="{ex:.1f}" cy="{ey:.1f}" r="3" fill="{CYAN}"/>')

    # ---- order book -------------------------------------------------------
    sx, bx0, bx1 = 574.5, 592, 824
    b.append(f'<line x1="{sx}" y1="31" x2="{sx}" y2="{H - 1}" stroke="{BORDER}"/>')
    b.append(text(bx0, 49, "L2 ▸ DEPTH OF BOOK", 10.5, AMBER, 700, ls=1.2))
    b.append(text(bx0, 63, "PRICE", 9.5, DIM, ls=1))
    b.append(text(bx1, 63, "SIZE", 9.5, DIM, anchor="end", ls=1))
    tk = 0.25
    best_ask = math.floor(lc / tk) * tk + tk
    best_bid = best_ask - tk
    my_ask = min(max(best_ask, math.ceil(ask_now / tk) * tk), best_ask + 7 * tk)
    my_bid = max(min(best_bid, math.floor(bid_now / tk) * tk), best_bid - 7 * tk)
    rows = [(best_ask + tk * k, RED, k == 0) for k in range(7, -1, -1)]
    rows += [(best_bid - tk * k, GREEN, k == 0) for k in range(8)]
    maxw = 140
    y = 80.0
    for idx, (price, col, best) in enumerate(rows):
        if idx == 8:  # spread row
            b.append(f'<line x1="{bx0}" y1="{y - 6:.1f}" x2="{bx1}" y2="{y - 6:.1f}" '
                     f'stroke="{GRID}" stroke-dasharray="3 3"/>')
            b.append(f'<rect x="{(bx0 + bx1) / 2 - 48}" y="{y - 14:.1f}" width="96" height="15" fill="{BG}"/>')
            b.append(text((bx0 + bx1) / 2, y - 2.5, f"SPREAD {tk:.2f}", 10, AMBER,
                          700, anchor="middle", ls=1))
            y += 15
        ws = [rnd.uniform(0.18, 1.0) * maxw for _ in range(5)]
        ws.append(ws[0])
        dur = rnd.uniform(2.6, 5.4)
        b.append(text(bx0, y, f"{price:.2f}", 11, col, 700 if best else None))
        b.append(
            f'<g transform="translate({bx1},{y - 9:.1f}) scale(-1,1)">'
            f'<rect width="{ws[0]:.1f}" height="10" fill="{col}" opacity="{.55 if best else .25}">'
            f'<animate attributeName="width" values="{";".join(f"{w:.1f}" for w in ws)}" '
            f'dur="{dur:.2f}s" begin="-{rnd.uniform(0, dur):.2f}s" repeatCount="indefinite"/>'
            "</rect></g>"
        )
        fd = rnd.uniform(2.5, 7.0)
        b.append(
            f'<rect x="{bx0 - 6}" y="{y - 11:.1f}" width="{bx1 - bx0 + 12}" height="13" rx="2" '
            f'fill="{col}" opacity="0"><animate attributeName="opacity" values="0;0;.28;0" '
            f'keyTimes="0;.86;.9;1" dur="{fd:.2f}s" begin="-{rnd.uniform(0, fd):.2f}s" '
            f'repeatCount="indefinite"/></rect>'
        )
        if abs(price - my_ask) < 1e-9 or abs(price - my_bid) < 1e-9:  # our resting quote
            b.append(f'<g class="o" style="animation-delay:{d_all:.2f}s">'
                     f'<rect x="{bx0 - 7}" y="{y - 11.5:.1f}" width="{bx1 - bx0 + 14}" height="14" rx="2" '
                     f'fill="none" stroke="{AMBER}" stroke-opacity=".8"/>'
                     + text(bx0 + 44, y, "◆ A-S", 9.5, AMBER, 700, cls="pulse") + "</g>")
        y += 13.6

    # bid/ask imbalance meter
    my = y + 4
    b.append(text(bx0, my + 6, "IMB", 9.5, DIM, ls=1))
    mx0, mw = bx0 + 34, bx1 - bx0 - 34
    iw = [rnd.uniform(0.3, 0.7) * mw for _ in range(5)]
    iw.append(iw[0])
    b.append(f'<rect x="{mx0}" y="{my}" width="{mw}" height="7" rx="2" fill="{RED}" opacity=".6"/>')
    b.append(f'<rect x="{mx0}" y="{my}" width="{iw[0]:.1f}" height="7" rx="2" fill="{GREEN}" opacity=".8">'
             f'<animate attributeName="width" values="{";".join(f"{w:.1f}" for w in iw)}" '
             f'dur="7s" repeatCount="indefinite"/></rect>')
    return doc(W, H, "Candlestick chart with an Avellaneda-Stoikov market maker switched on: "
               "reservation price, skewed bid and ask quotes, fills, inventory and PnL, "
               "next to a level-2 order book showing its resting quotes", css, defs, b)


# --------------------------------------------------------------------------
def options():
    """Short iron condor: P&L today decays toward the expiry payoff, Greeks follow."""
    W, H = 412, 264
    S0, sig = 100.0, 0.30
    K1, K2, K3, K4 = 80.0, 90.0, 110.0, 120.0
    days = [45, 25, 10, 2]
    kt = [0, .3, .6, .9, 1]
    DUR = 12

    def liab(S, T, s=sig):
        return (bs_price(S, K2, T, s, False) - bs_price(S, K1, T, s, False)
                + bs_price(S, K3, T, s, True) - bs_price(S, K4, T, s, True))

    credit = liab(S0, days[0] / 365)

    def pl(S, T, s=sig):
        return credit - liab(S, T, s)

    Ss = [70 + 0.5 * i for i in range(121)]
    exp_pl = [pl(S, 0) for S in Ss]
    lo, hi = min(exp_pl) - 0.6, credit + 1.4
    x0, x1, y0, y1 = 44.0, 396.0, 52.0, 168.0

    def px(S):
        return x0 + (S - Ss[0]) / (Ss[-1] - Ss[0]) * (x1 - x0)

    def py(v):
        return y1 - (v - lo) / (hi - lo) * (y1 - y0)

    defs, b = window(W, H, "OPTIONS ▸ IRON CONDOR")
    b += cycle_texts([f"T−t {d}d" for d in days], W - 16, 19.5, 11, CYAN, 700, "end", kt, DUR)
    zy = py(0)
    defs += [
        f'<clipPath id="up"><rect x="{x0}" y="{y0 - 10}" width="{x1 - x0}" height="{zy - y0 + 10:.1f}"/></clipPath>',
        f'<clipPath id="dn"><rect x="{x0}" y="{zy:.1f}" width="{x1 - x0}" height="{y1 - zy + 2:.1f}"/></clipPath>',
    ]
    # axes
    for v in (credit, 0, min(exp_pl)):
        b.append(f'<line x1="{x0}" y1="{py(v):.1f}" x2="{x1}" y2="{py(v):.1f}" stroke="{GRID if v else BORDER}"/>')
    b.append(text(x0 - 6, py(credit) + 3.5, f"+{credit:.2f}", 9, GREEN, anchor="end"))
    b.append(text(x0 - 6, zy + 3.5, "0", 9, DIM, anchor="end"))
    b.append(text(x0 - 6, py(min(exp_pl)) + 3.5, f"{min(exp_pl):.1f}", 9, RED, anchor="end"))
    for K in (K1, K2, K3, K4):
        b.append(f'<line x1="{px(K):.1f}" y1="{y1}" x2="{px(K):.1f}" y2="{y1 + 4}" stroke="{DIM}"/>')
        b.append(text(px(K), y1 + 14, f"{K:.0f}", 9, DIM, anchor="middle"))
    b.append(f'<line x1="{px(S0):.1f}" y1="{y0 - 6}" x2="{px(S0):.1f}" y2="{y1}" stroke="{AMBER}" '
             f'stroke-dasharray="2 3" opacity=".7"/>')
    b.append(text(px(S0), y0 - 9, "SPOT", 8.5, AMBER, 700, anchor="middle", ls=1))

    # expiry payoff with profit/loss shading
    ep = [(px(S), py(v)) for S, v in zip(Ss, exp_pl)]
    area = ep + [(x1, zy), (x0, zy)]
    b.append(f'<g class="f"><polygon clip-path="url(#up)" points="{pts_str(area)}" fill="{GREEN}" opacity=".16"/>'
             f'<polygon clip-path="url(#dn)" points="{pts_str(area)}" fill="{RED}" opacity=".09"/>'
             f'<polyline points="{pts_str(ep)}" fill="none" stroke="{AMBER}" stroke-width="1.6"/></g>')
    for be in (K2 - credit, K3 + credit):
        b.append(f'<circle cx="{px(be):.1f}" cy="{zy:.1f}" r="2.6" fill="{AMBER}"/>')

    # P&L today, decaying toward expiry
    curves = [pts_str([(px(S), py(pl(S, d / 365))) for S in Ss]) for d in days]
    keys = (f'keyTimes="{";".join(str(k) for k in kt)}" calcMode="spline" '
            f'keySplines=".4 0 .6 1;.4 0 .6 1;.4 0 .6 1;.4 0 .6 1"')
    b.append(f'<polyline points="{curves[0]}" fill="none" stroke="{CYAN}" stroke-width="1.8" '
             f'filter="url(#glow2)"><animate attributeName="points" values="{";".join(curves + curves[:1])}" '
             f'dur="{DUR}s" repeatCount="indefinite" {keys}/></polyline>')
    defs.append(GLOW)
    b.append(text(x1, y0 + 2, "━ TODAY", 9, CYAN, 700, anchor="end", ls=1))
    b.append(text(x1, y0 + 14, "━ EXPIRY", 9, AMBER, 700, anchor="end", ls=1))

    # Greeks at spot for each time step
    def greeks(T):
        h = 0.5
        d = (pl(S0 + h, T) - pl(S0 - h, T)) / (2 * h)
        g = (pl(S0 + h, T) - 2 * pl(S0, T) + pl(S0 - h, T)) / (h * h)
        th = pl(S0, T - 1 / 365) - pl(S0, T)
        v = pl(S0, T, sig + 0.01) - pl(S0, T)
        return d, g, th, v

    gs = [greeks(d / 365) for d in days]
    names = [("Δ", "DELTA", "{:+.3f}"), ("Γ", "GAMMA", "{:+.3f}"),
             ("Θ", "THETA", "{:+.3f}"), ("ν", "VEGA", "{:+.3f}")]
    b.append(f'<line x1="16" y1="186.5" x2="{W - 16}" y2="186.5" stroke="{BORDER}"/>')
    cwid = (W - 32) / 4
    for gi, (sym, nm, fmt) in enumerate(names):
        cx0 = 16 + gi * cwid
        vals = [g[gi] for g in gs]
        vmax = max(abs(v) for v in vals) or 1
        b.append(text(cx0 + 6, 210, sym, 17, AMBER, 700))
        b.append(text(cx0 + 26, 206, nm, 8.5, DIM, ls=1))
        b += cycle_texts([fmt.format(v) for v in vals], cx0 + 26, 220, 11, TEXT, 700, None, kt, DUR)
        mid, half = cx0 + cwid / 2, cwid / 2 - 10
        b.append(f'<line x1="{mid:.1f}" y1="232" x2="{mid:.1f}" y2="244" stroke="{DIM}"/>')
        b.append(f'<rect x="{mid - half:.1f}" y="236" width="{2 * half:.1f}" height="4" rx="2" fill="{PANEL2}"/>')
        xs = [mid if v >= 0 else mid - abs(v) / vmax * half for v in vals]
        ws = [abs(v) / vmax * half for v in vals]
        col = GREEN if vals[0] >= 0 else RED
        b.append(f'<rect x="{xs[0]:.1f}" y="235" width="{ws[0]:.1f}" height="6" rx="2" fill="{col}" opacity=".85">'
                 f'<animate attributeName="x" values="{";".join(f"{v:.1f}" for v in xs + xs[:1])}" dur="{DUR}s" repeatCount="indefinite" {keys}/>'
                 f'<animate attributeName="width" values="{";".join(f"{v:.1f}" for v in ws + ws[:1])}" dur="{DUR}s" repeatCount="indefinite" {keys}/>'
                 "</rect>")
    return doc(W, H, "Short iron condor: P&L today decaying toward the expiry payoff, "
               "with delta, gamma, theta and vega at spot", "", defs, b)


# --------------------------------------------------------------------------
def macro():
    W, H = 412, 264
    defs, b = window(W, H, "MACRO ▸ ECON CALENDAR", "ET")
    defs.append(GLOW)
    cols = [(16, "TIME"), (62, "CCY"), (100, "EVENT"), (262, "IMPACT")]
    for x, lab in cols:
        b.append(text(x, 52, lab, 9.5, DIM, ls=1))
    b.append(text(W - 16, 52, "STATUS", 9.5, DIM, anchor="end", ls=1))
    b.append(f'<line x1="16" y1="59.5" x2="{W - 16}" y2="59.5" stroke="{GRID}"/>')
    rows = [
        ("07:45", "EUR", "ECB Rate Decision", 3, "RELEASED"),
        ("08:30", "USD", "CPI m/m", 3, "RELEASED"),
        ("08:30", "USD", "Nonfarm Payrolls", 3, "RELEASED"),
        ("10:00", "USD", "ISM Services PMI", 2, "RELEASED"),
        ("14:00", "USD", "FOMC Rate Decision", 3, "NEXT"),
        ("14:30", "USD", "Fed Chair Presser", 3, "QUEUED"),
    ]
    y = 78
    for i, (tm, ccy, ev, imp, st) in enumerate(rows):
        nxt = st == "NEXT"
        done = st == "RELEASED"
        g = [f'<g class="f" style="animation-delay:{0.1 + i * 0.1:.2f}s">']
        if nxt:
            g.append(f'<rect class="pulse" x="10" y="{y - 14}" width="{W - 20}" height="20" rx="3" '
                     f'fill="{AMBER}" fill-opacity=".13"/>')
            g.append(f'<rect x="10" y="{y - 14}" width="3" height="20" fill="{AMBER}"/>')
        tc = DIM if done else TEXT
        g.append(text(16, y, tm, 11.5, tc, 700 if nxt else None))
        g.append(text(62, y, ccy, 11.5, AMBER if nxt else tc, 700))
        g.append(text(100, y, ev, 11.5, AMBER if nxt else tc, 700 if nxt else None))
        for k in range(3):
            fill = RED if k < imp else PANEL2
            g.append(f'<circle cx="{266 + k * 10}" cy="{y - 4}" r="3.3" fill="{fill}" '
                     f'opacity="{.55 if done and k < imp else 1}"/>')
        if done:
            g.append(text(W - 16, y, "✓ " + st, 9.5, DIM, anchor="end", ls=1))
        elif nxt:
            g.append(f'<g filter="url(#glow2)">' + text(W - 16, y, "▶ NEXT", 10, AMBER, 700, anchor="end",
                                                        ls=1.2, cls="blink") + "</g>")
        else:
            g.append(text(W - 16, y, st, 9.5, DIM, anchor="end", ls=1))
        g.append("</g>")
        b.append("".join(g))
        y += 22

    # countdown to the next event (counts down from 9:59 and loops)
    b.append(f'<line x1="16" y1="{y - 6.5}" x2="{W - 16}" y2="{y - 6.5}" stroke="{BORDER}"/>')
    b.append(text(16, y + 12, "NEXT ▸ FOMC RATE DECISION", 10, AMBER, 700, ls=1))
    fs, cy_ = 21, y + 42
    cw = fs * CW
    cd = []
    xx = 16.0
    for ch in "T-00:0":
        cd.append(text(xx, cy_, ch, fs, AMBER, 700))
        xx += cw
    for cid, seq, unit in (("m1", list(range(9, -1, -1)), 60),):
        clip, body = digit_strip(cid, xx, cy_, seq, unit, fs, AMBER)
        defs.append(clip)
        cd.append(body)
        xx += cw
    cd.append(text(xx, cy_, ":", fs, AMBER, 700))
    xx += cw
    for cid, seq, unit in (("s10", list(range(5, -1, -1)), 10), ("s1", list(range(9, -1, -1)), 1)):
        clip, body = digit_strip(cid, xx, cy_, seq, unit, fs, AMBER)
        defs.append(clip)
        cd.append(body)
        xx += cw
    b.append(f'<g filter="url(#glow2)">{"".join(cd)}</g>')
    b.append(text(W - 16, y + 12, "EVENT MODE", 9.5, DIM, anchor="end", ls=1.2))
    b.append(text(W - 16, y + 29, "● ARMED", 11, RED, 700, anchor="end", ls=1.5, cls="pulse"))
    b.append(text(W - 16, y + 44, "widen · cut size · flat into print", 9, DIM, anchor="end"))
    return doc(W, H, "Macro economic calendar with released events, the next FOMC decision "
               "and a live countdown", "", defs, b)


# --------------------------------------------------------------------------
CODE = '''import numpy as np
from scipy.stats import norm

def bs_call(S, K, T, sigma, r=0.0):
    """Black–Scholes price of a European call."""
    d1 = (np.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

def as_quotes(s, q, sigma, gamma, k, tau):
    """Avellaneda–Stoikov: reservation price + optimal spread."""
    r = s - q * gamma * sigma**2 * tau
    spread = gamma * sigma**2 * tau + (2 / gamma) * np.log(1 + gamma / k)
    return r - spread / 2, r + spread / 2'''

TOKEN = re.compile(
    r'(?P<doc>""".*?""")|(?P<com>#.*$)|(?P<kw>\b(?:import|from|def|return|as)\b)'
    r'|(?P<num>\b\d+(?:\.\d+)?\b)|(?P<name>\b[A-Za-z_]\w*\b)|(?P<op>[^\w\s]+)|(?P<ws>\s+)')


def highlight(line):
    out, prev_kw = [], None
    for m in TOKEN.finditer(line):
        kind, tok = m.lastgroup, m.group()
        col, wt = TEXT, None
        if kind == "doc":
            col = "#6fcf97"
        elif kind == "com":
            col = DIM
        elif kind == "kw":
            col = PURPLE
        elif kind == "num":
            col = AMBER
        elif kind == "op":
            col = "#89a4c0"
        elif kind == "name":
            nxt = line[m.end():m.end() + 1]
            if prev_kw == "def":
                col, wt = CYAN, 700
            elif tok in ("np", "norm", "scipy", "numpy", "stats"):
                col = BLUE
            elif nxt == "(":
                col = BLUE
        if kind == "kw":
            prev_kw = tok
        elif kind != "ws":
            prev_kw = None
        t = html.escape(tok).replace(" ", " ")
        w = f' font-weight="{wt}"' if wt else ""
        out.append(f'<tspan fill="{col}"{w}>{t}</tspan>')
    return "".join(out)


def code():
    W, H = 840, 300
    lines = CODE.split("\n")
    fs, lh, gx, cx0, top = 12, 17, 44, 56, 62
    css = """
.cur{animation:show .01s linear both,blink 1.05s step-end infinite}
"""
    defs, b = window(W, H)
    defs.append(GLOW)
    for i, c in enumerate((RED, AMBER, GREEN)):
        b.append(f'<circle cx="{20 + i * 18}" cy="15" r="5.5" fill="{c}"/>')
    # tabs
    b.append(f'<rect x="80" y="4" width="112" height="27" rx="4" fill="{BG}"/>')
    b.append(f'<rect x="80" y="4" width="112" height="2" fill="{AMBER}"/>')
    b.append(text(94, 21, "● quant.py", 11.5, TEXT, 700))
    b.append(text(206, 21, "README.md", 11.5, DIM))
    b.append(text(W - 16, 19.5, "PYTHON 3.12 · UTF-8 · LF", 10.5, DIM, anchor="end", ls=1))
    ex = 610  # editor / REPL split
    b.append(f'<line x1="{ex + .5}" y1="31" x2="{ex + .5}" y2="{H - 1}" stroke="{BORDER}"/>')
    b.append(f'<rect x="1" y="31" width="{gx - 6}" height="{H - 32}" fill="{PANEL}" opacity=".6"/>')

    # typing schedule
    per, t, starts = 0.013, 0.4, []
    for ln in lines:
        starts.append(t)
        t += (len(ln) + 1) * per + (0.08 if ln.strip() else 0.12)
    t_done = t

    # active-line highlight that follows the typing
    ys = [top + i * lh for i in range(len(lines))]
    kts = ";".join(f"{s / t_done:.4f}" for s in starts)
    yv = ";".join(f"{y - 12.5:.1f}" for y in ys)
    b.append(f'<rect x="{gx - 6}" y="{ys[-1] - 12.5:.1f}" width="{ex - gx + 6}" height="{lh}" fill="#ffffff" '
             f'opacity=".035"><animate attributeName="y" calcMode="discrete" values="{yv}" '
             f'keyTimes="{kts}" dur="{t_done:.2f}s" fill="freeze"/></rect>')

    for i, ln in enumerate(lines):
        y = ys[i]
        b.append(text(gx - 12, y, str(i + 1), 11, DIM, anchor="end", cls="o",
                      style=f"animation-delay:{starts[i]:.2f}s"))
        if not ln:
            continue
        clip, _ = typing_clip(f"cl{i}", cx0, y, ln, fs, starts[i], per)
        defs.append(clip)
        b.append(f'<text x="{cx0}" y="{y}" font-size="{fs}" clip-path="url(#cl{i})">{highlight(ln)}</text>')
    lastw = len(lines[-1]) * fs * CW
    b.append(f'<rect class="cur" style="animation-delay:{t_done:.2f}s,{t_done:.2f}s" x="{cx0 + lastw + 2:.1f}" '
             f'y="{ys[-1] - 11}" width="7" height="14" fill="{AMBER}" filter="url(#glow2)"/>')

    # REPL: actually evaluate both functions
    S, K, T, sg = 100, 105, 0.5, 0.25
    d1 = (math.log(S / K) + sg ** 2 / 2 * T) / (sg * math.sqrt(T))
    call = S * ncdf(d1) - K * ncdf(d1 - sg * math.sqrt(T))
    _, qb, qa = as_quotes(108.5, 1, 1.0, 0.5, 1.5, 1)
    rx, rf = ex + 14, 11
    b.append(text(rx, 52, "REPL", 9.5, DIM, ls=1.5))
    repl = [
        (">>> ", "bs_call(100,105,.5,.25)", True),
        ("", f"{call:.4f}", False),
        (">>> ", "as_quotes(108.5,1,", True),
        ("... ", "  1.0,.5,1.5,1)", True),
        ("", f"({qb:.2f}, {qa:.2f})", False),
    ]
    rt, ry = t_done + 0.3, 76
    for i, (pr, body, typed) in enumerate(repl):
        if typed:
            b.append(text(rx, ry, pr, rf, GREEN, 700, cls="o", style=f"animation-delay:{rt:.2f}s"))
            clip, rt = typing_clip(f"rp{i}", rx + len(pr) * rf * CW, ry, body, rf, rt, 0.035)
            defs.append(clip)
            b.append(f'<text x="{rx + len(pr) * rf * CW:.1f}" y="{ry}" font-size="{rf}" fill="{TEXT}" '
                     f'clip-path="url(#rp{i})">{esc(body)}</text>')
            rt += 0.15
        else:
            b.append(text(rx, ry, body, rf, AMBER, 700, cls="o", style=f"animation-delay:{rt + 0.2:.2f}s"))
            rt += 0.6
        ry += 20
    b.append(text(rx, ry, ">>>", rf, GREEN, 700, cls="o", style=f"animation-delay:{rt:.2f}s"))
    b.append(f'<rect class="cur" style="animation-delay:{rt:.2f}s,{rt:.2f}s" x="{rx + 4 * rf * CW:.1f}" '
             f'y="{ry - 10}" width="6.5" height="12" fill="{GREEN}"/>')
    b.append(text(rx, H - 16, "✓ 2 functions · 0 errors", 9.5, GREEN, cls="o",
                  style=f"animation-delay:{rt:.2f}s", ls=0.5))
    return doc(W, H, "Code editor typing a Black-Scholes pricer and the Avellaneda-Stoikov "
               "quoting function in Python, then running both in a REPL", css, defs, b)


# --------------------------------------------------------------------------
def volsurf():
    """Implied-vol surface (SSVI) drawn as a ridgeline of smiles that breathes."""
    W, H = 412, 264
    nk, nt = 29, 11
    kmin, kmax = -0.6, 0.45
    ks = [kmin + (kmax - kmin) * i / (nk - 1) for i in range(nk)]
    Ts = [0.06 * (2.0 / 0.06) ** (j / (nt - 1)) for j in range(nt)]
    states = [(-0.55, 1.1, 1.0), (-0.3, 1.45, 1.06), (-0.72, 0.85, 0.95)]

    def iv(k, T, rho, eta, lev):
        atm = lev * (0.20 + 0.07 * math.exp(-2.5 * T))
        th = atm * atm * T
        phi = eta / (th ** 0.35 * (1 + th) ** 0.65)
        w = th / 2 * (1 + rho * phi * k + math.sqrt((phi * k + rho) ** 2 + 1 - rho * rho))
        return math.sqrt(w / T)

    surf = [[[iv(k, T, *st) for k in ks] for T in Ts] for st in states]
    base = 0.10
    top = max(max(max(r) for r in s) for s in surf)
    ox, oy, Wu, Dx, Dy, Hz = 36, 236, 250, 90, 74, 148

    def proj(u, v, z):
        return ox + u * Wu + v * Dx, oy - v * Dy - z * Hz

    def z_(x):
        return (x - base) / (top - base)

    defs, b = window(W, H, "VOL SURFACE ▸ SSVI", "IMPLIED VOL")
    b.append(text(16, 48, "ρ · η · θ(T)", 10, DIM, ls=1))
    b.append(text(W - 16, 48, "3W → 2Y", 10, DIM, anchor="end", ls=1))

    fl = [proj(0, 0, 0), proj(1, 0, 0), proj(1, 1, 0), proj(0, 1, 0)]
    b.append(f'<polygon points="{pts_str(fl)}" fill="{PANEL}" stroke="{BORDER}"/>')
    for q in (0.25, 0.5, 0.75):
        a1, a2 = proj(q, 0, 0), proj(q, 1, 0)
        b.append(f'<line x1="{a1[0]:.1f}" y1="{a1[1]:.1f}" x2="{a2[0]:.1f}" y2="{a2[1]:.1f}" stroke="{GRID}"/>')
    ax_top = proj(0, 0, 1)
    b.append(f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{ax_top[1]:.1f}" stroke="{BORDER}"/>')
    for lvl in (0.2, 0.4, 0.6):
        if base < lvl < top:
            yy = oy - z_(lvl) * Hz
            b.append(f'<line x1="{ox - 3}" y1="{yy:.1f}" x2="{ox}" y2="{yy:.1f}" stroke="{DIM}"/>')
            b.append(text(ox - 5, yy + 3.5, f"{lvl:.0%}", 9, DIM, anchor="end"))

    keys = 'keyTimes="0;.33;.66;1" calcMode="spline" keySplines=".45 0 .55 1;.45 0 .55 1;.45 0 .55 1"'
    for j in range(nt - 1, -1, -1):  # back to front so nearer smiles occlude
        v = j / (nt - 1)
        col = hsl_lerp(AMBER, CYAN, v)
        defs.append(f'<linearGradient id="vg{j}" x1="0" y1="0" x2="0" y2="1">'
                    f'<stop offset="0" stop-color="{col}" stop-opacity=".16"/>'
                    f'<stop offset="1" stop-color="{col}" stop-opacity="0"/></linearGradient>')
        lines, polys = [], []
        for s in range(len(states)):
            line = [proj((k - kmin) / (kmax - kmin), v, z_(surf[s][j][i])) for i, k in enumerate(ks)]
            lines.append(pts_str(line))
            polys.append(pts_str(line + [proj(1, v, 0), proj(0, v, 0)]))
        lv = ";".join(lines + lines[:1])
        pv = ";".join(polys + polys[:1])
        anim_l = f'<animate attributeName="points" values="{lv}" dur="10s" repeatCount="indefinite" {keys}/>'
        anim_p = f'<animate attributeName="points" values="{pv}" dur="10s" repeatCount="indefinite" {keys}/>'
        b.append(
            f'<g class="f" style="animation-delay:{(nt - 1 - j) * 0.09:.2f}s">'
            f'<polygon points="{polys[0]}" fill="{BG}">{anim_p}</polygon>'
            f'<polygon points="{polys[0]}" fill="url(#vg{j})">{anim_p}</polygon>'
            f'<polyline points="{lines[0]}" fill="none" stroke="{col}" stroke-width="{1.8 if j == 0 else 1.2}" '
            f'stroke-linejoin="round">{anim_l}</polyline></g>'
        )

    u0 = (0 - kmin) / (kmax - kmin)
    cys = [proj(u0, 0, z_(iv(0, Ts[0], *st)))[1] for st in states]
    cx = proj(u0, 0, 0)[0]
    b.append(f'<circle class="pulse" cx="{cx:.1f}" cy="{cys[0]:.1f}" r="3.2" fill="{TEXT}">'
             f'<animate attributeName="cy" values="{";".join(f"{c:.1f}" for c in cys + cys[:1])}" '
             f'dur="10s" repeatCount="indefinite" {keys}/></circle>')

    b.append(text(ox, oy + 16, "◂ PUTS", 9.5, DIM, ls=1))
    b.append(text(cx, oy + 16, "ATM", 9.5, TEXT, 700, anchor="middle", ls=1))
    b.append(text(ox + Wu, oy + 16, "CALLS ▸", 9.5, DIM, anchor="end", ls=1))
    return doc(W, H, "Implied volatility surface drawn as a ridgeline of SSVI smiles "
               "from 3 weeks to 2 years, gently shifting skew", "", defs, b)


# --------------------------------------------------------------------------
def montecarlo():
    W, H = 412, 264
    rnd = random.Random(42)
    S0, mu, sig, T, n = 100.0, 0.08, 0.32, 1.0, 64
    dt = T / n

    def path():
        s = [S0]
        for _ in range(n):
            s.append(s[-1] * math.exp((mu - 0.5 * sig * sig) * dt
                                      + sig * math.sqrt(dt) * rnd.gauss(0, 1)))
        return s

    sims = [path() for _ in range(1500)]
    shown = sims[:34]

    def pct(vals, q):
        s = sorted(vals)
        return s[int(q * (len(s) - 1))]

    cols = [[p[t] for p in sims] for t in range(n + 1)]
    p05 = [pct(c, .05) for c in cols]
    p50 = [pct(c, .50) for c in cols]
    p95 = [pct(c, .95) for c in cols]
    lo, hi = min(p05) * 0.9, max(p95) * 1.08

    x0, x1, y0, y1 = 44.0, 318.0, 56.0, 236.0
    hx0, hx1 = 326.0, 396.0

    def px(t):
        return x0 + (x1 - x0) * t / n

    def py(s):  # paths beyond the axis are cut by the #plot clip, not clamped
        return y1 - (s - lo) / (hi - lo) * (y1 - y0)

    css = """
.mc{stroke-dasharray:1;animation:mc 7.5s linear infinite}
@keyframes mc{0%{stroke-dashoffset:1;opacity:.7}45%{stroke-dashoffset:0;opacity:.7}80%{opacity:.7}100%{stroke-dashoffset:0;opacity:0}}
"""
    defs, b = window(W, H, "MONTE CARLO ▸ GBM", "μ .08  σ .32  N 1500")
    defs.append(f'<clipPath id="plot"><rect x="{x0}" y="{y0 - 4}" width="{x1 - x0}" height="{y1 - y0 + 8}"/></clipPath>')
    b.append(text(x0, 46, "━ MEDIAN", 9.5, AMBER, 700, ls=1))
    b.append(text(x0 + 70, 46, "▮ P5–P95", 9.5, CYAN, 700, ls=1))
    b.append(text(hx1, 46, "S(T)", 9.5, DIM, anchor="end", ls=1))

    tick = nice_tick(hi - lo, 4)
    p = math.ceil(lo / tick) * tick
    while p < hi:
        yy = py(p)
        b.append(f'<line x1="{x0}" y1="{yy:.1f}" x2="{hx1}" y2="{yy:.1f}" stroke="{GRID}"/>')
        b.append(text(x0 - 6, yy + 3.5, f"{p:.0f}", 9.5, DIM, anchor="end"))
        p += tick
    b.append(f'<line x1="{hx0 - 4}" y1="{y0 - 4}" x2="{hx0 - 4}" y2="{y1}" stroke="{BORDER}"/>')
    b.append(text(x0, y1 + 16, "t = 0", 9.5, DIM, ls=1))
    b.append(text(x1, y1 + 16, "T = 1Y", 9.5, DIM, anchor="end", ls=1))

    up = [(px(t), py(p95[t])) for t in range(n + 1)]
    dn = [(px(t), py(p05[t])) for t in range(n + 1)]
    b.append(
        f'<g class="f" style="animation-delay:.3s">'
        f'<polygon points="{pts_str(up + dn[::-1])}" fill="{CYAN}" opacity=".08"/>'
        f'<polyline points="{pts_str(up)}" fill="none" stroke="{CYAN}" opacity=".5" stroke-dasharray="3 3"/>'
        f'<polyline points="{pts_str(dn)}" fill="none" stroke="{CYAN}" opacity=".5" stroke-dasharray="3 3"/></g>'
    )

    g = ['<g clip-path="url(#plot)">']
    for i, s in enumerate(shown):
        col = GREEN if s[-1] >= S0 else RED
        d = "M" + " L".join(f"{px(t):.1f},{py(v):.1f}" for t, v in enumerate(s))
        g.append(f'<path class="mc" style="animation-delay:{i * 0.2:.2f}s" d="{d}" pathLength="1" '
                 f'fill="none" stroke="{col}" stroke-width="1" stroke-linejoin="round"/>')
    g.append("</g>")
    b.extend(g)

    med = [(px(t), py(p50[t])) for t in range(n + 1)]
    b.append(f'<polyline class="f" style="animation-delay:.6s" points="{pts_str(med)}" fill="none" '
             f'stroke="{AMBER}" stroke-width="2" stroke-linejoin="round"/>')
    b.append(f'<circle cx="{x0}" cy="{py(S0):.1f}" r="3.5" fill="{AMBER}"/>')

    nb = 22
    edges = [lo + (hi - lo) * i / nb for i in range(nb + 1)]
    counts = [0] * nb
    for s in sims:
        if lo <= s[-1] < hi:  # tails beyond the axis are left out, not piled at the edge
            counts[int((s[-1] - lo) / (hi - lo) * nb)] += 1
    cmax = max(counts)
    for i, c in enumerate(counts):
        if not c:
            continue
        ya, yb = py(edges[i + 1]), py(edges[i])
        mid = (edges[i] + edges[i + 1]) / 2
        col = GREEN if mid >= S0 else RED
        b.append(f'<rect class="grow" style="animation-delay:{0.8 + i * 0.03:.2f}s" x="{hx0}" '
                 f'y="{ya + 0.5:.1f}" width="{c / cmax * (hx1 - hx0):.1f}" height="{max(yb - ya - 1, 1):.1f}" '
                 f'fill="{col}" opacity=".5"/>')
    ym = py(p50[-1])
    b.append(f'<line x1="{hx0}" y1="{ym:.1f}" x2="{hx1}" y2="{ym:.1f}" stroke="{AMBER}" stroke-width="1.5"/>')
    return doc(W, H, "Monte Carlo fan chart: GBM price paths with a P5 to P95 band, "
               "median path and a histogram of terminal prices", css, defs, b)


# --------------------------------------------------------------------------
def stack():
    W, H = 412, 264
    rnd = random.Random(5)
    defs, b = window(W, H, "WATCHLIST ▸ STACK", "6 SYMBOLS")
    b.append(text(16, 54, "SYM", 9.5, DIM, ls=1))
    b.append(text(70, 54, "NAME", 9.5, DIM, ls=1))
    b.append(text(170, 54, "USE", 9.5, DIM, ls=1))
    b.append(text(W - 16, 54, "TREND", 9.5, DIM, anchor="end", ls=1))
    b.append(f'<line x1="16" y1="62.5" x2="{W - 16}" y2="62.5" stroke="{GRID}"/>')
    rows = [
        ("PY", "Python", "research · backtests"),
        ("CPP", "C++", "low-latency engines"),
        ("RS", "Rust", "systems · tooling"),
        ("CS", "C#", "NT8 strategies"),
        ("IBKR", "IB API", "broker · execution"),
        ("NT8", "NinjaTrader", "futures platform"),
    ]
    y = 88
    for i, (sym, name, use) in enumerate(rows):
        d = f"animation-delay:{0.15 + i * 0.12:.2f}s"
        v, pts = 0.0, []
        for _ in range(12):
            v += rnd.gauss(0.35, 0.8)
            pts.append(v)
        mn, mx = min(pts), max(pts)
        sx0, sx1 = W - 76, W - 22
        poly = " ".join(
            f"{sx0 + k * (sx1 - sx0) / 11:.1f},{y - 2 - (p - mn) / (mx - mn) * 14:.1f}"
            for k, p in enumerate(pts))
        ey = y - 2 - (pts[-1] - mn) / (mx - mn) * 14
        b.append(
            f'<g class="f" style="{d}">'
            + text(16, y, sym, 13, AMBER, 700)
            + text(70, y, name, 13, TEXT)
            + text(170, y, use, 11.5, DIM)
            + f'<polyline points="{poly}" fill="none" stroke="{GREEN}" stroke-width="1.5" stroke-linejoin="round"/>'
            + f'<circle class="pulse" cx="{sx1:.1f}" cy="{ey:.1f}" r="2.5" fill="{GREEN}"/>'
            + "</g>"
        )
        if i < len(rows) - 1:
            b.append(f'<line x1="16" y1="{y + 11.5}" x2="{W - 16}" y2="{y + 11.5}" stroke="{GRID}" stroke-dasharray="1 3"/>')
        y += 31
    return doc(W, H, "Watchlist of the stack: Python, C++, Rust, C#, IBKR API, NinjaTrader 8",
               "", defs, b)


def desks():
    W, H = 412, 264
    defs, b = window(W, H, "DESKS ▸ STRATEGIES", "● 5 ACTIVE", GREEN)
    y = 56
    for i, name in enumerate(["OPTIONS", "HFT", "MARKET MAKING", "PROP FIRM CYCLING", "MACRO / NEWS"]):
        d = f"animation-delay:{0.15 + i * 0.12:.2f}s"
        end = 36 + len(name) * (12.5 * CW + 1) + 10
        b.append(
            f'<g class="f" style="{d}">'
            f'<circle class="pulse" style="animation-delay:{i * 0.3:.1f}s" cx="22" cy="{y - 4}" r="3.5" fill="{GREEN}"/>'
            + text(36, y, name, 12.5, TEXT, 700, ls=1)
            + f'<line x1="{end:.1f}" y1="{y - 4}" x2="{W - 70}" y2="{y - 4}" stroke="{GRID}" stroke-dasharray="1 4"/>'
            + text(W - 16, y, "ACTIVE", 10.5, GREEN, 700, anchor="end", ls=1.2)
            + "</g>"
        )
        y += 23
    b.append(f'<line x1="16" y1="{y - 6.5}" x2="{W - 16}" y2="{y - 6.5}" stroke="{BORDER}"/>')
    y += 14
    b.append(text(16, y, "INFRA ▸ SELF-BUILT", 11, AMBER, 700, ls=1.6))
    y += 24
    for i, name in enumerate(["backtesting engine", "execution layer", "options-flow analytics"]):
        d = f"animation-delay:{0.8 + i * 0.12:.2f}s"
        end = 36 + len(name) * 12.5 * CW + 10
        b.append(
            f'<g class="f" style="{d}">'
            + text(20, y, "▸", 12.5, AMBER)
            + text(36, y, name, 12.5, TEXT)
            + f'<line x1="{end:.1f}" y1="{y - 4}" x2="{W - 72}" y2="{y - 4}" stroke="{GRID}" stroke-dasharray="1 4"/>'
            + text(W - 16, y, "ONLINE", 10.5, CYAN, 700, anchor="end", ls=1.2)
            + "</g>"
        )
        y += 22
    return doc(W, H, "Strategy desks: options, HFT, market making, prop firm cycling, "
               "macro/news. Self-built backtesting, execution and options-flow tools",
               "", defs, b)


# --------------------------------------------------------------------------
def statusbar():
    """Powerline-style status bar with an uptime counter that ticks from page load."""
    W, H, A = 840, 30, 10
    fs = 11.5
    cw = fs * CW
    defs = [f'<clipPath id="bar"><rect width="{W}" height="{H}" rx="6"/></clipPath>']
    b = ['<g clip-path="url(#bar)">', f'<rect width="{W}" height="{H}" fill="{BG}"/>']

    def seg_l(xa, xb, fill):
        return f'<polygon points="{xa},0 {xb},0 {xb + A},{H / 2} {xb},{H} {xa},{H}" fill="{fill}"/>'

    def seg_r(xa, xb, fill):
        return f'<polygon points="{xb},0 {xa},0 {xa - A},{H / 2} {xa},{H} {xb},{H}" fill="{fill}"/>'

    ty = 19.5
    b.append(seg_l(0, 206, PANEL2))
    b.append(seg_l(0, 104, AMBER))
    b.append(text(14, ty, "◆ QT//OS", fs, BG, 700, ls=1.5))
    b.append(text(122, ty, "git:main", fs, TEXT, ls=0.5))
    b.append(text(232, ty, "~/alpha/research", fs, DIM))
    b.append(seg_r(W - 270, W, PANEL2))
    b.append(seg_r(W - 104, W, AMBER))
    b.append(text(W - 14, ty, "qtjohn18", fs, BG, 700, anchor="end", ls=1))
    lab_x = W - 256
    b.append(text(lab_x, ty, "UPTIME", fs, DIM, ls=1))
    dx = lab_x + 7 * (cw + 1) + 4
    spec = [(None, 0), (range(10), 3600), (":", 0), (range(6), 600), (range(10), 60),
            (":", 0), (range(6), 10), (range(10), 1)]
    for i, (seq, unit) in enumerate(spec):
        x = dx + i * cw
        if seq is None:
            b.append(text(x, ty, "0", fs, TEXT, 700))
        elif seq == ":":
            b.append(text(x, ty, ":", fs, DIM, 700))
        else:
            clip, body = digit_strip(f"dg{i}", x, ty, list(seq), unit, fs, TEXT)
            defs.append(clip)
            b.append(body)
    b.append(f'<circle class="pulse" cx="{W - 470}" cy="{H / 2}" r="3.5" fill="{GREEN}"/>')
    b.append(text(W - 460, ty, "ALL SYSTEMS NOMINAL", fs, GREEN, 700, ls=1))
    b.append("</g>")
    b.append(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="6" fill="none" stroke="{BORDER}"/>')
    return doc(W, H, "Status bar: QT//OS, git main, all systems nominal, uptime counter, qtjohn18",
               "", defs, b, rx=6, scan=False)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (("header", header), ("ticker", ticker), ("market", market),
                     ("options", options), ("macro", macro), ("code", code),
                     ("volsurface", volsurf), ("montecarlo", montecarlo),
                     ("stack", stack), ("desks", desks), ("statusbar", statusbar)):
        path = os.path.join(OUT, f"{name}.svg")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(fn())
        print("wrote", path)


if __name__ == "__main__":
    main()
