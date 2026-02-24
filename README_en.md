# Forge Mirror

English | [简体中文](./README.md)

Forge Mirror is an automation tool for mirroring repositories across GitHub, Gitee, GitLab, GitCode, and generic Git servers.

Open source: <https://github.com/OpenSiFli/forge-mirror>

## Project Lineage

This project is the fork-based successor of <https://github.com/Yikun/hub-mirror-action/>.

- We keep the core capabilities and usage model from the upstream project.
- We continue to evolve parameter design, structured YAML config, maintainability, and test coverage.
- For v2 behavior and parameter definitions, `action.yml` and source code in this repository are the source of truth.

## Quick Start

```yaml
steps:
  - name: Mirror GitHub org to Gitee org
    uses: OpenSiFli/forge-mirror@v2
    with:
      src_platform: github
      src_account: kunpengcompute
      dst_platform: gitee
      dst_account: kunpengcompute
      dst_key: ${{ secrets.GITEE_PRIVATE_KEY }}
      dst_token: ${{ secrets.GITEE_TOKEN }}
      src_account_type: org
      dst_account_type: org
```

## Input Overview (v2)

Required:
- `src_account`
- `dst_platform`
- `dst_account`
- `dst_token`

Common optional:
- `src_platform` (default `github`)
- `src_key` (required when `src_transport=ssh`)
- `dst_key` (required when `dst_transport=ssh`)
- `src_token` (for source-side API authentication, private repo visibility, and rate limits)
- `src_account_type` / `dst_account_type` (default `user`)
- `src_endpoint` / `dst_endpoint` (repository endpoints used for clone/push)
- `src_api_endpoint` / `dst_api_endpoint` (API endpoints; override platform API request address when set)
- `src_transport` (default `https`)
- `dst_transport` (default `ssh`)
- `src_ssh_user` (source SSH username, default `git`)
- `dst_ssh_user` (destination SSH username, default `git`)
- `repos` (YAML repository config, see details below)
- `push_strategy` (`safe` / `force` / `no`)
- `log_level` (`DEBUG` / `INFO` / `WARNING` / `ERROR`)
- `timeout` (for example `30m`)
- `api_timeout` (for example `60`, `2m`)
- `cache_path`
- `lfs`
- `dst_visibility` (`auto` / `public` / `private`)

See [`action.yml`](./action.yml) for the full schema.

### Self-hosted GitLab: Separate SSH and API Endpoints

If SSH and API addresses (or ports) are different, configure them separately:

```yaml
with:
  dst_platform: gitlab
  dst_account: sifli
  dst_transport: ssh
  dst_endpoint: gitlab.sifli.com:8218
  dst_api_endpoint: gitlab.sifli.com
  dst_key: ${{ secrets.GITLAB_SSH_KEY }}
  dst_token: ${{ secrets.GITLAB_TOKEN }}
```

Notes:
- `dst_endpoint` is used for git clone/push repository URLs
- `dst_api_endpoint` is only used for GitLab API calls (repo existence check, create repo, visibility update, etc.)
- The same pattern applies on source side with `src_endpoint` + `src_api_endpoint`

## `repos` Parameter Deep Dive

`repos` is a YAML string that replaces v1 parameters: `black_list`, `white_list`, `static_list`, and `mappings`.

### Full shape

```yaml
repos: |
  static:
    - repo1
    - name: repo2
      dst_name: repo2-renamed
      visibility: private
      push_strategy: force
      refs:
        branches:
          include: [main]
        tags:
          include: [v*]

  include:
    - repo1
    - repo2

  exclude:
    - archived-repo

  mappings:
    old-name: new-name

  refs:
    branches:
      include: [main, release/*]
      exclude: [feature/*]
    tags:
      include: [v*]
      exclude: [v*-rc*]
```

### Top-level fields

- `static`
  - Type: `list`
  - Purpose: explicit source repository list.
  - If non-empty: dynamic API listing is skipped.
  - If empty: repositories are listed dynamically from source account.

- `include`
  - Type: `list[str]`
  - Purpose: allowlist filter.
  - Empty means no allowlist filtering.

- `exclude`
  - Type: `list[str]`
  - Purpose: denylist filter.
  - Filter order is: `include` first, then `exclude`.

- `mappings`
  - Type: `dict[str, str]`
  - Purpose: global name mapping (`source_repo -> destination_repo`).

- `refs`
  - Type: refs filter config (detailed below).
  - Purpose: global branch/tag sync rules.

### Two `static` item formats

1. String shorthand (repo name only)

```yaml
static:
  - repo1
  - repo2
```

2. Object form (per-repo override)

```yaml
static:
  - name: repo2
    dst_name: repo2-renamed
    visibility: private
    push_strategy: force
    refs:
      branches:
        include: [main]
```

Per-repo object fields:
- `name`: source repo name
- `dst_name`: destination repo name
- `visibility`: per-repo visibility policy (`auto/public/private`)
- `push_strategy`: per-repo push policy (`safe/force/no`)
- `refs`: per-repo refs rules (fully overrides global `refs`)

### Merge priority (important)

Final config priority per repository:

1. `dst_name`: per-repo `dst_name` > global `mappings` > original name
2. `visibility`: per-repo `visibility` > global `dst_visibility` > `auto`
3. `push_strategy`: per-repo `push_strategy` > global `push_strategy` > `safe`
4. `refs`: per-repo `refs` fully overrides global `refs` (no deep merge)

### Typical patterns

1. Dynamic listing + include/exclude

```yaml
repos: |
  include: [repo-a, repo-b, repo-c]
  exclude: [repo-c]
```

2. Static list + rename

```yaml
repos: |
  static:
    - name: old-repo
      dst_name: new-repo
```

3. Force push only for specific repositories

```yaml
repos: |
  static:
    - name: release-repo
      push_strategy: force
```

## `refs` Parameter Deep Dive

`refs` controls which branches and tags are synchronized. It supports both global and per-repo scopes.

### Shape

```yaml
refs:
  branches:
    include: ["*"]
    exclude: []
  tags:
    include: ["*"]
    exclude: []
```

### Matching rules

- Wildcards follow `fnmatch` semantics:
  - `*`: any sequence of characters
  - `?`: any single character
- Evaluation order: `include` first, then `exclude`
- `exclude` wins over `include`

### Default behavior

- If `refs` is not set: sync all branches and all tags (same as v1 default)
- If `include` is not set: defaults to `[*]`
- If `include: []`: matches nothing
- If `exclude` is not set: defaults to empty list

### Global vs per-repo

- If a repository defines `refs` under `static`, that block fully overrides global `refs`.
- Override is block-level replacement, not field-level merge.

### Example: only sync `main`, no tags

```yaml
repos: |
  static:
    - name: repo-a
      refs:
        branches:
          include: [main]
        tags:
          include: []
```

### Example: only release branches and stable version tags

```yaml
repos: |
  refs:
    branches:
      include: [release/*]
      exclude: [release/tmp-*]
    tags:
      include: [v*]
      exclude: [v*-rc*]
```

## Bare Git Platform (`dst_platform: git`)

Use this for arbitrary Git servers (for example self-hosted Gitea/Gogs/plain SSH Git).

```yaml
with:
  src_platform: github
  src_account: my-org
  dst_platform: git
  dst_endpoint: git.example.com/my-org
  dst_transport: ssh
  dst_key: ${{ secrets.BARE_GIT_SSH_KEY }}
  dst_token: dummy-token
  repos: |
    static:
      - repo1
      - repo2
```

Notes:
- `platform=git` does not support API-based dynamic listing, so `repos.static` is required
- create/update visibility API calls are skipped
- when `dst_transport=https`, push URL supports embedded token auth

## GitLab CI Component

This repository provides `templates/hub-mirror.yml`.

```yaml
include:
  - component: $CI_SERVER_FQDN/your-group/forge-mirror/hub-mirror@2.0.0
    inputs:
      image: $CI_REGISTRY/your-group/forge-mirror:latest
      src-platform: github
      src-account: kunpengcompute
      dst-platform: gitee
      dst-account: kunpengcompute
      dst-key: $GITEE_PRIVATE_KEY
      dst-token: $GITEE_TOKEN
      src-account-type: org
      dst-account-type: org
```

## Migration Guide (v1 -> v2)

| v1 | v2 |
| --- | --- |
| `src: github/account` | `src_platform: github` + `src_account: account` |
| `dst: gitee/account` | `dst_platform: gitee` + `dst_account: account` |
| `private_key` | removed; use `src_key` / `dst_key` separately |
| `account_type` | `src_account_type` + `dst_account_type` |
| `clone_style` | `src_transport` + `dst_transport` |
| `debug: true` | `log_level: DEBUG` |
| `force_update: true` | `push_strategy: force` |
| `black_list` / `white_list` / `static_list` / `mappings` | merged into `repos` YAML |
| (none) | `src_token` |
| (none) | `repos.refs` |
| (none) | `dst_platform: git` |
| (none) | `src_api_endpoint` / `dst_api_endpoint` |
| unified `ssh_user` | `src_ssh_user` + `dst_ssh_user` |
