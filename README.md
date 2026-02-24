# Hub Mirror Action

简体中文 | [English](./README_en.md)

在 GitHub、Gitee、GitLab、GitCode（以及裸 Git 服务）之间同步仓库的 Action。

## 快速开始

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

## 参数概览（v2）

必填：
- `src_account`
- `dst_platform`
- `dst_account`
- `dst_token`

常用可选：
- `src_platform`（默认 `github`）
- `src_key`（`src_transport=ssh` 时必填）
- `dst_key`（`dst_transport=ssh` 时必填）
- `src_token`（用于源端 API 认证）
- `src_account_type` / `dst_account_type`（默认 `user`）
- `src_endpoint` / `dst_endpoint`（自托管地址）
- `src_transport`（默认 `https`）
- `dst_transport`（默认 `ssh`）
- `ssh_user`（默认 `git`）
- `repos`（YAML 仓库配置）
- `push_strategy`（`safe`/`force`/`no`）
- `log_level`（`DEBUG`/`INFO`/`WARNING`/`ERROR`）
- `timeout`（如 `30m`）
- `api_timeout`（如 `60`、`2m`）
- `cache_path`
- `lfs`
- `dst_visibility`（`auto`/`public`/`private`）

完整定义以 [`action.yml`](./action.yml) 为准。

## `repos` YAML 配置

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

优先级：
1. `dst_name`: per-repo > `mappings` > 同名
2. `visibility`: per-repo > `dst_visibility` > `auto`
3. `push_strategy`: per-repo > 全局 `push_strategy` > `safe`
4. `refs`: per-repo 完整覆盖全局 `refs`

## Refs 过滤示例

只同步 `main` 分支，不同步任何 tag：

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

## 裸 Git 平台示例

同步到任意 Git 服务器（不依赖平台 API）：

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

说明：
- `platform=git` 时不支持动态仓库列表，必须使用 `repos.static`
- 不执行 create/update visibility API

## GitLab CI Component

仓库提供 `templates/hub-mirror.yml` 组件模板。

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

## v1 -> v2 迁移指南

| v1 | v2 |
| --- | --- |
| `src: github/account` | `src_platform: github` + `src_account: account` |
| `dst: gitee/account` | `dst_platform: gitee` + `dst_account: account` |
| `private_key` | 删除；分别使用 `src_key` / `dst_key` |
| `account_type` | `src_account_type` + `dst_account_type` |
| `clone_style` | `src_transport` + `dst_transport` |
| `debug: true` | `log_level: DEBUG` |
| `force_update: true` | `push_strategy: force` |
| `black_list` / `white_list` / `static_list` / `mappings` | 合并为 `repos` YAML |
| （无） | `src_token` |
| （无） | `repos.refs` |
| （无） | `dst_platform: git` |

