# Matt Pocock's Agent Skills

This workspace has 27 engineering and productivity skills installed from
[mattpocock/skills](https://github.com/mattpocock/skills) — a curated set of
structured workflows for real engineering: grilling, spec/ticket flows, TDD,
code review, domain modelling, and more.

## How to invoke a skill

Skills are loaded on-demand. Type the skill name as a slash command (e.g.
`/grill-me`, `/tdd`, `/code-review`) or describe what you want and the model
will activate the right one.

Run `/ask-matt` (or `/setup-matt-pocock-skills` first if this is a new project)
to get oriented.

## Skill map

### Engineering (model- or user-invoked)

| Skill | When to reach for it |
|---|---|
| `ask-matt` | Not sure which skill fits? Start here. |
| `diagnosing-bugs` | Hard bug, intermittent flake, or regression. |
| `grill-with-docs` | Sharpen an idea via interview; writes GLOSSARY + ADRs. |
| `triage` | Move incoming issues/PRs through triage roles. |
| `improve-codebase-architecture` | Surface deepening opportunities as an HTML report. |
| `setup-matt-pocock-skills` | First-time setup: issue tracker, triage labels, domain docs. |
| `tdd` | Build features or fix bugs test-first (red-green-refactor). |
| `to-spec` | Synthesise the current conversation into a spec. |
| `to-tickets` | Break a spec into tracer-bullet tickets. |
| `wayfinder` | Chart a map for a huge, foggy multi-session effort. |
| `implement` | Implement work from a spec or tickets. |
| `implement-spec` | Orchestrate parallel subagent build from a full spec. |
| `prototype` | Throwaway program to answer one design question. |
| `research` | Background agent that reads primary sources and files a report. |
| `domain-modeling` | Sharpen domain language; write/edit GLOSSARY and ADRs. |
| `codebase-design` | Design a module's shape using the deep-module vocabulary. |
| `code-review` | Two-axis review (Standards + Spec) of diff since a fixed point. |
| `pr` | Write a PR body with before/after evidence. |
| `retro` | Retrospective: turn session learnings into env improvements. |
| `wizard` | Generate a bash wizard for steps only a human can take. |

### Productivity (model- or user-invoked)

| Skill | When to reach for it |
|---|---|
| `grill-me` | Relentless interview with no working directory (stateless). |
| `grilling` | The raw interview primitive used inside other skills. |
| `handoff` | Compact the conversation for another agent to pick up. |
| `teach` | Learn a concept over multiple sessions in this directory. |
| `to-questionnaire` | Turn a blocker into a questionnaire for someone else to fill in. |
| `wait-what` | Re-pitch the last message that didn't land. |
| `writing-for-agents` | Reference for writing SKILL.md, AGENTS.md, and agent-facing docs. |

## Recommended first steps

1. Run `/setup-matt-pocock-skills` to configure the issue tracker, triage labels,
   and domain doc layout that the engineering skills assume.
2. Run `/ask-matt` any time you're unsure which skill fits your situation.
