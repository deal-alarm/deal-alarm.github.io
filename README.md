# Deal-Alarm 🔥 Top-Rabatte

Holt jede Stunde über die offizielle **Amazon Creators API** die besten Rabatte (Haushalt, Garten, TV & Sound, Kameras) und baut daraus:

- **`site/index.html`**: die öffentliche Deal-Seite, deren Link ins TikTok-Profil kommt
- **`storefront-auswahl.md`**: die Top 10 zum Übertragen in die Storefront-Liste „Deal-Alarm“

## Einstellungen (`config.json`)
- `min_rabatt_prozent`: ab welchem Rabatt ein Produkt aufgenommen wird (Standard 20 %)
- `min_bewertung`: Mindest-Sternebewertung (Standard 4)
- `kategorien`: Suchbegriffe pro Kategorie, frei erweiterbar

## Einrichtung (einmalig)
1. In Partnernet unter „Tools → Creators API“ Zugangsdaten anlegen (Region EU).
2. Neues GitHub-Repository anlegen und diesen Ordner hochladen.
3. Im Repository unter *Settings → Secrets and variables → Actions* drei Secrets anlegen:
   `CREATORS_API_CLIENT_ID`, `CREATORS_API_CLIENT_SECRET`, `AMAZON_PARTNER_TAG`.
4. *Settings → Pages → Source: GitHub Actions* wählen.
5. Unter *Actions* den Workflow „Hot Deals stündlich aktualisieren“ einmal von Hand starten.

Danach läuft das Update jede Stunde automatisch.

## Vorschau ohne API
`python3 deals.py --demo` erzeugt eine Seite mit Beispieldaten (nicht veröffentlichen).

## Partnerprogramm-Regeln, die eingebaut sind
- Werbelink-Hinweis im Seitenfuß und `rel="sponsored"` an allen Links
- Preise immer mit „Stand: …“-Zeitstempel, Aktualisierung stündlich
- Daten nur über die offizielle API, kein Scraping
