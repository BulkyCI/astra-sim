---
name: Experiment ledger entry
about: Record an experiment result permanently, with commit and run backreferences
title: 'Experiment run #<run-number> · <short-sha> · <ref>'
labels: experiment-ledger
assignees: ''
---

<!-- astra-ledger-run repository=<owner>/<repo> run_id=<run-id> -->

# Experiment run #\<run-number\> · \<short-sha\> · \<ref\>

> Permanent record of one experiment. Actions logs and artifacts expire; this
> issue does not. CI opens this issue automatically for every push and manual
> dispatch — file one by hand only for a run performed outside CI.

| Field | Value |
| --- | --- |
| Commit | [`<full-sha>`](../../commit/<full-sha>) |
| Tree | [browse at this commit](../../tree/<full-sha>) |
| Workflow run | [#\<run-number\>](../../actions/runs/<run-id>) |
| Attempt | [1](../../actions/runs/<run-id>/attempts/1) |
| Workflow | `CI` |
| Trigger | `<event>` by @\<actor\> |
| Ref | `refs/heads/<branch>` |

## Sections

| Section | Status | Parts | Content digest |
| --- | --- | --- | --- |
| \<job or evaluation name\> | ✅ success | 1 | `sha256 prefix` |

## Synchronization

State whether the reports below match the run outputs, and how that was
checked.

---

Each report is posted as its own comment carrying a machine-readable marker:

```text
<!-- astra-ledger key=<section-key> part=<i>/<n> status=<status> digest=<sha256> -->
```

A comment body is capped at 65,536 characters, so a long report is paginated
across several comments; the digest identifies the whole section, not the part,
and is the sha256 of the same file the run uploaded as an artifact. The Sections
table above is rebuilt from these markers when the run finishes, so it always
matches the comments below it.

GitHub exposes no API for issue file attachments, so binary reproducibility
bundles stay in the run's Actions artifacts and are referenced, not attached.

Do not hand-edit a CI-published comment. The publisher reconciles each section
by key on every run attempt and will overwrite manual edits.
