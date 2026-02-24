# Hub Mirror Action

English | [简体中文](./README.md)

Mirror repositories between GitHub, Gitee, GitLab, GitCode, and generic Git servers.

## Quick Start

```yaml
steps:
  - name: Mirror GitHub org to Gitee org
    uses: Yikun/hub-mirror-action@master
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

## Inputs (v2)

Required:
- `src_account`
- `dst_platform`
- `dst_account`
- `dst_token`

Common optional:
- `src_platform` (default `github`)
- `src_key` (required when `src_transport=ssh`)
- `dst_key` (required when `dst_transport=ssh`)
- `src_token` (source API authentication)
- `src_account_type` / `dst_account_type` (default `user`)
- `src_endpoint` / `dst_endpoint` (self-hosted endpoint)
- `src_transport` (default `https`)
- `dst_transport` (default `ssh`)
- `ssh_user` (default `git`)
- `repos` (YAML repo config)
- `push_strategy` (`safe`/`force`/`no`)
- `log_level` (`DEBUG`/`INFO`/`WARNING`/`ERROR`)
- `timeout` (for example `30m`)
- `api_timeout` (for example `60`, `2m`)
- `cache_path`
- `lfs`
- `dst_visibility` (`auto`/`public`/`private`)

See [`action.yml`](./action.yml) for the complete source of truth.

## `repos` YAML Config

```yaml
with:
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

Priority:
1. `dst_name`: per-repo > `mappings` > same name
2. `visibility`: per-repo > `dst_visibility` > `auto`
3. `push_strategy`: per-repo > global `push_strategy` > `safe`
4. `refs`: per-repo fully overrides global `refs`

## Refs Filtering Example

Only sync `main` and no tags:

```yaml
with:
  repos: |
    static:
      - name: repo-a
        refs:
          branches:
            include: [main]
          tags:
            include: []
```

## Bare Git Platform Example

Mirror to any Git server without platform API support:

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
- `platform=git` does not support dynamic repo listing, so `repos.static` is required
- create/update visibility API operations are skipped

## GitLab CI Component

This repository includes `templates/hub-mirror.yml`.

```yaml
include:
  - component: $CI_SERVER_FQDN/your-group/hub-mirror-action/hub-mirror@2.0.0
    inputs:
      image: $CI_REGISTRY/your-group/hub-mirror-action:latest
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
| `private_key` | removed; use `src_key` / `dst_key` |
| `account_type` | `src_account_type` + `dst_account_type` |
| `clone_style` | `src_transport` + `dst_transport` |
| `debug: true` | `log_level: DEBUG` |
| `force_update: true` | `push_strategy: force` |
| `black_list` / `white_list` / `static_list` / `mappings` | merged into `repos` YAML |
| (none) | `src_token` |
| (none) | `repos.refs` |
| (none) | `dst_platform: git` |

