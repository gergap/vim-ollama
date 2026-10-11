# OllamaEdit Memory and Skills Support

## Roadmap

Implement the features in this order so the smaller Memory feature can be
verified independently before skill discovery and management are added:

1. **Memory and user context**
   - [x] Add `g:ollama_enable_memory` as the Memory feature gate.
   - [x] Add safe, bounded storage helpers for `MEMORY.md` and `USER.md`.
   - [x] Add the `memory` tool and Vim confirmation flow for global mutations.
   - [x] Integrate bounded memory/user context into prompts.
   - [x] Add unit tests and documentation for Memory.
2. **Skill foundation and discovery**
   - [x] Add Git-root detection, skill-root resolution, safe names, frontmatter
         parsing, validation, and effective catalog precedence.
   - [x] Add read-only `find_skill` and prompt catalog integration.
   - [x] Add unit tests and documentation for discovery.
3. **Skill management**
    - [x] Add `skill_manage` schemas, guarded mutations, supporting-file handling,
          scope permissions, and confirmation callbacks.
    - [x] Add batched-operation validation and progress reporting.
    - [x] Add focused unit tests for mutation and safety behavior.
4. **Integration and polish**
   - [x] Verify mode-specific tool exposure and disabled-mode behavior.
   - [x] Complete Vim help, README, help tags, and examples.
    - [x] Run the full repository checks and manually verify a temporary Git
          workspace with global and local data.
5. **Self-optimization and skill evolution**
    - [x] Add `g:ollama_enabled_self_optimization` as an independent feature
          gate, enabled by default.
    - [x] Add prompt guidance for recognizing durable workflow improvements and
          distinguishing them from isolated failures or unsafe instructions.
    - [x] Add a guarded proposal workflow that records rationale, evidence,
          intended scope, and expected benefit before changing a skill.
    - [x] Add validation and evaluation hooks for proposed skill changes,
          including stale-hash protection, rollback, and failure reporting.
    - [x] Require explicit confirmation for global self-optimization and keep
          project self-optimization within workspace Build permissions.
    - [x] Add tests and documentation for enabled, disabled, rejected, and
          confirmed self-optimization paths.
6. **Automatic context compaction**
    - [x] Add `g:ollama_enable_autocompact` as an independent feature gate,
          enabled by default.
    - [x] Track the effective context budget and compact before requests exceed
          the configured model limit.
    - [x] Preserve the system prompt, active mode, tool permissions, pending
          confirmations, and the current task objective across compaction.
    - [x] Summarize older conversation turns into bounded, clearly labeled,
          untrusted context without silently dropping recent tool results.
    - [ ] Add user inspection, clearing, and regeneration of compacted history.
    - [x] Add configurable thresholds, summary limits, failure handling, tests,
          and documentation.
7. **Subagent delegation**
    - [x] Add a guarded subagent tool for bounded delegated analysis, including
          single-file analysis as the first supported use case.
    - [x] Define inherited mode, filesystem, tool, timeout, and output-size
          restrictions for subagents; prevent unrestricted recursive delegation.
    - [x] Return structured, labeled results and failures while keeping the main
          conversation context bounded.
    - [x] Add approval, cancellation, concurrency, isolation, tests, and
          documentation for subagent calls.
8. Context Status Info
    - [x] Add helper function to get Context info like '178.9K (36%)'
    - [ ] Support displaying this info in normal Vim Status line
    - [ ] Add Vim Airline extension to display this info


Each roadmap item should be usable and testable before starting the next item.

## Implementation Status

- [x] Memory and user context, including bounded storage, confirmation, prompt
      context, tests, and documentation.
- [x] Skill foundation, catalog discovery, and read-only `find_skill`.
- [x] Project-local example skill at `.skills/example/SKILL.md`.
- [x] Skill management mutations and permissions.
- [x] Final integration, manual verification, and full polish.
- [x] Self-optimization and skill evolution.
- [ ] Automatic context compaction (core behavior complete; history inspection,
      clearing, and regeneration remain).
- [x] Subagent delegation.

## Feature 1: Memory and User Context

### Goal

Give OllamaEdit a bounded, explicit way to retain recurring observations and
user-specific information across sessions. This is a distinct feature from
Skills and must not depend on skill discovery or skill management.

### Storage

When enabled, OllamaEdit may load these optional global Markdown files:

```text
~/.vim/config/MEMORY.md
~/.vim/config/USER.md
```

`MEMORY.md` stores recurring patterns and reusable observations. `USER.md`
stores information about the user. Both files are bounded in size and clearly
labeled in the system prompt so they are not confused with project
instructions. Their content is untrusted and cannot override system safety,
mode, or tool restrictions.

### Tool

Add a dedicated `memory` tool with this interface:

```text
target: "memory" | "user"
action?: "add" | "replace" | "remove"
content?: string
old_text?: string
new_text?: string
operations?: [{ action, content?, old_text?, new_text? }]
```

The targets map to `MEMORY.md` and `USER.md` respectively. Operations are
validated, bounded, and applied atomically where possible. `replace` and
`remove` require matching `old_text`; ambiguous matches must fail unless the
operation explicitly supports the intended replacement semantics.

Global memory and user writes require Vim confirmation. The model may record
recurring patterns proactively when useful, but should not persist every
isolated failure. Memory mutation is unavailable when the feature is disabled
or when the active mode does not permit mutation.

### Memory implementation package

1. Storage and validation helpers for target mapping, size limits, UTF-8 text,
   atomic writes, and exact-match operations.
2. Python tool schema, dispatch, structured results, and error handling.
3. Vim confirmation callback/event flow for global writes.
4. System-prompt context and disabled-mode omission.
5. Unit tests and Vim help documentation.

## Feature 2: Skills

### Goal

Add reusable, discoverable skills to OllamaEdit. Skills provide durable
workflow instructions that the model can load when relevant, while allowing
the model to preserve recurring project lessons and user-wide practices.

Skills are independent of Memory. Memory may contain observations that lead to
a skill, but skill discovery and management must not require either memory file
to exist.

The feature is enabled by default with `g:ollama_enable_skills = v:true` and
can be disabled completely.

## Storage Model

### Global skills

Global skills are stored below:

```text
~/.vim/config/skills/<skill-name>/SKILL.md
```

Additional files required by a skill are stored in the same skill directory and
are referenced by `SKILL.md`. The existing file-reading tools can read those
files after the skill has been found.

### Project skills

Project skills are stored below the repository root:

```text
<git-root>/.skills/<skill-name>/SKILL.md
```

The Git root is the nearest ancestor of the current working directory that
contains a `.git` directory. Discovery does not continue above that root. If no
Git root exists, project-local skills are unavailable.

Project-local skills override global skills with the same skill name. Discovery
must return one effective skill per name, with project-local metadata taking
precedence.

### Skill file format

Every skill has a `SKILL.md` containing YAML frontmatter followed by Markdown
instructions. `name` and `description` are required. The optional `version`,
`tags`, and `author` fields are accepted and preserved but have no behavior in
this first implementation. Unknown frontmatter fields should also be
preserved when a complete skill is updated.

Example:

```markdown
---
name: cmake-workflow
description: Build and validate company CMake projects.
version: 1.0
tags: [cmake, build]
author: team
---

Use the referenced build instructions when working on a CMake project.
```

Skill names must be safe directory names and must not permit absolute paths,
`..` traversal, symbolic-link escapes, or writes outside the selected skill
root.

## Skill Tools

### `find_skill`

Add a read-only tool that searches the effective global and project skill
catalog. It should support an optional skill name or search query and return
matching metadata, source scope, skill directory, and a content hash. When a
specific skill is selected, return its complete `SKILL.md` content and the
relative names of its supporting files. Supporting file contents remain
available through the existing `read_file` tool.

The tool must reject unsafe names, ignore symlinks, skip malformed or oversized
skills with useful diagnostics, and never expose files outside the skill
directory.

### `skill_manage`

Implement the supplied batched management interface:

```text
operations: [
  { action: "create", name, content, category? },
  { action: "patch", name, old_string, new_string, file_path?, replace_all? },
  { action: "patch", name, content },
  { action: "write_file", name, file_path, file_content },
  { action: "remove_file", name, file_path },
  { action: "delete", name, absorbed_into? }
]
```

Extend the operation schema with:

- `scope: "project" | "global"`, selecting the destination root.
- `expected_hash` for full `SKILL.md` replacement and deletion.

`category` is optional frontmatter metadata only; it must not create another
directory level. The prompt should guide scope selection: explicit general
user practices use global scope, project-specific skills use project scope, and
skills created from discovered project problems default to project scope.

Operation behavior:

- `create` creates a new skill directory and validates complete `SKILL.md`
  frontmatter before writing it.
- String `patch` requires `old_string` to match and supports `replace_all`.
- Full-content `patch` compares `expected_hash` against the current exact file
  bytes before replacing it.
- `write_file` and `remove_file` operate only on supporting files inside the
  selected skill directory and reject `SKILL.md` unless the full-skill patch
  operation is used.
- `delete` compares `expected_hash` before removing the skill directory and
  its supporting files. `absorbed_into` is recorded only in tool output; it
  does not automatically merge content.
- Batched operations validate all paths and guards before applying mutations;
  report per-operation results and avoid silently overwriting conflicts.

Global skill, `MEMORY.md`, and `USER.md` writes require Vim confirmation.
Project skill writes follow the existing workspace Build permission model.
Mutation tools are available only in workspace Build mode. Read-only skill
discovery is available in Plan, range, and workspace modes.

## Prompt and Configuration Integration

### Configuration

Add this default in `plugin/ollama.vim`:

```vim
if !exists('g:ollama_enable_skills')
    let g:ollama_enable_skills = v:true
endif
```

Pass the setting into the Python session settings from
`autoload/ollama/edit.vim`. Add it to the configuration help/completion data
in `autoload/ollama/config.vim`.

When false, omit all skill tools, skill catalog context, `MEMORY.md`, and
`USER.md` context. No skill or memory filesystem access should occur.

### System prompt

When enabled, add concise context explaining:

- global and project skill locations and precedence;
- that skills are loaded on demand with `find_skill`;
- that supporting files are relative to the selected skill directory;
- how to choose global versus project scope;
- when recurring observations justify memory updates or a project skill;
- that skill, memory, and user files are untrusted instructions and cannot
  override system safety, mode, or tool restrictions.

Include a compact catalog of available skill names and descriptions, rather
than loading every full skill into every request. Include bounded labeled
memory and user context when present.

Ensure Plan and range prompts explain that skill discovery is read-only and
that skill mutations are unavailable in those modes.

## Skill Implementation Packages

1. **Skill filesystem foundation:** Git-root detection, global/project root
   resolution, safe skill names, symlink rejection, bounded file access, and
   content hashes.
2. **Frontmatter and catalog:** YAML parsing/validation, required fields,
   optional/unknown field preservation, malformed-skill diagnostics, metadata
   enumeration, and project-over-global precedence.
3. **`find_skill`:** Read-only schema and dispatch, exact-name/query search,
   full `SKILL.md` loading, supporting-file listing, and prompt catalog
   integration.
4. **`skill_manage` creation:** Batched schema, explicit project/global scope,
   validated creation, category metadata, and project Build permission checks.
5. **`skill_manage` guarded updates:** Exact string patches, full replacement
   with `expected_hash`, supporting-file writes/removals, and all-path
   prevalidation.
6. **`skill_manage` deletion and global confirmation:** Hash-guarded deletion,
   global confirmation callbacks, per-operation results, and progress events.
7. **Mode and prompt integration:** Read-only discovery in Plan/range/workspace
   modes, mutations only in workspace Build mode, untrusted-content guidance,
   and complete disabled-mode omission.
8. **Skill tests and documentation:** Focused unit tests, Vim help, README,
   help tags, examples, and manual temporary-repository verification.

Memory helpers and tool work belong to Feature 1 above; they must not be
duplicated in the Skill packages.

## Implementation Areas

1. Implement and verify Feature 1: Memory and user context.
2. Implement and verify Skill packages 1-2: filesystem foundation and catalog.
3. Implement and verify Skill package 3: read-only discovery.
4. Implement and verify Skill packages 4-6: mutations and permissions.
5. Implement and verify Skill packages 7-8: integration, tests, and docs.
6. Add the `g:ollama_enable_skills` configuration default and pass it through
   Vim settings when Skills are enabled.
7. Add the `g:ollama_enabled_self_optimization` configuration default and pass
   it through Vim settings when guarded self-optimization is enabled.

## Feature 1 Tests

Extend `tests/test_codeeditor_tools.py` and add focused tests where useful for:

- memory/user target mapping;
- add, replace, and remove operations;
- exact-match, ambiguous-match, size, UTF-8, and atomic-write guards;
- global confirmation requests and mutation denial in unsupported modes;
- bounded prompt inclusion of labeled memory and user context;
- complete omission of memory behavior and filesystem access when disabled.

## Feature 2 Tests

Add focused tests for:

- YAML frontmatter validation and required fields;
- optional and unknown frontmatter preservation;
- Git-root discovery and no-root behavior;
- global/project discovery and project-over-global precedence;
- malformed, oversized, symlinked, traversal, and unsafe-name rejection;
- `find_skill` metadata, full content, supporting-file listing, and hashes;
- skill creation and category handling;
- guarded string patches, full replacements, and stale-hash failures;
- guarded deletion and supporting-file write/remove safety;
- batched operation validation and partial-result reporting;
- mode-specific skill tool availability;
- prompt inclusion of skill catalogs;
- complete omission of skill behavior when disabled;
- existing workspace/range behavior remaining unchanged.

Run the repository checks after implementation:

```text
pytest -q tests/test_codeeditor_tools.py
python3 -m compileall -q python
```

Also manually verify the Vim help documentation, confirmation flow, and a
workspace session in a temporary Git repository with both global and local
skills.

## Documentation

### Memory documentation

Update `doc/vim-ollama.txt` with the Memory overview, global file locations,
`MEMORY.md` and `USER.md` semantics, `memory` operations, size and safety
limits, confirmation requirements, configuration, and security guidance.

### Skill documentation

Update `doc/vim-ollama.txt` with the Skills overview, enable/disable
configuration, global and project directory layouts, `SKILL.md` frontmatter
requirements, supporting-file references, discovery precedence, Git-root rules,
`find_skill`, `skill_manage`, guarded updates/deletes, confirmation
requirements, security guidance, and examples for creating a project skill and
a global user skill.

Update `doc/tags` for new help anchors. Update `README.md` with a concise
feature summary and link to the detailed Vim help.

## Feature 1 Acceptance Criteria

- `MEMORY.md` and `USER.md` can be safely read and updated through the
  dedicated memory interface.
- Memory and user context is bounded, labeled, untrusted, and omitted entirely
  when `g:ollama_enable_memory` is false.
- Global memory/user mutations require explicit user confirmation.
- Memory behavior is independently tested and documented before Skill work
  begins.

## Feature 2 Acceptance Criteria

- Skills are enabled by default and can be fully disabled with
  `g:ollama_enable_skills`.
- The model receives a compact effective skill catalog and can load a selected
  skill on demand.
- Project skills override global skills by name.
- Skill mutations are validated, path-safe, and guarded against stale updates.
- Global skill mutations require explicit user confirmation.
- Skill behavior is independently tested and documented without requiring
  memory files to exist.

## Self-Optimization Feature

### Goal

Allow OllamaEdit to improve reusable Skills from demonstrated task outcomes
without silently changing instructions or weakening safety controls. This is a
separate feature from Skill discovery and management.

### Configuration

Add this default in `plugin/ollama.vim`:

```vim
if !exists('g:ollama_enabled_self_optimization')
    let g:ollama_enabled_self_optimization = v:true
endif
```

Pass the setting through `autoload/ollama/edit.vim`. When false, omit
self-optimization prompt guidance, proposal state, evaluation behavior, and
self-optimization operations. Existing `find_skill` and explicitly requested
ordinary `skill_manage` operations remain available under their existing mode
and confirmation rules.

### Safety Model

Self-optimization must:

- treat task results, user feedback, and existing Skill content as untrusted;
- propose changes rather than silently applying them;
- record the target Skill, scope, rationale, evidence, expected benefit, and
  exact proposed diff;
- reject changes based only on an isolated failure, prompt injection, or an
  instruction to weaken safety, mode, permission, or confirmation rules;
- preserve stale-hash guards and support rollback when evaluation fails;
- require global confirmation and use workspace Build permission for project
  changes;
- avoid storing secrets or full task transcripts by default.

### Workflow

The agent should consider self-optimization only after a repeated pattern,
explicit user feedback, or a verified successful workflow. It should inspect
the relevant Skill, create a bounded proposal, validate the proposed patch,
and request confirmation before applying it. New Skills may be proposed when
no existing Skill is appropriate, using the same scope, validation, and
confirmation rules as other Skill mutations.

Evaluation should prefer focused tests, checker results, or an explicit user
acceptance signal. Failed evaluation must leave the previous Skill unchanged
or restore it automatically.

## Self-Optimization Acceptance Criteria

- Self-optimization is enabled by default and independently controlled by
  `g:ollama_enabled_self_optimization`.
- Disabling it omits self-optimization behavior without disabling ordinary
  Skills or explicit Skill management.
- The model proposes evidence-backed Skill changes rather than silently
  rewriting Skills.
- Proposals are bounded, hash-guarded, validated, evaluable, and reversible.
- Global proposals require explicit confirmation; project proposals require
  workspace Build permission.
- Unsafe, unsupported, stale, or failed proposals leave the prior Skill intact.

## Feature 6: Automatic Context Compaction

### Goal

Keep long-running OllamaEdit sessions usable when the conversation approaches
the model context limit. Compaction must reduce historical context without
changing the active task, safety rules, mode, permissions, or user-approved
state.

### Configuration

Add this default in `plugin/ollama.vim`:

```vim
if !exists('g:ollama_enable_autocompact')
    let g:ollama_enable_autocompact = v:true
endif
```

Pass the setting through `autoload/ollama/edit.vim`. Add configuration values
for the compaction trigger threshold and maximum summary size, with safe
defaults and validation. When disabled, no automatic summarization or
compaction state should be created and existing request behavior must remain
unchanged.

### Behavior

- Estimate request tokens using the provider/model context limit and reserve
  space for the next response, tool calls, and protocol overhead.
- Trigger compaction before the request would exceed the effective limit, with
  a configurable safety margin rather than waiting for a provider error.
- Keep the system prompt, current mode, tool restrictions, active objective,
  recent user messages, recent tool calls/results, and unresolved confirmations
  verbatim or in an equivalent structured form.
- Summarize only older turns, label the result as an untrusted generated
  summary, and bound its size. Do not treat summary content as system or user
  instructions.
- Prefer deterministic trimming when summarization fails. Report compaction
  failures clearly and never send an over-limit request merely because the
  summary provider failed.
- Allow the user to inspect, clear, and regenerate the compacted history.
  Compaction must not write Memory, USER.md, Skills, or project files.
- Avoid repeated compaction loops and preserve enough metadata to diagnose how
  the request was reduced.

### Implementation Package

1. Context-budget calculation for supported providers and model limits.
2. Conversation partitioning into protected recent state and compactable history.
3. Bounded summary generation, validation, fallback trimming, and state
   serialization.
4. Vim/Python configuration and optional user-visible compaction events.
5. Unit tests, integration tests with mocked providers, and documentation.

## Feature 7: Subagent Delegation

### Goal

Allow OllamaEdit to delegate focused, independent work to a bounded subagent
so the main context remains smaller. The initial use case is analyzing one
file and returning findings or a concise summary to the parent session.

### Tool Interface

Add a `subagent` tool with a deliberately small interface:

```text
task: string
files?: [string]
mode?: "analyze"
max_output_chars?: integer
timeout_seconds?: integer
```

The first implementation should support read-only analysis of explicitly
selected files. File paths must use the existing workspace safety checks,
reject traversal and symlink escapes, and be resolved relative to the active
workspace. Future write-capable modes require a separate design and must not
be implied by this interface.

### Safety and Execution Model

- Subagents inherit the parent mode and cannot obtain broader filesystem,
  network, tool, confirmation, or provider permissions.
- Analyze-mode subagents are read-only and cannot mutate buffers, Memory,
  Skills, project files, or configuration.
- Bound task length, input file size, context size, output size, runtime, and
  concurrent subagent count. Reject invalid limits before starting work.
- Do not allow unrestricted recursive subagent creation. Either disallow
  delegation by child agents or enforce a fixed depth of one.
- Preserve the parent conversation by returning a structured result containing
  status, findings, diagnostics, and bounded output. Do not inject raw child
  prompts or untrusted file content as system instructions.
- Support cancellation and timeout handling. A failed child must produce a
  bounded error result and must not fail or mutate the parent session.
- Make approval behavior explicit: read-only analysis may be available in
  Plan, range, and workspace modes, while any future mutation-capable mode
  requires the existing Build permissions and confirmation flow.
- Keep provider credentials and full child transcripts out of normal results
  unless explicitly requested for debugging.

### Implementation Package

1. Subagent schema, dispatch, lifecycle, timeout, cancellation, and structured
   result handling.
2. Safe file selection and inherited mode/permission enforcement.
3. Context and output budgets, concurrency limits, and recursion prevention.
4. Parent prompt guidance for when delegation is useful, especially for
   independent single-file analysis.
5. Unit tests, mocked-provider integration tests, and documentation.

## Feature 6 and 7 Tests

Add focused tests for:

- autocompaction disabled behavior and configuration validation;
- context-budget calculation, trigger thresholds, and reserved response space;
- preservation of system/mode/tool/confirmation state across compaction;
- bounded summaries, untrusted labeling, repeated-compaction prevention, and
  deterministic fallback trimming;
- provider summary failures, over-limit prevention, inspection, clearing, and
  regeneration of compacted history;
- subagent schema validation, explicit file selection, path and symlink safety;
- inherited mode and permission restrictions, read-only enforcement, and
  blocked mutations;
- bounded child input/output, timeout, cancellation, concurrency, and depth;
- structured child failures and parent-context preservation;
- disabled subagent behavior and mode-specific tool exposure;
- provider calls being mocked so tests do not require Ollama or API credentials.

Run the repository checks after implementation:

```text
pytest -q tests/test_codeeditor_tools.py
python3 -m compileall -q python
```

Add focused documentation in `doc/vim-ollama.txt`, update `doc/tags`, and add
a concise README feature summary. Manually verify a long session that crosses
the compaction threshold and a workspace session delegating analysis of a
temporary single file.

## Feature 6 Acceptance Criteria

- Context is compacted before provider limits are exceeded when the feature is
  enabled.
- Protected task, mode, safety, permission, tool, and confirmation state is
  preserved across compaction.
- Summaries and fallback trimming are bounded, labeled, inspectable, and never
  silently treated as higher-trust instructions.
- Disabled, failed, or repeated compaction paths do not corrupt the session or
  send an over-limit request.

## Feature 7 Acceptance Criteria

- The model can delegate bounded read-only analysis of explicitly selected
  files and receive concise structured results.
- Subagents cannot bypass parent mode, permissions, path safety, limits, or
  confirmation requirements.
- Timeouts, cancellation, provider failures, and invalid requests leave the
  parent session usable and unchanged.
- Subagent behavior is independently testable without external services.

## Overall Acceptance Criteria

- The model can maintain project skills and global memory/user context without
  bypassing existing mode and filesystem restrictions.
- Documentation and automated tests cover both features.
- Long sessions remain usable through bounded automatic context compaction.
- Focused analysis can be delegated without expanding permissions or causing
  unbounded context, recursion, or resource usage.
