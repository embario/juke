# iOS JukeKit Migration Slice

Ecosystem goal: Advance iOS app consolidation by moving one real Juke app path onto shared JukeKit infrastructure.

Evaluation focus: Tests targeted Swift refactoring, shared-package judgment, build hygiene, and whether the model avoids damaging project configuration or migrating every app at once.

Review the repository handbook, iOS guidance, current reusable-library task context, iOS architecture notes, and existing JukeKit implementation. Promote this idea into an `ITERATIVE` task for one small Juke app migration slice that consumes existing JukeKit networking/profile/auth functionality and removes duplicate app-local logic. Keep the scope to one service or model path, verify narrowly, and use the required iOS build script only if runtime validation is truly needed.
