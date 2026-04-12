---
id: mlcore-dataset-viability-assessment
title: ML Core - Dataset viability assessment for research vs commercial use
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - research
  - compliance
complexity: 3
updated_at: 2026-02-12
---

## Goal

Produce a decision-ready dataset assessment for post-MusicBrainz sources, covering legal viability, operational effort, and ML applications.

## Scope

- Inventory candidate datasets beyond MusicBrainz (for example: ListenBrainz, AcousticBrainz, Spotify MPD, and other relevant open music corpora).
- For each dataset, document license terms and classify usage as:
- production-commercial allowed
- research-only allowed
- prohibited/unclear
- Map dataset characteristics to MLCore applications:
- metadata graph enrichment
- cooccurrence and behavioral rankers
- content/audio embedding enrichment
- offline evaluation and benchmark corpora
- Define onboarding recommendations:
- source tier (`production_approved`, `research_only`, `blocked`)
- required legal/policy checks before ingestion
- expected engineering work for ingestion, normalization, and governance
- Propose a phased adoption order aligned with existing MLCore phases.

## Out Of Scope

- Implementing new ingestion pipelines.
- Shipping model changes based on newly assessed datasets.

## Acceptance Criteria

- A written assessment exists at `/Users/embario/Documents/juke/docs/arch/MLCORE_DATASET_VIABILITY_ASSESSMENT.md`.
- Each candidate dataset has explicit license classification and citation links.
- Each dataset includes at least one concrete ML application fit and one risk/tradeoff.
- Recommendation section defines which sources can enter production next, and under what policy gates.
- Task handoff notes include unresolved legal or product decisions.

## Execution Notes

- Key files:
- `/Users/embario/Documents/juke/docs/arch/INDEPENDENT_ML_CORE_ARCHITECTURE.md`
- `/Users/embario/Documents/juke/docs/arch/MLCORE_DATASET_VIABILITY_ASSESSMENT.md` (new)
- `/Users/embario/Documents/juke/tasks/mlcore-phase0-corpus-manifest-and-license-policy.md`
- Commands:
- `docker compose exec backend python manage.py test`
- Risks:
- License interpretations may require counsel review before production use.
- Dataset availability/hosting constraints may change recommended adoption order.

## Handoff

- Completed:
  - 2026-03-29 ListenBrainz commercialization investigation completed against both project docs/tasks and MetaBrainz primary-source policy pages.
  - Repo context already treated ListenBrainz as the intended primary behavioral dataset for a monetization-safe recommender:
    - `docs/arch/INDEPENDENT_ML_CORE_ARCHITECTURE.md` defines a monetization-first posture and allows MetaBrainz/ListenBrainz datasets where terms allow production use.
    - `docs/juke_dataset_report_full.md` classifies ListenBrainz as a production-safe primary source, with privacy protection and pseudonymous user handling.
    - `tasks/mlcore-phase1a-listenbrainz-ingestion.md` already hashes source user IDs and strips the decision down to whether the source should stay `research_only` or move to `production_approved`.
  - MetaBrainz primary sources confirm the commercial-use posture for ListenBrainz dumps:
    - MetaBrainz datasets page lists ListenBrainz PostgreSQL dumps as `Commercial use: Allowed` under `Creative Commons Zero (CC0)`.
    - MetaBrainz GDPR statement says ListenBrainz listens are public, are included in public data dumps, and are used to build recommendation engines.
  - Determination for Juke: ListenBrainz full + incremental dumps should be classified as `production_approved` for commercialization of cooccurrence, behavioral, and hybrid-ranking ML artifacts, provided Juke continues to:
    - ingest only the dump data needed for training/evaluation,
    - hash or otherwise pseudonymize source user identifiers,
    - avoid carrying user-facing profile fields into production ML artifacts,
    - preserve periodic full-refresh/rebuild capability because incremental dumps do not include deletions.
- Next:
  - Keep `docs/arch/MLCORE_DATASET_VIABILITY_ASSESSMENT.md` as the canonical source-review matrix for future dataset approvals.
  - Split mixed-rights datasets into separate MLCore source ids before they are added to `SOURCE_CLASSIFICATION`.
- Blockers:
  - None for commercialization of ListenBrainz-derived ML itself.
  - Counsel review is still prudent if product plans expand beyond model training/ranking into exposing raw ListenBrainz identities, profile fields, or user-level exports.
