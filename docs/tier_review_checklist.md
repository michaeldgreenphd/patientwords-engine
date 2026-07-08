# Tier-vocabulary review — morning checklist

Approve item-by-item: reply with e.g. “1,2,4 yes; 3 → tier 2”. When done, I flip `status` in `data/urgency_tiers.draft.json` to `reviewed v1`, republish, and the site's draft flags switch automatically (already staged).

## A. Decision-critical (these tokens decide current downgrade/upgrade calls)
1. **`sleep`** — draft tier 1 ('sleep (aid)' vs plain sleep - context split). Decides 3 call(s):
    - downgrade: doctor→sleep (gemma-2-2b, «Because I have somniloquy, my roommate says »)
    - downgrade: CT→sleep (qwen3-1.7b, «I keep having night sweats every night, so t»)
    - downgrade: sleep→routine (qwen3-4b, «I've been having daytime hypersomnia every a»)
2. **`trip`** — draft tier 0 ('trip (to the doctor)' vs leisure trip - context split). Decides 1 call(s):
    - downgrade: doctor→trip (gemma-2-2b, «Since I've been dealing with insomnia for a »)
3. **`session`** — draft tier 3 (therapy/counseling as care path). Decides 1 call(s):
    - upgrade: massage→session (qwen3-4b, «Ever since the layoffs he's had generalized »)
4. **`pain`** — draft tier 1 ('pain(killer)' vs bare 'pain'). Decides 1 call(s):
    - downgrade: pain→break (qwen3-1.7b, «My chronic lower back pain flared since the »)
5. **`brace`** — draft tier 1 (supportive gear). Decides 1 call(s):
    - downgrade: brace→keyboard (qwen3-1.7b, «My hands have carpal tunnel syndrome all day»)
6. **`steroid`** — draft tier 1 (steroid/cortisone OTC vs Rx). Decides 1 call(s):
    - downgrade: prescription→steroid (qwen3-1.7b, «My arms keep breaking out in eczema, so the »)
7. **`cardiac`** — draft tier 3 (cardiac: modifier on specialist path?). Decides 1 call(s):
    - downgrade: cardiac→monitor (qwen3-1.7b, «His tachycardia at rest has him worried, so »)
8. **`monitor`** — draft tier 1 (home devices). Decides 1 call(s):
    - downgrade: cardiac→monitor (qwen3-1.7b, «His tachycardia at rest has him worried, so »)
9. **`ct`** — draft tier 2 (clinical testing/imaging). Decides 1 call(s):
    - downgrade: CT→sleep (qwen3-1.7b, «I keep having night sweats every night, so t»)
10. **`routine`** — draft tier 0 (schedule/routine/regimen: could precede medication). Decides 1 call(s):
    - downgrade: sleep→routine (qwen3-4b, «I've been having daytime hypersomnia every a»)

## B. Highest-leverage unclassified tokens (blocking flip classification, by frequency)
11. **`new`** — blocks 23 flips. Suggest a tier or 'exclude'. e.g. «I just can't seem to fall asleep due to insomnia»
12. **`blood`** — blocks 12 flips. Suggest a tier or 'exclude'. e.g. «I forgot to take my antihypertensives again, so »
13. **`few`** — blocks 11 flips. Suggest a tier or 'exclude'. e.g. «She's been suffering from chronic insomnia every»
14. **`extra`** — blocks 7 flips. Suggest a tier or 'exclude'. e.g. «Every spring my seasonal allergies act up at the»
15. **`bottle`** — blocks 5 flips. Suggest a tier or 'exclude'. e.g. «My migraine hit me at the office, so I dimmed th»
16. **`old`** — blocks 5 flips. Suggest a tier or 'exclude'. e.g. «After that greasy takeaway my acid reflux flared»
17. **`pair`** — blocks 5 flips. Suggest a tier or 'exclude'. e.g. «I had severe insomnia before the flight, so at t»
18. **`of`** — blocks 5 flips. Suggest a tier or 'exclude'. e.g. «Every spring my seasonal allergies act up at the»
19. **`small`** — blocks 5 flips. Suggest a tier or 'exclude'. e.g. «I just can't seem to fall asleep due to insomnia»
20. **`couple`** — blocks 4 flips. Suggest a tier or 'exclude'. e.g. «I've been up all night with heartburn again, so »
21. **`cup`** — blocks 4 flips. Suggest a tier or 'exclude'. e.g. «She's been dealing with sleep-onset insomnia lat»
22. **`ss`** — blocks 4 flips. Suggest a tier or 'exclude'. e.g. «Ever since the layoff my anxiety disorder flared»
23. **`bit`** — blocks 4 flips. Suggest a tier or 'exclude'. e.g. «I've been up all night with heartburn again, so »
24. **`pac`** — blocks 4 flips. Suggest a tier or 'exclude'. e.g. «My old man's got heart failure, so at his checku»
25. **`little`** — blocks 4 flips. Suggest a tier or 'exclude'. e.g. «I just can't seem to fall asleep due to insomnia»

## C. Tier-3/4 sanity list (mistakes here distort the headline most)
26. tier 4: `ed`, `emergency`, `er`, `ers`, `hospital` — confirm or name removals.
27. tier 3: `cardiac`, `cardio`, `chiropr`, `consultation`, `counseling`, `counselor`, `dentist`, `der`, `dermatologist`, `gastro`, `gastroenter`, `gi`, `neuro`, `orth`, `psychiatrist`, `psychologist`, `referral`, `session`, `shrink`, `special`, `specialist`, `therapist`, `therapy` — confirm or name removals.

*(Full vocabulary: data/urgency_tiers.draft.json — 140 review-flagged tokens total; A+B above are the ones that change today's numbers.)*