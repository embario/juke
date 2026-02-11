---
id: dep-upgrade-phase-1
title: Full-Stack Dependency Upgrade Audit + Execution Hooks
status: ready
priority: p1
owner: unassigned
area: platform
label: ALL/GENERAL
complexity: 5
updated_at: 2026-02-11
---

## Goal

Upgrade third-party dependencies across backend, web, Android, and iOS with minimal breakage risk using phased, test-gated batches.

## Scope

- Produce and execute a phased dependency-upgrade plan for all first-party surfaces.
- Stabilize dependency resolution where currently non-deterministic.
- Gate each phase with relevant automated and manual validation.
- Document compatibility hotspots and rollback guidance.

## Out Of Scope

- A single monolithic "upgrade everything" PR.
- Unrelated refactors not required to complete dependency upgrade phases.
- Live package-registry version discovery in this environment.

## Acceptance Criteria

- Dependency upgrades are delivered in phased PRs with passing tests per subsystem.
- Python dependency resolution is deterministic/reproducible in CI and local compose.
- Backend, web, Android, and iOS upgrade notes include known incompatibilities and rollback instructions.
- CI/test coverage gaps impacted by upgrades are closed or explicitly documented with manual gates.

## Execution Notes

- Current findings:
- Highest risk is unpinned Python requirements in `/Users/embario/Documents/juke/backend/requirements.txt` and `/Users/embario/Documents/juke/backend/recommender_engine/requirements.txt`.
- Backend compatibility hotspots include social auth fallback imports in `/Users/embario/Documents/juke/backend/juke_auth/views.py` and OpenAI integration in `/Users/embario/Documents/juke/backend/tunetrivia/services.py`.
- Web compatibility hotspots include router/runtime dependencies in `/Users/embario/Documents/juke/web/src/router.tsx` and `/Users/embario/Documents/juke/web/package.json`.
- Android toolchain is already modern in `/Users/embario/Documents/juke/mobile/android/juke/build.gradle.kts` and should be upgraded in isolation from app libs.
- iOS third-party exposure is concentrated around Spotify SDK usage in `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock.xcodeproj/project.pbxproj`.
- Dev/CI environment drift exists around Postgres image pinning in `/Users/embario/Documents/juke/docker-compose.yml` and `/Users/embario/Documents/juke/docker-compose.ci.yml`.
- CI currently lacks dedicated Android TuneTrivia coverage in `/Users/embario/Documents/juke/.github/workflows/ci.yml`.
- Recommended phase order:
- Stabilize deterministic dependency inputs first.
- Upgrade tooling before runtime libraries.
- Upgrade backend and recommender non-core libraries before core frameworks.
- Upgrade web runtime libraries after build tooling stabilizes.
- Upgrade Android app libraries while initially holding AGP/Kotlin/Gradle steady.
- Upgrade iOS Spotify SDK after backend/web/mobile API surfaces are stable.
- Run major upgrades one-by-one in separate PRs.
- Key files:
- `/Users/embario/Documents/juke/backend/requirements.txt`
- `/Users/embario/Documents/juke/backend/recommender_engine/requirements.txt`
- `/Users/embario/Documents/juke/backend/juke_auth/views.py`
- `/Users/embario/Documents/juke/backend/tunetrivia/services.py`
- `/Users/embario/Documents/juke/web/package.json`
- `/Users/embario/Documents/juke/web/src/router.tsx`
- `/Users/embario/Documents/juke/mobile/android/juke/build.gradle.kts`
- `/Users/embario/Documents/juke/mobile/android/juke/gradle/wrapper/gradle-wrapper.properties`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock.xcodeproj/project.pbxproj`
- `/Users/embario/Documents/juke/docker-compose.yml`
- `/Users/embario/Documents/juke/docker-compose.ci.yml`
- `/Users/embario/Documents/juke/.github/workflows/ci.yml`
- Commands:
- `git checkout -b chore/dependency-upgrades-phase-1`
- `git status --short`
- `docker compose -f docker-compose.ci.yml up -d db redis backend`
- `docker compose -f docker-compose.ci.yml exec -T backend ruff check`
- `docker compose -f docker-compose.ci.yml exec -T backend python manage.py test`
- `docker compose -f docker-compose.ci.yml run --rm web npm run test`
- `scripts/test_mobile.sh --android-only -p juke`
- `scripts/test_mobile.sh --android-only -p shotclock`
- `scripts/test_mobile.sh --ios-only -p juke`
- `scripts/test_mobile.sh --ios-only -p shotclock`
- `scripts/test_mobile.sh --ios-only -p tunetrivia`
- Risks:
- Backend major upgrades can break auth and social-login pipelines.
- Recommender/runtime upgrades can introduce numeric and binary compatibility regressions.
- Android and iOS toolchain/library bumps can require coordinated CI/runtime updates.
- Live latest-version lookup still requires a machine with registry/network access.

## Handoff

- Completed:
- Initial cross-stack dependency-risk audit completed and captured.
- Phase ordering and validation hooks documented.
- Next:
- Add deterministic pinning for backend/recommender dependencies.
- Align dev/CI Postgres pinning strategy.
- Add or document gating for Android TuneTrivia CI coverage.
- Execute phased upgrade batches and validate after each batch.
- Blockers:
- Package-registry access is required to resolve current-vs-latest version targets before final upgrade selection.
