# æsthetoica

A marbling tray that fills each day with things that pass Lyme Regis unseen. The sheet begins at
midnight, every visitor watches today's sheet fill (and can stir their own copy), and at the next
midnight the official print is pulled, given a page, and a line is written in Thomasin Gale's ledger.

## How it fits together

```
every 15 min  fetch.yml   ──►  pipeline/fetch.py  ──►  data branch: days/YYYY-MM-DD.json
                                                          │  (read live by the tray via raw.githubusercontent.com)
00:25 UTC     nightly.yml ──►  fetch.py --final (adds meteors)
                           ──►  ledger.py          (Anthropic API: Thomasin's line)
                           ──►  render.mjs         (headless Chromium replays the day, saves the print)
                           ──►  build.py           (sheet pages, archive, sitemap, index.json)
                           ──►  push main  ──►  Cloudflare Pages deploys site/
```

Live data goes to a separate `data` branch so the 15-minute updates don't trigger a Cloudflare deploy each time.
Only the nightly job commits to `main`, so you get one deploy a day.

| Path | What it is |
|---|---|
| `site/index.html` | The tray. Self-contained. Falls back to simulation for any missing feed. |
| `site/sheets/<no>/` | Generated: one page per pulled sheet (`sheet.jpg`, `og.jpg`, `index.html`). |
| `pipeline/fetch.py` | Nearest live magnetometer, Chambon-la-Forêt (INTERMAGNET HAPI; UK stations are ~10 days late), Kiel (NMDB NEST), Elexon frequency, GraceDB, Wikipedia, Global Meteor Network. |
| `pipeline/ledger.py` | Writes the day's ledger line from the day's facts. |
| `pipeline/render.mjs` | Pulls the print. Software GL, so it runs on GitHub's GPU-less runners (allow ~10–15 minutes). |
| `pipeline/build.py` | Sheet pages with VisualArtwork JSON-LD, the archive, `sitemap.xml`, `robots.txt`, `site/data/index.json`. |

Page routes inside the tray: `/#on-the-word` (the pamphlet), `/#sheets` (archive), `/#day-YYYY-MM-DD` (replay any day).
Render mode: `/?render=YYYY-MM-DD`.

## Setup

1. Push this folder to a new **public** GitHub repo (public so the tray can read the data branch from
   raw.githubusercontent.com without a token).
2. Create the empty data branch:
   `git switch --orphan data && mkdir days && touch days/.keep && git add days && git commit -m "data" && git push -u origin data && git switch main`
3. In `site/index.html`, set the data source to that branch:
   `<meta name="data-base" content="https://raw.githubusercontent.com/andykillworth/aesthetoica/data/">`
4. Add the repo secret `ANTHROPIC_API_KEY` (Settings → Secrets and variables → Actions). Optional variable: `ANTHROPIC_MODEL`.
5. Cloudflare Pages: connect the repo, production branch `main`, no build command, output directory `site`.
6. Optional but recommended (GitHub's scheduler can run late): trigger `fetch.yml` every 15 minutes and `nightly.yml`
   at 00:25 from cron-job.org with a `workflow_dispatch` call and a fine-grained token that has Actions: write.
7. Run **nightly** once by hand from the Actions tab to check everything end to end.

## Check on the first real run

Each source fails on its own without stopping the others, and the tray simulates anything missing. These are the
parts most likely to need a tweak once real responses come back:

- **NMDB NEST**: the query parameter names in `nmdb()` follow NEST's URL form; compare with a URL built on nest.nmdb.eu.
  Confirm KIEL2 reports in real time; any real-time station works.
- **INTERMAGNET HAPI**: the dataset is discovered from `/hapi/catalog` (first `had/…/PT1M/…`), and the parser handles HDZ or XYZ.
- **Elexon**: expects `data[].measurementTime` and `data[].frequency`.
- **GraceDB**: uses the `created:` range query; public alerts only, retracted events skipped. During gaps between
  observing runs this is simply empty.
- **Global Meteor Network**: reads the daily trajectory summary files and keeps meteors that ended within 400 km of Lyme Regis.

## Credits and licences

- Chambon-la-Forêt observatory, Institut de physique du globe de Paris, via INTERMAGNET (CC BY-NC 4.0).
- NMDB (www.nmdb.eu) and the Kiel neutron monitor. Free for non-commercial use; acknowledge NMDB and the station.
- Elexon: "Contains BSC information that is available from Elexon at no charge and which is licensed under the Elexon Public Data Licence."
- Global Meteor Network (CC BY 4.0). LIGO, Virgo and KAGRA public alerts via GraceDB. Wikimedia recent changes.
- Lighthouse characters from Trinity House.

INTERMAGNET and NMDB data are non-commercial. Selling prints (for example "your sheet" for a birthday) needs
written permission from BGS and the NMDB station, or a version of the sheet without those two layers.
These credits also appear in the pamphlet (`/#on-the-word`).
