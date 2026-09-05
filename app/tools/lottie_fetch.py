"""Add-on A: source the ten state-cue animations from LottieFiles (public GraphQL, the same API the
LottieFiles MCP wraps), keep only free public files <= 100 KB, download the JSON, recolour to the app
palette, and write docs/ASSETS.md + app/assets/lottie/manifest.json.

    python app/tools/lottie_fetch.py          (needs internet; run once, commit the results)
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "app" / "assets" / "lottie"
DOCS = ROOT / "docs" / "ASSETS.md"
GQL = "https://graphql.lottiefiles.com/2022-08"
MAX_BYTES = 100 * 1024
# app palette (interview_cracker.dart themeColor)
PALETTE = {
    "primary": (0x0F, 0x6E, 0x56), "secondary": (0x1F, 0x3A, 0x5F), "tertiary": (0xE0, 0x7A, 0x2F),
    "success": (0x2A, 0x9D, 0x4B), "warning": (0xE0, 0xA1, 0x00), "error": (0xC0, 0x3A, 0x2B),
}
# cue -> (search queries in preference order, palette role, where it is used)
CUES = {
    "mic_idle": (["microphone pulse", "mic pulse", "microphone idle"], "primary", "Room - idle (not listening, not speaking)"),
    "listening_wave": (["voice waveform", "sound wave", "audio wave"], "primary", "Room - isListening"),
    "thinking_dots": (["typing dots", "loading dots", "three dots loading"], "secondary", "Room - thinking (answer end -> tts_start)"),
    "speaking": (["speaker sound", "speaker wave", "audio speaker"], "tertiary", "Room - isSpeaking"),
    "countdown_warning": (["timer warning", "countdown timer", "hourglass"], "warning", "Room - countdownSeconds <= 10"),
    "qr_scan": (["qr code scan", "qr scanner", "scan qr"], "secondary", "Pair - while scanning"),
    "connected_check": (["success check", "check mark success", "checkmark"], "success", "Pair - connectionState == connected"),
    "offline": (["no internet", "offline", "no connection"], "error", "Pair/Room - connectionState == disconnected/error"),
    "empty_history": (["empty box", "empty state", "no data"], "secondary", "History - no sessions"),
    "report_success": (["confetti success", "trophy", "celebration"], "success", "Report - when the report arrives"),
}

SEARCH = """query($q:String!,$first:Int!){ searchPublicAnimations(query:$q, first:$first){
  edges{ node{ id name slug url jsonUrl lottieUrl lottieFileSize frameRate downloads likesCount createdBy{ username firstName lastName } } } } }"""


def gql(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(GQL, data=body, headers={"Content-Type": "application/json", "User-Agent": "interview-cracker/asset-fetch"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def pick(queries: list[str]) -> dict | None:
    best = None
    for q in queries:
        try:
            d = gql(SEARCH, {"q": q, "first": 12})
        except Exception as e:  # noqa: BLE001
            print(f"  search {q!r} failed: {e}", file=sys.stderr)
            continue
        for e in d.get("data", {}).get("searchPublicAnimations", {}).get("edges", []):
            n = e["node"]
            size = n.get("lottieFileSize") or 0
            if not n.get("jsonUrl") or size <= 0 or size > MAX_BYTES:
                continue
            score = (n.get("downloads") or 0) + 3 * (n.get("likesCount") or 0)
            if best is None or score > best[0]:
                best = (score, n, q)
        if best:
            break
    return None if best is None else {**best[1], "query": best[2]}


def recolour(anim: dict, rgb: tuple[int, int, int]) -> int:
    """Replace every solid fill/stroke colour with the palette colour (alpha kept). Returns the count."""
    target = [rgb[0] / 255, rgb[1] / 255, rgb[2] / 255]
    n = 0

    def walk(o):
        nonlocal n
        if isinstance(o, dict):
            if o.get("ty") in ("fl", "st") and isinstance(o.get("c"), dict):
                k = o["c"].get("k")
                if isinstance(k, list) and len(k) >= 3 and all(isinstance(x, (int, float)) for x in k[:3]):
                    o["c"]["k"] = target + k[3:]
                    n += 1
                elif isinstance(k, list):  # animated colour keyframes
                    for kf in k:
                        if isinstance(kf, dict):
                            for key in ("s", "e"):
                                v = kf.get(key)
                                if isinstance(v, list) and len(v) >= 3:
                                    kf[key] = target + v[3:]
                                    n += 1
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(anim)
    return n


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for cue, (queries, role, usage) in CUES.items():
        print(f"{cue}: searching {queries} ...")
        n = pick(queries)
        if not n:
            print(f"  NOT FOUND under {MAX_BYTES // 1024} KB", file=sys.stderr)
            rows.append((cue, None, role, usage, 0, 0))
            continue
        # the asset CDN rejects urllib's default UA with 403; a browser UA + referer is accepted
        dl = urllib.request.Request(n["jsonUrl"], headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) interview-cracker/asset-fetch", "Referer": "https://lottiefiles.com/", "Accept": "application/json,*/*"})
        raw = urllib.request.urlopen(dl, timeout=60).read()
        anim = json.loads(raw)
        changed = recolour(anim, PALETTE[role])
        out = OUT / f"{cue}.json"
        out.write_text(json.dumps(anim, separators=(",", ":")), encoding="utf-8")
        size = out.stat().st_size
        by = n.get("createdBy") or {}
        author = (by.get("username") or "").lstrip("/") or f"{by.get('firstName', '')} {by.get('lastName', '')}".strip() or "unknown"
        print(f"  -> {n['name']!r} by {author}  {size / 1024:.1f} KB  recoloured {changed} fills/strokes  {n['url']}")
        rows.append((cue, {**n, "author": author}, role, usage, size, changed))

    lines = [
        "# Assets - Lottie micro-animations (master prompt Add-on A)",
        "",
        "Sourced 2026-09-05 through the LottieFiles public GraphQL API (`graphql.lottiefiles.com/2022-08`, the surface the LottieFiles MCP wraps; the MCP endpoint itself returned 404 in this session). Only free public animations under the **Lottie Simple License** (https://lottiefiles.com/page/license), each <= 100 KB, recoloured to the app palette by `app/tools/lottie_fetch.py` (fills/strokes -> theme colour, motion untouched). Files live in `app/assets/lottie/`; they are embedded in the FlutterFlow custom widget `StateCue` so the app never fetches a network URL at runtime (offline demo).",
        "",
        "| Cue | File (palette role) | Used on | Source | Author | Size | License |",
        "|---|---|---|---|---|---|---|",
    ]
    for cue, n, role, usage, size, _ in rows:
        if n:
            lines.append(f"| `{cue}` | `app/assets/lottie/{cue}.json` ({role}) | {usage} | [{n['name']}]({n['url']}) | {n['author']} | {size / 1024:.1f} KB | Lottie Simple License |")
        else:
            lines.append(f"| `{cue}` | - | {usage} | not found <= 100 KB | | | |")
    lines += ["", "Rules applied: one cue at a time in the Room (no decorative motion), animations frozen when the OS reduced-motion setting is on (`MediaQuery.disableAnimations`), and the cue widget never touches the voice pipeline (pure UI driven by App State)."]
    DOCS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {cue: {"name": n["name"], "url": n["url"], "author": n["author"], "jsonUrl": n["jsonUrl"], "bytes": size, "role": role}
                for cue, n, role, usage, size, _ in rows if n}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nwrote {DOCS} and {len(manifest)}/{len(CUES)} assets to {OUT}")
    return 0 if len(manifest) == len(CUES) else 1


if __name__ == "__main__":
    sys.exit(main())
