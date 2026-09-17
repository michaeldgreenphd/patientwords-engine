"""PatientWords-owned execution of multi-turn register experiments through the
Petri harness (docs/petri_integration_design.md).

The package splits by Python version so the engine's 3.11 suite never imports
the harness:

- 3.11-safe, no Inspect or Petri import: ``framework`` (contracts and digests),
  ``seeds`` (seed validation), ``envlock`` (environment-lock verification),
  ``transcripts`` (transcript 0.2 records), ``rules`` (rule outcomes),
  ``sanitizer`` (raw-log allowlist projection), ``manifest`` (run manifest and
  hash chain), ``spend`` (pricing and pre-flight bounds), ``seal`` (holdout
  checks over publishable outputs), ``judge_runner`` (per-turn judge of record).
- 3.12 only, imported on demand: ``controller`` (the scripted auditor Agent),
  ``task`` (study Task assembly and ``eval`` invocation) and ``adapter`` (the
  deterministic ``.eval`` reader).

Nothing here writes medical vocabulary into Python: every text a run stages
comes from the seed file, and every judge instruction from a prompt file.
"""
