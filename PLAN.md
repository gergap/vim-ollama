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
   - [ ] Add `skill_manage` schemas, guarded mutations, supporting-file handling,
         scope permissions, and confirmation callbacks.
   - [ ] Add batched-operation validation and progress reporting.
   - [ ] Add focused unit tests for all mutation and safety behavior.
4. **Integration and polish**
   - [ ] Verify mode-specific tool exposure and disabled-mode behavior.
   - [ ] Complete Vim help, README, help tags, and examples.
   - [ ] Run the full repository checks and manually verify a temporary Git
         workspace with global and local data.

Each roadmap item should be usable and testable before starting the next item.

## Implementation Status

- [x] Memory and user context, including bounded storage, confirmation, prompt
      context, tests, and documentation.
- [x] Skill foundation, catalog discovery, and read-only `find_skill`.
- [x] Project-local example skill at `.skills/example/SKILL.md`.
- [ ] Skill management mutations and permissions.
- [ ] Final integration, manual verification, and full polish.

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

## Overall Acceptance Criteria

- The model can maintain project skills and global memory/user context without
  bypassing existing mode and filesystem restrictions.
- Documentation and automated tests cover both features.
