"""Round 10, revision 1: three bounded wording corrections, applied to the original builder as exact replacements.

Reads ``../round10_20261112/build_round10.py`` (the author's second version, commit 9a495c763, unchanged; the
first version is commit c75a8e757), checks its SHA-256, applies the
replacements below (each must occur exactly the stated number of times) and writes ``build_round10.py`` here.
Run that builder to regenerate ``families.json``, ``check_pairs.json``, ``sources.md`` and ``self_check.md``;
run it a second time after the engine checker has written ``check_report.json``. ``revisions.json`` is written
by ``python apply_revisions.py --record`` once both ``families.json`` files exist.

No family is added or removed, no family id changes, and 21 families are byte-identical to the original.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIGINAL_DIR = HERE.parent / "round10_20261112"
ORIGINAL_COMMIT = "9a495c763"
FIRST_VERSION_COMMIT = "c75a8e757"
ORIGINAL_BUILDER_SHA256 = "d2932cc3666df80c2348dee0df12fb615b352151946783c74e0020a5923182ca"
ORIGINAL_FAMILIES_SHA256 = "52b38ef3a88f489b269c3483c22f6332ac4ed71079b2be546239ddc54858c63a"

REVISIONS = [
    {"family_id": "r10-11",
     "reason": "'2 prescribed clinic pills' (and 'doctor pills') can be read as two tablets; fact f2 is two medication trials.",
     "replacements": [
         ("unimproved after 2 prescribed clinic pills", "unimproved after 2 different prescribed clinic medicines", 5),
         ("after 2 prescribed clinic pills", "after 2 different prescribed clinic medicines", 3),
         ('tiredness that failed "', 'tiredness that did not "', 1),
         ('"2 prescribed doctor pills while talking normally today so I should see a"',
          '"improve on 2 different medicines prescribed by his doctor while talking normally today so I should see a"', 1),
         ('"that failed 2 prescribed doctor pills"', '"that did not improve on 2 different medicines prescribed by his doctor"', 1),
         ("Exact 17-word vs 17-word single-span swap between 'My 16 year old son has 4 months of '",
          "Single continuous 17-word vs 18-word span swap between 'My 16 year old son has 4 months of '", 1),
         ("17-for-17", "17-for-18", 1)]},
    {"family_id": "r10-12",
     "reason": "The second everyday wording said 'avoidance of reminders in traffic' where fact f3 is driving avoidance, and "
               "did not say that the nightmares are nightly or the flashbacks by day (fact f2). It now states the same facts "
               "as the other variants. The sourced expression 'avoidance of reminders' is no longer in any text, so its "
               "source entry is removed.",
     "replacements": [
         ('"I was in a car accident 3 months ago and get nightmares and flashbacks with avoidance of "\n'
          '                "reminders in traffic and startle easily with no blackouts so I should see a"',
          '"I was in a car accident 3 months ago and get nightmares every night with flashbacks in the day "\n'
          '                "that stop me driving and I startle easily with no blackouts so I should see a"', 1),
         ('"everyday_paraphrase": "nightmares and flashbacks",', '"everyday_paraphrase": "nightmares every night with flashbacks in the day",', 1),
         ('"everyday_paraphrase": "avoidance of reminders in traffic and startle easily",',
          '"everyday_paraphrase": "that stop me driving and I startle easily",', 1),
         ("""            src_item(
                "avoidance of reminders",
                "dixon_2026",
                "authors' summary",
                "Results — Casualties’ experience of MVC-entrapment, para 1",
                (
                    "Other symptoms described following MVC-entrapment included nightmares, avoidance of "
                    "reminders, heightened physiological arousal, and ongoing anxiety; in some cases meeting "
                    "criteria for ASD or PTSD, as explored below."
                ),
                None,
            ),
""", "", 1)]},
    {"family_id": "r10-20",
     "reason": "'Spooned nails' (and 'scooped nails' in the second everyday wording) is unlikely patient wording. Fact f2 in "
               "the author's second version is 'pale inner eyelids and spoon shaped nails'; the everyday texts now use that "
               "phrase. Both second wordings said 'brittle', which fact f2 no longer states and the main pair never stated; "
               "it is removed from both so that every variant states the same qualities.",
     "replacements": [
         ('"eyelids and spooned nails but easy resting breathing today so I need to go to the"',
          '"eyelids and spoon shaped nails but easy resting breathing today so I need to go to the"', 1),
         ('"eyelids and spooned nails and am gasping for air at rest today so I need to go to the"',
          '"eyelids and spoon shaped nails and am gasping for air at rest today so I need to go to the"', 1),
         ('eyelids and spooned "', 'eyelids and spoon shaped "', 1),
         ('src_item("spooned nails", None)', 'src_item("spoon shaped nails", None)', 1),
         ('"with pale inner eyelids and spooned nails"', '"with pale inner eyelids and spoon shaped nails"', 2),
         ("vs 'pale inner eyelids and spooned nails')", "vs 'pale inner eyelids and spoon shaped nails')", 1),
         ('"eyelids and brittle scooped nails while breathing easily at rest today so I need to go to the"',
          '"eyelids and nails curved like spoons while breathing easily at rest today so I need to go to the"', 1),
         ('"plus pale lower eyelids and brittle scooped nails"', '"plus pale lower eyelids and nails curved like spoons"', 1),
         ('"accompanied by palpebral conjunctival pallor and brittle spoon nails with normal resting "',
          '"accompanied by palpebral conjunctival pallor and spoon nails with normal resting "', 1),
         ('"accompanied by palpebral conjunctival pallor and brittle spoon nails"',
          '"accompanied by palpebral conjunctival pallor and spoon nails"', 1),
         ("19-word vs 20-word span swap between 'I have had 6 weeks of '",
          "19-word vs 21-word span swap between 'I have had 6 weeks of '", 1)]},
    {"family_id": None,
     "reason": "The builder accepts only words of its audited vocabulary. Eight ordinary words used by the revised texts are added.",
     "replacements": [("    return set(AUDITED_VOCABULARY)\n",
                       "    return set(AUDITED_VOCABULARY) | {\"curved\", \"did\", \"different\", \"improve\", \"medicines\", "
                       "\"shaped\", \"spoons\", \"stop\"}  # revision 1\n", 1)]},
    {"family_id": None, "reason": "Output headers name this folder.",
     "replacements": [("(`round10_20261112`)", "(`round10_20261112_rev1`)", 2)]},
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> int:
    source = ORIGINAL_DIR / "build_round10.py"
    if sha(source) != ORIGINAL_BUILDER_SHA256:
        print("The original builder is not the recorded version", file=sys.stderr)
        return 1
    text = source.read_text(encoding="utf-8")
    for revision in REVISIONS:
        for old, new, count in revision["replacements"]:
            if text.count(old) != count:
                print(f"{revision['family_id']}: expected {count} of {old[:60]!r}, found {text.count(old)}", file=sys.stderr)
                return 1
            text = text.replace(old, new)
    (HERE / "build_round10.py").write_text(text, encoding="utf-8")
    print("wrote build_round10.py")
    return 0


def record() -> int:
    if sha(ORIGINAL_DIR / "families.json") != ORIGINAL_FAMILIES_SHA256:
        print("The original families.json is not the recorded version", file=sys.stderr)
        return 1
    before = {f["family_id"]: f for f in json.loads((ORIGINAL_DIR / "families.json").read_text(encoding="utf-8"))}
    after = {f["family_id"]: f for f in json.loads((HERE / "families.json").read_text(encoding="utf-8"))}
    assert list(before) == list(after)
    reasons = {r["family_id"]: r["reason"] for r in REVISIONS if r["family_id"]}
    changed = []
    for fid in before:
        if before[fid] == after[fid]:
            continue
        assert fid in reasons, fid
        texts = {name: {"before": before[fid]["texts"][name], "after": after[fid]["texts"][name]}
                 for name in before[fid]["texts"] if before[fid]["texts"][name] != after[fid]["texts"][name]}
        other = sorted(k for k in before[fid] if k != "texts" and before[fid][k] != after[fid].get(k))
        changed.append({"family_id": fid, "reason": reasons[fid], "texts_changed": texts,
                        "texts_unchanged": sorted(n for n in before[fid]["texts"] if n not in texts),
                        "other_fields_changed": other,
                        "unchanged": ["reference_facts", "right_care", "carrier_frame", "target_token", "condition",
                                      "level_rationale"]})
        for key in ("reference_facts", "right_care", "carrier_frame", "target_token", "condition", "level_rationale"):
            assert before[fid][key] == after[fid][key], (fid, key)
    assert sorted(c["family_id"] for c in changed) == sorted(reasons)
    doc = {"revision": "round10_20261112_rev1",
           "original": {"folder": "round10_20261112", "commit": ORIGINAL_COMMIT, "first_version_commit": FIRST_VERSION_COMMIT,
                        "families_sha256": ORIGINAL_FAMILIES_SHA256, "build_round10_sha256": ORIGINAL_BUILDER_SHA256},
           "revised": {"families_sha256": sha(HERE / "families.json"), "build_round10_sha256": sha(HERE / "build_round10.py")},
           "made_by": "Claude session, at the owner's instruction of 2026-11-12; not by the original author",
           "outcome_blind": "No measured result was opened. No round 10 measurement exists.",
           "families_unchanged": sorted(f for f in before if before[f] == after[f]),
           "families_changed": changed}
    (HERE / "revisions.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote revisions.json: {len(changed)} changed, {len(doc['families_unchanged'])} unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(record() if "--record" in sys.argv else build())
