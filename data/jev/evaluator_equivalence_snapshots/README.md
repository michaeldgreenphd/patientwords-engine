# Reviewed evaluator-equivalence snapshots

This directory is the allowlist of historical registry bytes accepted by the
site contract validator. Each JSON filename is the SHA-256 of its exact bytes;
those bytes must match before its edges can authorize a pooled export.

Before changing `../evaluator_equivalence.json`, preserve the previous reviewed
bytes here under their digest. Snapshots are append-only: do not edit or delete
one to make a newer export pass. New or corrected equivalence claims belong in
the current registry and require review. Unknown digests and altered snapshots
refuse; a payload's self-declared graph alone never authorizes equivalence.
