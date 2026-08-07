# Agent context index

Read only the document that matches the task; this keeps onboarding context
small while retaining the non-obvious project decisions.

| Task | Read |
| --- | --- |
| Any code, configuration, test, or documentation change | [Development workflow](development.md) |
| Interpreting the original DBLP paper | [DBLP paper brief](ring-3d-paper-brief.md) |
| Evaluating a DBLP criticism or validity threat | [DBLP known flaws](ring-3d-known-flaws.md) |
| Changing packet loss, control traffic, priority classes, or recovery | [Loss-tolerant RDMA decision](loss-tolerant-rdma-decision.md), then [implementation-gap audit](loss-tolerant-rdma-audit.md) |
| Deciding whether a paper mechanism maps to ASTRA-sim | [ASTRA-sim pivot](ring-3d-astra-pivot.md) |
| Interpreting Ring-3D claims, limits, or roadmap | [Ring-3D research context](ring-3d-research-context.md) |
| Editing profiles, CLR, microbursts, or analysis | [Ring-3D local guide](../../experiments/ring_3d/AGENTS.md), then [Ring-3D glossary](../../experiments/ring_3d/GLOSSARY.md) |
| Editing policy selection, completion, or telemetry bridge | [ns-3 policy implementation](../../astra-sim/network_frontend/ns3/POLICY_IMPLEMENTATION.md) |
| Defining an experimental comparison or interpreting results | [Validation protocol](../../experiments/ring_3d/VALIDATION_PROTOCOL.md) |
| Diagnosing a slow, stalled, or timed-out simulation; changing hot-path or recovery code; sizing CI time budgets | [Simulation liveness and performance discipline](simulation-liveness-and-performance.md) |
| Compiling the ns-3 backend on a machine without root or system protobuf/boost/MPI | [Rootless ephemeral build](rootless-ephemeral-build.md) |
| Creating a commit | [Git commit skill](../../.github/skills/git-commits/SKILL.md) |
| Creating or changing an agent skill | [Skill authoring guide](../../.github/skills/authoring-skills/SKILL.md) |

The root [AGENTS.md](../../AGENTS.md) is the authoritative short operational
contract. Keep it concise; place domain-specific material in this directory or
a nearer nested `AGENTS.md`.

## Ring-3D reading order

1. Read the [paper brief](ring-3d-paper-brief.md) for the original DBLP
	protocol and empirical assumptions.
2. Read the [known-flaws register](ring-3d-known-flaws.md) before proposing a
	reproduction, deliberate abstraction, baseline, or claim.
3. Read the [loss-tolerant RDMA decision](loss-tolerant-rdma-decision.md)
	before changing packet loss, a control class, priority handling, or recovery.
4. Read the [implementation-gap audit](loss-tolerant-rdma-audit.md) before
	selecting an implementation boundary or claiming support for that decision.
5. Read the [ASTRA-sim pivot](ring-3d-astra-pivot.md) to distinguish the
	current model from the paper; it does not prescribe a remedy.
6. Load the local [glossary](../../experiments/ring_3d/GLOSSARY.md) and
	[implementation guide](../../astra-sim/network_frontend/ns3/POLICY_IMPLEMENTATION.md)
	only when changing a named parameter or code path.
7. Treat [the validation protocol](../../experiments/ring_3d/VALIDATION_PROTOCOL.md)
	as the source of truth for estimands, controls, and decision rules.