# Forge Mirror

简体中文 | [English](./README_en.md)

Forge Mirror 是一个用于在 GitHub、Gitee、GitLab、GitCode 以及通用 Git 服务之间同步仓库的自动化工具。

开源地址：<https://github.com/OpenSiFli/forge-mirror>

## 项目关系说明

本项目是 <https://github.com/Yikun/hub-mirror-action/> 的 fork 后继产品。

- 我们继承了上游项目的核心能力与使用习惯。
- 在此基础上，持续推进参数体系重构、配置结构化（YAML）、可维护性和测试覆盖。
- 文档中提到的 v2 参数与行为，以本仓库的 `action.yml` 和源码实现为准。

## 快速开始

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

## 输入参数概览（v2）

必填：
- `src_account`
- `dst_platform`
- `dst_account`
- `dst_token`

常用可选：
- `src_platform`（默认 `github`）
- `src_key`（`src_transport=ssh` 时必填）
- `dst_key`（`dst_transport=ssh` 时必填）
- `src_token`（用于源端 API 认证，提升私有仓库可见性与 API 限额）
- `src_account_type` / `dst_account_type`（默认 `user`）
- `src_endpoint` / `dst_endpoint`（代码仓库地址，SSH/HTTPS clone 与 push 使用）
- `src_api_endpoint` / `dst_api_endpoint`（API 地址；配置后将覆盖对应平台 API 请求地址）
- `src_transport`（默认 `https`）
- `dst_transport`（默认 `ssh`）
- `src_ssh_user`（源端 SSH 用户名，默认 `git`）
- `dst_ssh_user`（目标端 SSH 用户名，默认 `git`）
- `repos`（YAML 仓库配置，详见下文）
- `push_strategy`（`safe` / `force` / `no`）
- `log_level`（`DEBUG` / `INFO` / `WARNING` / `ERROR`）
- `timeout`（如 `30m`）
- `api_timeout`（如 `60`、`2m`）
- `cache_path`
- `lfs`
- `dst_visibility`（`auto` / `public` / `private`）

完整定义请参考 [`action.yml`](./action.yml)。

### 自建 GitLab 场景：SSH 与 API 地址分离

当 SSH 和 API 地址（或端口）不同，可分开配置：

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

说明：
- `dst_endpoint` 用于 git clone/push（SSH/HTTPS 仓库 URL）
- `dst_api_endpoint` 仅用于 GitLab API（仓库存在性检查、创建仓库、可见性更新等）
- 源端同理可使用 `src_endpoint` + `src_api_endpoint`

## `repos` 参数详解（重点）

`repos` 是一个 YAML 字符串，用于统一替代 v1 的 `black_list` / `white_list` / `static_list` / `mappings`。

### 结构总览

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

### 顶层字段语义

- `static`
  - 类型：`list`
  - 作用：显式指定要同步的仓库列表。
  - 若 `static` 非空：不再调用源端 API 动态拉取仓库列表。
  - 若 `static` 为空：会动态获取源账号下仓库列表。

- `include`
  - 类型：`list[str]`
  - 作用：白名单过滤，仅保留列表内仓库。
  - 为空时表示不过滤。

- `exclude`
  - 类型：`list[str]`
  - 作用：黑名单过滤，从候选仓库中剔除。
  - 过滤顺序：先 `include` 再 `exclude`。

- `mappings`
  - 类型：`dict[str, str]`
  - 作用：全局仓库名映射，`源仓库名 -> 目标仓库名`。

- `refs`
  - 类型：refs 过滤配置（详见下一节）
  - 作用：全局分支/标签同步规则。

### `static` 的两种写法

1. 简写字符串（仅仓库名）

```yaml
static:
  - repo1
  - repo2
```

2. 对象写法（单仓库覆写）

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

对象字段说明：
- `name`：源仓库名
- `dst_name`：目标仓库名（可重命名）
- `visibility`：该仓库目标可见性策略（`auto/public/private`）
- `push_strategy`：该仓库推送策略（`safe/force/no`）
- `refs`：该仓库的 refs 同步规则（完整覆盖全局 `refs`）

### 合并优先级（非常重要）

对单个仓库最终配置，优先级如下：

1. `dst_name`：`static` 单仓库 `dst_name` > 全局 `mappings` > 同名
2. `visibility`：`static` 单仓库 `visibility` > 全局 `dst_visibility` > `auto`
3. `push_strategy`：`static` 单仓库 `push_strategy` > 全局 `push_strategy` > `safe`
4. `refs`：`static` 单仓库 `refs` 完整覆盖全局 `refs`（非 merge）

### 常见使用模式

1. 动态拉取 + include/exclude

```yaml
repos: |
  include: [repo-a, repo-b, repo-c]
  exclude: [repo-c]
```

2. 静态列表 + 重命名

```yaml
repos: |
  static:
    - name: old-repo
      dst_name: new-repo
```

3. 仓库级别强制推送

```yaml
repos: |
  static:
    - name: release-repo
      push_strategy: force
```

## `refs` 参数详解（重点）

`refs` 控制“同步哪些分支和标签（tag）”。支持全局配置和 per-repo 配置。

### 结构

```yaml
refs:
  branches:
    include: ["*"]
    exclude: []
  tags:
    include: ["*"]
    exclude: []
```

### 匹配规则

- 通配符语义使用 `fnmatch`：
  - `*`：任意字符
  - `?`：单个字符
- 执行顺序：先 `include`，再 `exclude`
- `exclude` 优先级高于 `include`

### 默认行为

- `refs` 未配置：同步所有分支与所有 tag（与 v1 行为一致）
- `include` 未配置：默认 `[*]`（全包含）
- `include: []`：不包含任何项
- `exclude` 未配置：默认空列表

### per-repo 与全局关系

- 当某个仓库在 `static` 中配置了 `refs`，它会完整覆盖全局 `refs`。
- 覆盖是“整块替换”，不是字段级合并。

### 示例：仅同步 main 分支，不同步 tag

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

### 示例：仅同步 release 分支和正式版本 tag

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

## 裸 Git 平台（`dst_platform: git`）

用于接入任意 Git 服务器（例如自建 Gitea/Gogs/裸 SSH 服务器）。

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
- `platform=git` 不支持 API 仓库枚举，必须提供 `repos.static`
- 不执行 create_repo / update_visibility API
- `dst_transport=https` 时，push URL 支持 token 内嵌认证

## GitLab CI Component

仓库提供 `templates/hub-mirror.yml` 组件模板。

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
| （无） | `src_api_endpoint` / `dst_api_endpoint` |
| `ssh_user`（统一） | `src_ssh_user` + `dst_ssh_user` |
