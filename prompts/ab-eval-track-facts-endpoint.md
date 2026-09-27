# Track Fun-Facts Endpoint

Ecosystem goal: Add a reusable catalog intelligence surface that can enrich CLI, web, and mobile now-playing experiences.

Evaluation focus: Tests service isolation, cache-key correctness, failure-path coverage, and whether the model avoids real LLM calls or fabricated provider behavior.

Review the repository handbook, task board, backend catalog patterns, and existing internal LLM service patterns. Promote this idea into an `ASYNC` task spec, then implement the backend-only track facts endpoint with mocked LLM calls, model-versioned cache behavior, authenticated access, and explicit not-found and provider-failure tests. Do not make real OpenAI calls from tests or local validation.
