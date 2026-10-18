# Identity resolution retrospective — 18 October 2026

## Outcome and limits

We recovered a searchable evidence inventory: 53,190,053 subject/identifier/source facts, not 53 million unique tracks. That improved our ability to investigate identity disagreements. It did not establish better serving coverage or authorize broad identity merges.

The most consequential discovery came later. Original MusicBrainz recording rows named Herbaliser tracks, but their associated ISRCs led the earlier saved Spotify searches to Super Numeri tracks. The original dump reproduced those recording/ISRC associations, so the inconsistency preceded the new evidence loader. Source ISRC assignment/transcription errors are likely; provider catalog errors have not been independently excluded. We did not infer corrected codes by swapping digits.

Eight suspect Spotify aliases, eight ISRC aliases and eight hydration records were reversibly quarantined. These were pre-existing API-derived mappings, not bad aliases introduced by the new evidence load. The three best documented alternative-ID candidates remain supported examples, not an approved batch. Bulk jobs remain paused.

The original 86.22% score measured agreement with saved API/ISRC references. Holding eight invalid references changed eligible agreement to 86.24%; it did not establish independently measured accuracy or pass the unchanged 95% gate. The remediation reassessment replayed the frozen comparison with fresh checks for the exclusions; it was not a new review of all 39,398 comparisons.

## Where my approach fell short

**I trusted the reference path too early.** Exact agreement between the queried ISRC and returned ISRC proves the API answered that query consistently. It does not prove that the ISRC belonged to the MusicBrainz recording. I initially described the disagreement score as precision and gave too much weight to that supposed reference. Comparing the original recording names with a few disagreement examples earlier would have exposed this assumption sooner.

**I blurred different kinds of corroboration.** Two identifiers sharing an MSID across separate listens is weaker than both appearing on one listen, and one joint listen is weaker than independent recording verification. The 583 “direct MBID support” cases were an aggregate evidence category, not 583 proven matches. The later report made that distinction, but it should have been explicit from the start. Missing same-event identifiers mean unverified, not wrong.

**The first audit normalizer was too lossy.** ASCII-only normalization damaged Turkish names and could erase non-Latin titles. Literal multi-artist matching flagged compatible joined credits. Version-word comparison missed different remaster years. The exporter also read `listened_at` while the source used `timestamp`, weakening the event fingerprint. We corrected the reviewed cases, but those errors show why a small source-verified fixture set should precede a billion-row audit. The new tests preserve Unicode, require complete credits, retain version years, and reject partial-credit matches.

**I underexplained why we were reading already ingested data.** ListenBrainz events were already in PostgreSQL and archives were already extracted. Older projections had discarded some identity identifiers and metadata. This run recovered that missing evidence; it did not need to re-ingest the basic listening history. My status reports should have separated archive extraction, field recovery, evidence loading, graph promotion and serving coverage in ordinary language.

**The first quarantine was containment, not a complete safeguard.** Serving honored inactive aliases, but raw-fact bridge/clustering code could still reuse the same ISRC associations, and hydration could reactivate a held alias on the same owner. We kept jobs paused and explicitly documented that limitation. The follow-up code now shares the hold policy across the reviewed consumers and checks staged writes again before committing.

**I should have preserved reference metadata and challenged outliers earlier.** The original bridge retained identifiers but not recording titles and artist credits. That forced expensive archive rereads to diagnose a basic mismatch. The new source-versioned metadata store retains names, credits, durations and archive checksums. A metadata-only backfill avoids repeating completed identity extraction/load phases.

## What worked

- Checkpoints and evidence-only extraction prevented repeated loads and kept graph promotion separate from recovery. We inspected the combined extraction command rather than accidentally invoking its redirect-writing path.
- The 95% gate remained intact. There were no Spotify API requests from the investigation, no deletion, and no broad alias/redirect activation.
- Original file/line examples and archive recording-ID joins let us move from a pattern to an auditable source-level diagnosis.
- Quarantine used existing inactive statuses, explicit reasons, exact before-images and verified rollback plans. The deployed resolver was checked with both held cases and unaffected controls.
- Reports separated immutable source facts, operational holds and proposed repairs. We preserved valid MusicBrainz URL/listen evidence instead of deleting it merely because a contaminated reference disagreed.

## Changes to the next investigation

| Earlier weakness | New practice | Evidence required |
| --- | --- | --- |
| Reference treated as truth | Validate the reference and disputed link symmetrically | Source recording names/credits plus saved provider metadata; contradictions and missing fields explicit |
| Full corpus read before rule validation | Start with a bounded source-verified set spanning positives, contradictions and uncertainty | Real-event fixtures pass before a large scan |
| Aggregate counts mistaken for proof | Label aggregate, joint-event, repeated and independently reviewed support separately | Exact file, line, timestamp, identifiers and deduplication definition |
| Overaggressive normalization | Preserve Unicode and recording/version distinctions; hold uncertain spellings | Turkish/non-Latin, joined-credit, partial-credit and master-year regression cases |
| Quarantine applied only at serving | One shared hold policy, whole-group veto and checks at write time | Mixed-cluster and post-staging hold tests; no reactivation by same-owner hydration |
| Exclusions improve an apparent score | Freeze the population and publish held cases and denominator | Held cases never enter the success numerator; eligible agreement cannot silently replace the gate metric |
| Work confused with deployment | State implementation, test, deployment, backfill and activation separately | A release checklist and explicit operational state |

Future audits should use a frozen population and a blind validation sample, with separate supported/contradictory/unverified labels. Community metadata, repeated listens and the ISRC query itself are correlated evidence; none should be presented as independent audio verification. If the available local evidence cannot establish a case, leave it unverified and report that limitation rather than manufacturing confidence.

## Current deliverable and next decision

The safeguards and regression tests are implemented on `codex/identity-reference-safeguards`; validation results are recorded in the task handoff. They have not been deployed to Neptune's live services. The operational quarantines remain active. After review, the next controlled rollout is migration, metadata-only backfill for the relevant June sources, a bounded dry run and a reviewed audit. Bulk hydration and graph promotion stay paused until that evidence supports the next step.

See [safeguards and rollout instructions](identity-reference-safeguards.md). Detailed historical evidence and reversible quarantine records are saved locally under `/Users/embario/.local/state/juke-identity-reports/20261017/` and on Neptune under `/srv/data/backups/juke/mlcore-handoffs/identity-20261017/`.
