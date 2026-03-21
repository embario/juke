---
id: mlcore-phase1c-hybrid-training-data-corpus
title: ML Core Phase 1c - Build unified training corpus and LTR examples from multi-source signals
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - training-data
complexity: 5
updated_at: 2026-03-19
---

## Goal

Create a single training corpus abstraction that combines SearchHistory + ListenBrainz interactions and metadata/content features into labeled examples for hybrid learning-to-rank training and evaluation.

## Scope

- Add a corpus builder service that emits feature rows:
  - query item `juke_id`
  - candidate item `juke_id`
  - label (positive/negative)
  - collaborative, metadata, and content features
- Replace/extend current cooccurrence basket-only path so it can consume:
  - normalized external interactions
  - `source` filters (e.g., internal-only, external-only, blended)
- Implement deterministic data split helpers for train/validation/test using stable hashed partitioning.
- Add hard-negative generation policies:
  - popular-unplayed
  - same-artist-not-played
  - same-style-not-played
- Add dataset hash/evidence to training artifacts.

## Out Of Scope

- Hybrid model architecture finalization.
- Candidate ANN infra changes.

## Acceptance Criteria

- `build_training_corpus()` produces comparable row schema across sources.
- Label generation rules are documented and deterministic.
- Split generation is stable as data grows (hash-bucket, not count-based modulus).
- Negative sampling includes configurable strategies and class balance controls.
- Corpus builder accepts lineage inputs (dataset/source version, ingest run IDs, policy gate IDs).

## Execution Notes

### Proposed components

- `backend/mlcore/services/training_corpus.py` (new): unified feature extraction + negative sampling.
- `backend/mlcore/services/training_examples.py` (new): label logic and serialization.
- `backend/mlcore/management/commands/build_mlcore_training_dataset.py` (new):
  - `--dataset-sources`
  - `--split`
  - `--output-format`
- `backend/mlcore/services/cooccurrence.py`: adapt basket source loading to unified event abstraction.
- `backend/mlcore/services/evaluation.py`: optional reuse for validation split compatibility.

### Suggested tests

- `tests/unit/test_training_corpus.py`
- `tests/unit/test_negative_sampling.py`
- `tests/unit/test_training_dataset_split_stability.py`

## Risks

- Missing `juke_id` resolution can drop valuable interaction rows.
- Class imbalance if negative sampling is not tuned per-source.
- Schema inflation if every feature source writes denormalized columns.

## Handoff

- Next: wire this corpus output into a dedicated hybrid trainer task with reproducible artifact lineage.
- Blocker: none.

## Dependencies

- Must start after:
  - `mlcore-phase1a-listenbrainz-ingestion`
  - `mlcore-phase1b-metadata-enrichment-ingestion`
- Suggested sequence:
  - internal `SearchHistoryResource` support remains available, but blended sources should be validated before phase-2 training.
- Successor: `mlcore-phase2-hybrid-ranker-training-orchestration`.
