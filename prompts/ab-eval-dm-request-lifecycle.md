# Direct-Message Request Lifecycle

Ecosystem goal: Establish safe first-contact messaging so Juke can become a social music platform without exposing users to uncontrolled DMs.

Evaluation focus: Tests state-machine design, permission modeling, negative tests, and restraint around a feature that could easily sprawl into realtime, push, and client work.

Review the repository handbook, task board, backend guidance, and messaging architecture notes. Promote this idea into an `ITERATIVE` backend-only task that defines a first slice for DM request state: initial message creates a request, receiver can accept/ignore/block, sender cannot send a second pre-acceptance message, and non-participants see 404. Implement only models/API/tests for that slice; leave websocket, push, group chat, and client UI out of scope.
