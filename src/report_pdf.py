"""Printable reports: inline-SVG charts, print CSS and PDF printing through headless Chrome or
Edge. Used by the run report (src/run_report.py) and the evaluation report (evals/report_pdf.py).
No extra Python dependencies."""

from __future__ import annotations

import html
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from src.common.stats import wilson_ci

logger = logging.getLogger(__name__)

# Print palette: brand hue families, re-stepped to pass colour-blind and contrast checks.
BRAND = {"Sephora India": "#9b3f86", "Nykaa": "#e2607f", "Tira": "#1f7fc0"}
INK, INK2, INK3 = "#16181d", "#4d5260", "#7b8090"
GRID, SURF = "#e3e6ec", "#ffffff"
GOOD, BAD = "#2f7d4f", "#b8401a"
ACCENT = "#9b3f86"
RAMP = ["#f6edf4", "#e6cde0", "#cf9fc3", "#b46ea5", "#9b3f86", "#6f2a60"]  # plum, light → dark

esc = html.escape


def pct(v: float | None, d: int = 1) -> str:
    return "n/a" if v is None else f"{v * 100:.{d}f}%"


# ---------------------------------------------------------------- SVG charts


def hbars(rows: list[tuple[str, float | None, str]], vmax: float = 1.0, fmt=pct,
          width: int = 640, label_w: int = 250, row_h: int = 26) -> str:  # fmt: skip
    """Horizontal bars. rows: (label, value, colour). Values are labelled at the bar end."""
    plot_w = width - label_w - 70
    h = row_h * len(rows) + 24
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img">']
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        x = label_w + plot_w * t
        out.append(f'<line x1="{x}" y1="4" x2="{x}" y2="{h - 18}" stroke="{GRID}"/>')
        out.append(f'<text x="{x}" y="{h - 4}" font-size="9" fill="{INK3}" '
                   f'text-anchor="middle">{fmt(vmax * t) if fmt is pct else round(vmax * t, 1)}'
                   "</text>")  # fmt: skip
    for i, (label, v, color) in enumerate(rows):
        y = 6 + i * row_h
        out.append(f'<text x="{label_w - 8}" y="{y + 13}" font-size="10.5" fill="{INK}" '
                   f'text-anchor="end">{esc(label)}</text>')  # fmt: skip
        if v is None:
            out.append(f'<text x="{label_w + 4}" y="{y + 13}" font-size="10" fill="{INK3}">'
                       "not measured</text>")  # fmt: skip
            continue
        w = plot_w * min(v, vmax) / vmax
        if w >= 8:  # rounded data-end anchored on the baseline
            out.append(f'<path d="M{label_w},{y + 3} h{w - 4} a4,4 0 0 1 4,4 v8 a4,4 0 0 1 -4,4 '
                       f'h-{w - 4} z" fill="{color}"/>')  # fmt: skip
        elif w > 0:
            out.append(f'<rect x="{label_w}" y="{y + 3}" width="{w}" height="16" fill="{color}"/>')
        out.append(f'<text x="{label_w + w + 6}" y="{y + 13}" font-size="10.5" fill="{INK}" '
                   f'font-weight="600">{fmt(v)}</text>')  # fmt: skip
    out.append("</svg>")
    return "".join(out)


def grouped(categories: list[str], series: dict[str, list[float | None]], colors: dict[str, str],
            vmax: float = 1.0, fmt=pct, width: int = 640, height: int = 230,
            ci: dict[str, list[tuple[float, float] | None]] | None = None) -> str:  # fmt: skip
    """Vertical grouped bars with a value on each bar, optional 95% CI whiskers, and a legend."""
    left, bottom, top = 40, 34, 14
    pw, ph = width - left - 10, height - bottom - top
    n_s = len(series)
    gw = pw / max(1, len(categories))
    bw = min(34, (gw - 18) / max(1, n_s))
    out = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img">']
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        y = top + ph * (1 - t)
        out.append(f'<line x1="{left}" y1="{y}" x2="{width - 10}" y2="{y}" stroke="{GRID}"/>')
        lab = fmt(vmax * t, 0) if fmt is pct else f"{vmax * t:.1f}"
        out.append(f'<text x="{left - 5}" y="{y + 3}" font-size="9" fill="{INK3}" '
                   f'text-anchor="end">{lab}</text>')  # fmt: skip
    for ci_, cat in enumerate(categories):
        gx = left + ci_ * gw + (gw - bw * n_s - 2 * (n_s - 1)) / 2
        for si, (name, vals) in enumerate(series.items()):
            v = vals[ci_]
            x = gx + si * (bw + 2)
            if v is None:
                out.append(f'<text x="{x + bw / 2}" y="{top + ph - 4}" font-size="8" '
                           f'fill="{INK3}" text-anchor="middle">–</text>')  # fmt: skip
                continue
            bh = max(1.5, ph * min(v, vmax) / vmax)
            y = top + ph - bh
            r = min(4, bh / 2)
            out.append(f'<path d="M{x},{top + ph} v-{bh - r} a{r},{r} 0 0 1 {r},-{r} '
                       f'h{bw - 2 * r} a{r},{r} 0 0 1 {r},{r} v{bh - r} z" '
                       f'fill="{colors[name]}"/>')  # fmt: skip
            label_y = y - 4
            if ci and ci.get(name) and ci[name][ci_]:
                lo, hi = ci[name][ci_]
                y_lo, y_hi = top + ph * (1 - lo / vmax), top + ph * (1 - hi / vmax)
                cx = x + bw / 2
                out.append(f'<path d="M{cx},{y_lo} V{y_hi} M{cx - 4},{y_lo} h8 M{cx - 4},{y_hi} '
                           f'h8" stroke="{INK}" stroke-width="1.2" fill="none"/>')  # fmt: skip
                label_y = min(label_y, y_hi - 4)
            out.append(f'<text x="{x + bw / 2}" y="{label_y}" font-size="9" fill="{INK}" '
                       f'text-anchor="middle" font-weight="600">'
                       f"{fmt(v, 0) if fmt is pct else fmt(v)}</text>")  # fmt: skip
        out.append(f'<text x="{left + ci_ * gw + gw / 2}" y="{top + ph + 14}" font-size="10" '
                   f'fill="{INK}" text-anchor="middle">{esc(cat)}</text>')  # fmt: skip
    lx = left
    for name in series:
        out.append(f'<rect x="{lx}" y="{height - 12}" width="10" height="10" rx="2" '
                   f'fill="{colors[name]}"/><text x="{lx + 14}" y="{height - 3}" font-size="10" '
                   f'fill="{INK}">{esc(name)}</text>')  # fmt: skip
        lx += 24 + 6.5 * len(name)
    out.append("</svg>")
    return "".join(out)


def matrix(rows: list[str], cols: list[str], counts: dict[tuple[str, str], int],
           diag_good: bool = True, cell: int = 46) -> str:  # fmt: skip
    """Count matrix (truth rows × predicted columns). Diagonal cells outlined green."""
    lw, top = 92, 34
    w, h = lw + cell * len(cols) + 8, top + cell * len(rows) + 8
    peak = max(counts.values() or [1])
    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" role="img">',
           f'<text x="{lw + cell * len(cols) / 2}" y="11" font-size="10" fill="{INK2}" '
           'text-anchor="middle">Predicted by parser</text>']  # fmt: skip
    for j, c in enumerate(cols):
        out.append(f'<text x="{lw + j * cell + cell / 2}" y="{top - 6}" font-size="10" '
                   f'fill="{INK}" text-anchor="middle">{esc(c)}</text>')  # fmt: skip
    for i, r in enumerate(rows):
        y = top + i * cell
        out.append(f'<text x="{lw - 8}" y="{y + cell / 2 + 4}" font-size="10" fill="{INK}" '
                   f'text-anchor="end">{esc(r)}</text>')  # fmt: skip
        for j, c in enumerate(cols):
            n = counts.get((r, c), 0)
            shade = RAMP[min(len(RAMP) - 1, round((len(RAMP) - 1) * n / peak))] if n else "#f4f5f8"
            stroke = f' stroke="{GOOD}" stroke-width="2"' if diag_good and r == c else ""
            x = lw + j * cell
            out.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cell - 2}" height="{cell - 2}" '
                       f'rx="4" fill="{shade}"{stroke}/>')  # fmt: skip
            fill = "#fff" if n and n / peak > 0.55 else INK
            out.append(
                f'<text x="{x + cell / 2}" y="{y + cell / 2 + 4}" font-size="12" '
                f'fill="{fill}" text-anchor="middle" font-weight="600">{n or ""}</text>'
            )
    out.append("</svg>")
    return "".join(out)


def strip(parts: list[tuple[str, float]], width: int = 640) -> str:
    """Share-of-voice strip with a 2px gap between segments and direct labels."""
    total = sum(v for _, v in parts) or 1
    out = [f'<svg viewBox="0 0 {width} 52" width="100%" role="img">']
    x = 0.0
    for name, v in parts:
        w = width * v / total
        out.append(f'<rect x="{x}" y="0" width="{max(0, w - 2)}" height="30" rx="4" '
                   f'fill="{BRAND.get(name, INK3)}"/>')  # fmt: skip
        out.append(f'<text x="{x + 6}" y="20" font-size="11" fill="#fff" font-weight="600">'
                   f"{pct(v, 0)}</text>")  # fmt: skip
        out.append(f'<text x="{x + 2}" y="46" font-size="10" fill="{INK}">{esc(name)}</text>')
        x += w
    out.append("</svg>")
    return "".join(out)


def table(headers: list[str], rows: list[list[Any]], numeric: set[int] = frozenset()) -> str:
    th = "".join(f'<th class="{"r" if i in numeric else ""}">{esc(h)}</th>'
                 for i, h in enumerate(headers))  # fmt: skip
    body = "".join(
        "<tr>" + "".join(f'<td class="{"r" if i in numeric else ""}">{c}</td>'
                         for i, c in enumerate(r)) + "</tr>"
        for r in rows
    )  # fmt: skip
    return f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


def ok(flag: bool) -> str:
    return ('<span class="ok">✔ correct</span>' if flag
            else '<span class="bad">✖ wrong</span>')  # fmt: skip


def review_box(section: str) -> str:
    return (f'<div class="review"><b>Manual review — {esc(section)}</b>'
            '<span>☐ Checked&nbsp;&nbsp; ☐ Agree&nbsp;&nbsp; ☐ Disagree</span>'
            '<span class="line">Reviewer ______ &nbsp; Date ______ &nbsp; Notes '
            "____________________________</span></div>")  # fmt: skip


# ---------------------------------------------------------------- real data


def load_real(run_id: str | None = None) -> dict[str, Any] | None:
    """A run with its visibility and sources. Default: the latest measured panel run."""
    try:
        from src.api import queries
        from src.db import get_conn
        from src.diagnostics.repository import load_source_share, load_visibility

        with get_conn() as conn:
            if run_id:
                run_ = queries.run_detail(conn, run_id)
            else:
                runs = [r for r in queries.list_runs_full(conn)
                        if r["diagnosed"] and r["run_type"] == "baseline"]  # fmt: skip
                run_ = runs[0] if runs else None
            if not run_:
                return None
            return {"run": run_, "visibility": load_visibility(conn, run_["run_id"]),
                    "sources": load_source_share(conn, run_["run_id"])}  # fmt: skip
    except Exception as exc:  # the sandbox report must still build without a database
        logger.warning("Real-data section skipped: %s", exc)
        return None


# ---------------------------------------------------------------- shared sections


def section_real(
    real: dict[str, Any] | None,
    title: str = "9. Real data: brand comparison",
    lead: str = "Latest measured panel run",
) -> str:
    if not real:
        return (f"<section><h2>{esc(title)}</h2>"
                "<p>Database not available; section skipped.</p></section>")  # fmt: skip
    run_ = real["run"]
    vis = [v for v in real["visibility"] if v["category"] == "ALL"]
    vis = sorted(vis, key=lambda v: list(BRAND).index(v["brand"]) if v["brand"] in BRAND else 9)
    n = vis[0]["n_responses"] if vis else 0
    brands = [v["brand"] for v in vis]
    f = lambda k: [float(v[k]) if v[k] is not None else None for v in vis]  # noqa: E731
    mr = f("mention_rate")
    cis = [wilson_ci(round(x * n), n) if x is not None else None for x in mr]
    valid = [c for c in cis if c]
    overlap = bool(valid) and max(lo for lo, _ in valid) <= min(hi for _, hi in valid)
    overlap_note = (
        "All intervals overlap, so this run cannot say which brand is mentioned most."
        if overlap
        else "Some intervals do not overlap: those differences are unlikely to be chance alone."
    )
    # one series per brand so each bar wears its brand colour
    mention = grouped(["Mention rate"], {b: [v] for b, v in zip(brands, mr, strict=True)},
                      BRAND, ci={b: [c] for b, c in zip(brands, cis, strict=True)},
                      width=520, height=200)  # fmt: skip
    ranks = f("avg_rank")
    rank_chart = grouped(["Average list position"],
                         {b: [v] for b, v in zip(brands, ranks, strict=True)}, BRAND,
                         vmax=max([x for x in ranks if x] or [1]) * 1.2,
                         fmt=lambda v, *_: f"#{v:.1f}", width=520, height=190)  # fmt: skip
    sov = strip([(v["brand"], float(v["share_of_voice"] or 0)) for v in vis])
    cats = sorted({v["category"] for v in real["visibility"] if v["category"] != "ALL"})
    cat_series = {b: [next((float(v["mention_rate"]) for v in real["visibility"]
                            if v["brand"] == b and v["category"] == c
                            and v["mention_rate"] is not None), None) for c in cats]
                  for b in brands}  # fmt: skip
    cat_chart = grouped(cats, cat_series, BRAND, height=240)
    cat_n = {c: next((v["n_responses"] for v in real["visibility"] if v["category"] == c), 0)
             for c in cats}  # fmt: skip
    src = [s for s in real["sources"] if s["category"] == "ALL"][:12]
    src_bars = hbars([(s["domain"], s["n_citations"], ACCENT) for s in src],
                     vmax=max([s["n_citations"] for s in src] or [1]),
                     fmt=lambda v: str(int(v)), row_h=20)  # fmt: skip
    vis_rows = [[v["brand"], pct(float(v["mention_rate"]) if v["mention_rate"] is not None
                                 else None),
                 (f"{pct(c[0], 0)}–{pct(c[1], 0)}" if c else "n/a"),
                 pct(float(v["share_of_voice"]) if v["share_of_voice"] is not None else None),
                 f"#{float(v['avg_rank']):.2f}" if v["avg_rank"] is not None else "n/a"]
                for v, c in zip(vis, cis, strict=True)]  # fmt: skip
    return f"""
<section class="break">
  <h2>{esc(title)}</h2>
  <p>{esc(lead)}: {esc(run_["provider"])} {esc(run_["model"])}, started
  {esc(str(run_["started_at"])[:16])} UTC. {run_["n_responses"] - run_["n_errors"]} answers
  ({run_["n_errors"]} of {run_["n_responses"]} calls failed; see the run's errors).
  <b>Small sample:</b> the 95% intervals below are wide, and the rank figures are subject to
  the list-position issues in section 3.</p>
  <h3>Mention rate with 95% Wilson interval (n={n})</h3>
  <p class="note">Whiskers show the range the true rate plausibly lies in. {overlap_note}</p>
  {mention}
  <h3>Average list position (lower is better)</h3>{rank_chart}
  <h3>Share of voice</h3>{sov}
  {
        table(
            ["Brand", "Mention rate", "95% interval", "Share of voice", "Avg position"],
            vis_rows,
            {1, 2, 3, 4},
        )
    }
  <h3>Mention rate by category</h3>
  <p class="note">Answers per category: {", ".join(f"{c} {k}" for c, k in cat_n.items())}.
  Categories with 1–2 answers cannot support conclusions.</p>
  {cat_chart}
  <h3>Most cited sites</h3>{src_bars}
  {review_box("Real data")}
</section>"""


CSS = f"""
@page {{ size: A4; margin: 14mm 13mm 16mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: "Segoe UI", Arial, sans-serif; color: {INK}; font-size: 10.5pt;
       line-height: 1.45; margin: 0; background: {SURF}; }}
h1 {{ font-size: 24pt; margin: 0 0 4px; letter-spacing: -0.01em; }}
h2 {{ font-size: 15pt; margin: 18px 0 6px; border-bottom: 2px solid {ACCENT};
      padding-bottom: 3px; }}
h3 {{ font-size: 11pt; margin: 12px 0 4px; color: {INK2}; }}
p {{ margin: 4px 0 8px; max-width: 170mm; }}
.note {{ color: {INK2}; font-size: 9pt; }}
section {{ page-break-inside: auto; }}
.break {{ page-break-before: always; }}
.cover {{ border-left: 6px solid {ACCENT}; padding: 6px 0 6px 14px; margin-bottom: 10px; }}
.meta {{ color: {INK2}; font-size: 9.5pt; }}
.tiles {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin: 10px 0; }}
.tile {{ border: 1px solid {GRID}; border-radius: 6px; padding: 8px 10px; }}
.tl {{ font-size: 8.5pt; color: {INK2}; }}
.tv {{ font-size: 18pt; font-weight: 700; margin: 2px 0; }}
.ts {{ font-size: 8pt; color: {INK3}; }}
table {{ width: 100%; border-collapse: collapse; margin: 6px 0 10px; font-size: 9pt; }}
th, td {{ border-bottom: 1px solid {GRID}; padding: 4px 6px; text-align: left;
          vertical-align: top; }}
th {{ color: {INK2}; font-weight: 600; background: #f6f7f9; }}
tr {{ page-break-inside: avoid; }}
.r {{ text-align: right; font-variant-numeric: tabular-nums; }}
.ok {{ color: {GOOD}; font-weight: 600; white-space: nowrap; }}
.bad {{ color: {BAD}; font-weight: 600; white-space: nowrap; }}
.row {{ display: flex; gap: 16px; align-items: flex-start; }}
.grow {{ flex: 1; min-width: 0; }}
.review {{ border: 1px dashed {INK3}; border-radius: 6px; padding: 6px 10px; margin: 10px 0;
           font-size: 9pt; display: flex; flex-wrap: wrap; gap: 4px 18px;
           page-break-inside: avoid; }}
.review .line {{ flex-basis: 100%; color: {INK2}; }}
code {{ font-family: Consolas, monospace; font-size: 8.5pt; }}
.cases {{ columns: 2; column-gap: 14px; }}
.case {{ break-inside: avoid; margin-bottom: 8px; font-size: 8.5pt; }}
.case pre {{ white-space: pre-wrap; background: #f6f7f9; border-radius: 4px; padding: 5px 7px;
             margin: 2px 0 0; font-size: 8pt; font-family: Consolas, monospace; }}
.findings li {{ margin-bottom: 6px; max-width: 170mm; }}
.sign td {{ border: 1px solid {GRID}; height: 26px; }}
svg text {{ font-family: "Segoe UI", Arial, sans-serif; }}
"""


def find_browser() -> str | None:
    for c in [shutil.which("chrome"), shutil.which("msedge"), shutil.which("google-chrome"),
              shutil.which("chromium"),
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]:  # fmt: skip
        if c and Path(c).exists():
            return c
    return None


def to_pdf(html_path: Path, pdf_path: Path) -> None:
    browser = find_browser()
    if not browser:
        raise RuntimeError("Chrome or Edge is needed to print the PDF; the HTML was saved.")
    subprocess.run(
        [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()],
        check=True, capture_output=True, timeout=120,
    )  # fmt: skip
