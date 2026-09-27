# Juke World API and Hook Hardening

Ecosystem goal: Make Juke World dependable as a live discovery surface by tightening the profile-location data contract and client loading behavior.

Evaluation focus: Tests API-contract hardening, async client-hook reasoning, and resource discipline by avoiding the tempting 3D rendering path.

Review the repository handbook, task board, web guidance, backend profile APIs, and Juke World architecture notes. Promote this idea into an `ITERATIVE` task focused on reliability of the globe data contract: backend bounds/zoom/limit/privacy tests and lightweight web API/hook tests for loading, caching, stale responses, and errors. Avoid WebGL, 3D rendering, browser screenshots, and simulator work in the first slice.
