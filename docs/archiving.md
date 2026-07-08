# Archiving big render runs

The public gallery (the `patientwords` repo) is a **demonstration**: it carries
every scenario's numbers plus the interactive circuit render for only the most
consequential ones. A large run's full render set is heavy — a few hundred MB of
HTML and PNG — and shouldn't live in the site repo or, long-term, in this
engine's git working tree. This is how the split works.

## The two halves

**Public demo (site repo).** `scripts/export_frontend_simulated.py` copies the
top-N most consequential renders (flips first, then largest language penalty) to
`patientwords/modes/simulated/`, capped by `--max-renders` (default **25**).
Every scenario still gets its full row of measurements in
`data/simulated_scenarios.json`; only the heavy interactive render is withheld
for the long tail. A data-only scenario's page says so and can link to the
back-end archive.

**Back-end archive (this repo's Releases).** The complete render set for a run
is zipped and attached to a **GitHub Release** on this private engine repo. That
keeps the durable full copy reachable without bloating the site or git.

## Archiving a run

1. **Bundle** (local, testable — no network):

   ```bash
   python scripts/archive_run.py \
       --runs trace_out/pairs_20260707T023656Z trace_out/pairs_20260707T023704Z \
       --tag renders-20260707 --out-dir dist
   ```

   Writes `dist/renders-20260707.zip` (full HTML + PNG) and a small
   `dist/renders-20260707.manifest.json` (run list, sizes, sha256). `--no-pngs`
   drops the multi-MB PNGs and keeps just the interactive HTML + summaries.

2. **Upload to a Release** — the `archive_renders` workflow does this in CI
   (it has a token). Fire it the same way as the trace workflow, by pushing a
   trigger file:

   ```jsonc
   // .github/trigger/archive-renders.json
   {
     "tag": "renders-20260707",
     "runs": ["trace_out/pairs_20260707T023656Z",
              "trace_out/pairs_20260707T023704Z"],
     "no_pngs": false,
     "prune": false
   }
   ```

   The workflow rebuilds the bundle, creates (or updates) the Release
   `renders-20260707`, uploads the zip, and commits the ~1KB manifest to
   `render_archives/renders-20260707.manifest.json` with the Release URL filled
   in. The zip itself is never committed (`dist/` is gitignored).

3. **Link the demo to the archive** (optional): re-run the export with the
   Release URL so data-only scenario pages get a "download the full render set"
   link:

   ```bash
   python scripts/export_frontend_simulated.py --frontend ../patientwords \
       --stamps 20260707T023656Z,20260707T023704Z --no-pngs \
       --archive-url https://github.com/michaeldgreenphd/patientwords-engine/releases/tag/renders-20260707
   ```

   The export prints this reminder automatically whenever a publish exceeds 100
   scenarios.

## `prune`: keeping git lean

Set `"prune": true` in the trigger to have the workflow `git rm` the archived
runs' `index_*.png` from the branch **after** a successful upload. The
interactive HTML and summaries stay in git (the export and back-end browsing
still work); the full-resolution PNGs live only in the Release. This shrinks
fresh clones — it does not rewrite history, so existing blobs remain in the
pack. Default is `false`.

## Why GitHub Releases (not Google Drive)

Releases live next to the code, need no extra credentials (CI's built-in
`GITHUB_TOKEN` covers them), and each asset carries a stable download URL. A
single Release asset can be up to 2 GB, comfortably above a full run's size.
Reach for external storage (e.g. Drive) only if a bundle outgrows that or you
want the archive off GitHub entirely.
