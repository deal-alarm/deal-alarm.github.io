#!/usr/bin/env python3
"""Hot-Deals-Generator: holt stündlich die besten Amazon-Rabatte über die
offizielle Amazon Creators API und baut daraus

  site/index.html          – die öffentliche Deal-Seite (für den TikTok-Link)
  site/deals.json          – dieselben Daten maschinenlesbar
  storefront-auswahl.md    – Top-Auswahl zum Übertragen in die Storefront-Liste

Benötigte Umgebungsvariablen (als GitHub-Secrets hinterlegen, nie ins Repo):
  CREATORS_API_CLIENT_ID, CREATORS_API_CLIENT_SECRET, AMAZON_PARTNER_TAG

Aufruf:
  python3 deals.py           # echte Daten über die API
  python3 deals.py --demo    # Beispieldaten, nur zur lokalen Vorschau
"""

import argparse
import datetime as dt
import html
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent
TOKEN_URL = "https://api.amazon.co.uk/auth/o2/token"  # EU-Region (Credential-Version 3.2)
API_URL = "https://creatorsapi.amazon/catalog/v1/searchItems"
TZ = ZoneInfo("Europe/Berlin")

RESOURCES = [
    "itemInfo.title",
    "images.primary.large",
    "offersV2.listings.price",
    "offersV2.listings.dealDetails",
    "offersV2.listings.availability",
    "offersV2.listings.isBuyBoxWinner",
    "offersV2.listings.merchantInfo",
]


def post_json(url, body, headers):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def get_token():
    data = post_json(
        TOKEN_URL,
        {
            "grant_type": "client_credentials",
            "client_id": os.environ["CREATORS_API_CLIENT_ID"],
            "client_secret": os.environ["CREATORS_API_CLIENT_SECRET"],
            "scope": "creatorsapi::default",
        },
        {},
    )
    return data["access_token"]


def search(token, cfg, category, keyword, partner_tag):
    body = {
        "partnerTag": partner_tag,
        "marketplace": cfg["marketplace"],
        "keywords": keyword,
        "searchIndex": category["searchIndex"],
        "minSavingPercent": cfg["min_rabatt_prozent"],
        "minReviewsRating": cfg["min_bewertung"],
        "condition": "New",
        "itemCount": 10,
        "languagesOfPreference": [cfg["sprache"]],
        "resources": RESOURCES,
    }
    headers = {"Authorization": f"Bearer {token}", "x-marketplace": cfg["marketplace"]}
    try:
        data = post_json(API_URL, body, headers)
    except urllib.error.HTTPError as e:
        print(f"  ! {category['name']}/{keyword}: HTTP {e.code} {e.read()[:300]!r}", file=sys.stderr)
        return []
    return (data.get("searchResult") or {}).get("items") or []


def parse_item(item, category):
    """Wandelt ein API-Item in einen flachen Deal um; None, wenn kein echter Rabatt."""
    listings = (item.get("offersV2") or {}).get("listings") or []
    listing = next((l for l in listings if l.get("isBuyBoxWinner")), listings[0] if listings else None)
    if not listing:
        return None
    price = listing.get("price") or {}
    money = price.get("money") or {}
    savings = price.get("savings") or {}
    basis = (price.get("savingBasis") or {}).get("money") or {}
    pct = savings.get("percentage")
    if not money.get("amount") or not pct:
        return None
    deal = listing.get("dealDetails") or {}
    return {
        "asin": item.get("asin"),
        "titel": ((item.get("itemInfo") or {}).get("title") or {}).get("displayValue", ""),
        "bild": (((item.get("images") or {}).get("primary") or {}).get("large") or {}).get("url"),
        "link": item.get("detailPageURL"),
        "preis": money["amount"],
        "preis_text": money.get("displayAmount") or f"{money['amount']:.2f} €",
        "statt": basis.get("amount"),
        "statt_text": basis.get("displayAmount"),
        "rabatt": int(pct),
        "blitzangebot": bool(deal) or listing.get("type") == "LIGHTNING_DEAL",
        "deal_ende": deal.get("endTime"),
        "kategorie": category["name"],
    }


def score(d):
    # Hoher Rabatt zählt am meisten, Blitzangebote bekommen einen Bonus.
    return d["rabatt"] + (15 if d["blitzangebot"] else 0)


def collect(cfg, demo):
    if demo:
        return demo_deals(cfg)
    partner_tag = os.environ["AMAZON_PARTNER_TAG"]
    token = get_token()
    deals = {}
    for cat in cfg["kategorien"]:
        print(f"Suche {cat['name']} …")
        for kw in cat["suchbegriffe"]:
            for item in search(token, cfg, cat, kw, partner_tag):
                d = parse_item(item, cat)
                if d and (d["asin"] not in deals or score(d) > score(deals[d["asin"]])):
                    deals[d["asin"]] = d
            time.sleep(1.1)  # Startlimit der API: 1 Anfrage pro Sekunde
    return list(deals.values())


def demo_deals(cfg):
    import random

    random.seed(1)
    out = []
    for cat in cfg["kategorien"]:
        for i in range(6):
            statt = random.choice([29.99, 49.99, 89.99, 199.0, 349.0])
            pct = random.randint(cfg["min_rabatt_prozent"], 60)
            preis = round(statt * (100 - pct) / 100, 2)
            out.append({
                "asin": f"DEMO{cat['name'][:3].upper().replace(' ', '')}{i}",
                "titel": f"BEISPIEL – {cat['suchbegriffe'][i % len(cat['suchbegriffe'])]} Produkt {i + 1}",
                "bild": None,
                "link": "#",
                "preis": preis,
                "preis_text": f"{preis:.2f} €".replace(".", ","),
                "statt": statt,
                "statt_text": f"{statt:.2f} €".replace(".", ","),
                "rabatt": pct,
                "blitzangebot": random.random() < 0.3,
                "deal_ende": None,
                "kategorie": cat["name"],
            })
    return out


def render_html(cfg, groups, stand):
    e = html.escape
    sections = []
    for cat in cfg["kategorien"]:
        deals = groups.get(cat["name"]) or []
        if not deals:
            continue
        cards = []
        for d in deals:
            img = f'<img src="{e(d["bild"])}" alt="" loading="lazy">' if d["bild"] else '<div class="noimg">📦</div>'
            statt = f'<s>{e(d["statt_text"])}</s>' if d.get("statt_text") else ""
            flash = '<span class="flash">⚡ Blitzangebot</span>' if d["blitzangebot"] else ""
            cards.append(f"""
      <a class="card" href="{e(d['link'])}" target="_blank" rel="sponsored noopener">
        <span class="badge">-{d['rabatt']} %</span>{flash}
        {img}
        <h3>{e(d['titel'])}</h3>
        <p class="price"><b>{e(d['preis_text'])}</b> {statt}</p>
        <span class="cta">Zum Deal* →</span>
      </a>""")
        sections.append(f"""
    <section>
      <h2>{cat['emoji']} {e(cat['name'])}</h2>
      <div class="grid">{''.join(cards)}
      </div>
    </section>""")

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(cfg['seitentitel'])}</title>
<style>
  :root {{ --bg:#fff7f2; --card:#fff; --text:#1d1d1f; --muted:#6b6b70; --hot:#e8452c; --line:#f0dcd2; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#141214; --card:#1f1c1f; --text:#f3f0f0; --muted:#a8a2a4; --hot:#ff6a4d; --line:#332c30; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text); font:16px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }}
  header {{ padding:28px 16px 12px; text-align:center; }}
  h1 {{ margin:0 0 6px; font-size:1.8rem; }}
  .stand {{ color:var(--muted); font-size:.9rem; margin:0; }}
  main {{ max-width:1100px; margin:0 auto; padding:0 16px 32px; }}
  h2 {{ margin:28px 0 12px; font-size:1.3rem; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:12px; }}
  .card {{ position:relative; display:flex; flex-direction:column; background:var(--card); border:1px solid var(--line); border-radius:14px; padding:12px; color:inherit; text-decoration:none; }}
  .card:hover {{ border-color:var(--hot); }}
  .card img, .noimg {{ width:100%; aspect-ratio:1; object-fit:contain; background:#fff; border-radius:8px; }}
  .noimg {{ display:grid; place-items:center; font-size:2.5rem; }}
  .badge {{ position:absolute; top:8px; left:8px; background:var(--hot); color:#fff; font-weight:700; padding:2px 8px; border-radius:999px; font-size:.85rem; }}
  .flash {{ position:absolute; top:8px; right:8px; background:#ffd60a; color:#1d1d1f; font-size:.75rem; padding:2px 6px; border-radius:999px; }}
  h3 {{ font-size:.9rem; font-weight:500; margin:10px 0 6px; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }}
  .price {{ margin:auto 0 6px; }} .price b {{ color:var(--hot); font-size:1.1rem; }} .price s {{ color:var(--muted); font-size:.85rem; }}
  .cta {{ font-size:.85rem; font-weight:600; }}
  footer {{ color:var(--muted); font-size:.8rem; padding:0 16px 32px; max-width:1100px; margin:0 auto; }}
</style>
</head>
<body>
<header>
  <h1>{e(cfg['seitentitel'])}</h1>
  <p class="stand">Stand: {stand:%d.%m.%Y, %H:%M} Uhr · wird stündlich aktualisiert</p>
</header>
<main>{''.join(sections) or '<p>Gerade keine passenden Deals – schau in einer Stunde wieder vorbei!</p>'}
</main>
<footer>
  <p>*Werbelinks: Als Amazon-Partner verdiene ich an qualifizierten Verkäufen. Für dich ändert sich am Preis nichts.</p>
  <p>Preise und Verfügbarkeit entsprechen dem angegebenen Stand und können sich jederzeit ändern. Maßgeblich ist der Preis, der zum Zeitpunkt des Kaufs auf Amazon angezeigt wird.</p>
</footer>
</body>
</html>
"""


def render_storefront(cfg, top, stand):
    lines = [
        f"# Storefront-Auswahl für „{cfg["seitentitel"]}“",
        "",
        f"Stand: {stand:%d.%m.%Y, %H:%M} Uhr. Diese Produkte in die Storefront-Liste übernehmen "
        "(Amazon-App → Profil → Storefront → Liste bearbeiten → Produkt per ASIN suchen).",
        "",
        "| # | Rabatt | Preis | Kategorie | ASIN | Produkt |",
        "|---|---|---|---|---|---|",
    ]
    for i, d in enumerate(top, 1):
        flash = " ⚡" if d["blitzangebot"] else ""
        title = d["titel"].replace("|", "/")[:80]
        lines.append(f"| {i} | -{d['rabatt']} %{flash} | {d['preis_text']} | {d['kategorie']} | `{d['asin']}` | {title} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="Beispieldaten statt API (nur Vorschau)")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    deals = collect(cfg, args.demo)
    deals.sort(key=score, reverse=True)

    groups = {}
    for d in deals:
        groups.setdefault(d["kategorie"], [])
        if len(groups[d["kategorie"]]) < cfg["max_deals_pro_kategorie"]:
            groups[d["kategorie"]].append(d)

    stand = dt.datetime.now(TZ)
    site = ROOT / "site"
    site.mkdir(exist_ok=True)
    (site / "index.html").write_text(render_html(cfg, groups, stand), encoding="utf-8")
    (site / "deals.json").write_text(
        json.dumps({"stand": stand.isoformat(), "deals": deals}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (ROOT / "storefront-auswahl.md").write_text(
        render_storefront(cfg, deals[: cfg["storefront_auswahl_anzahl"]], stand), encoding="utf-8"
    )
    print(f"{len(deals)} Deals gefunden, Seite geschrieben: {site / 'index.html'}")


if __name__ == "__main__":
    main()
