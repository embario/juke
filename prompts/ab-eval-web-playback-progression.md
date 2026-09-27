# Web Playback Progression Hardening

Ecosystem goal: Improve listening reliability by making web playback honor album context and match backend playback expectations.

Evaluation focus: Tests handoff-reading, regression-test design, and whether the model validates existing work instead of replacing it with a broad playback rewrite.

Review the repository handbook, task board, backend playback implementation, and web playback implementation. Promote this idea into an `ASYNC` task or update the existing playback task if it is still the right home. Focus on validating album-context playback progression with backend and web unit tests, using mocked Spotify behavior and avoiding live playback dependencies.
