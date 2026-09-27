# Social Follow/Unfollow Foundation

Ecosystem goal: Create the relationship graph needed for profile discovery, friend activity, social recommendations, and future messaging controls.

Evaluation focus: Tests relational modeling, privacy boundaries, pagination, and whether the model avoids building the full activity-feed roadmap too early.

Review the repository handbook, task board, backend guidance, and existing profile endpoint patterns. Promote this idea into an `ITERATIVE` task for a narrow follow/unfollow backend slice with relationship constraints, self-follow prevention, profile follow-state serialization, and pagination/privacy tests. Do not build a full activity feed or client UI unless the task spec explicitly scopes a minimal follow button contract.
