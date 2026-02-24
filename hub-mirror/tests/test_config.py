from dataclasses import asdict

import pytest

from config import RefsConfig, parse_repos_config, resolve_repo_config
from platforms import RepoVisibility


class DummyGlobalConfig:
    def __init__(
        self,
        push_strategy: str = "safe",
        dst_visibility: str = "auto",
    ) -> None:
        self.push_strategy = push_strategy
        self.dst_visibility = RepoVisibility.from_str(dst_visibility)


def test_parse_repos_config_empty_input() -> None:
    cfg_none = parse_repos_config(None)
    cfg_empty = parse_repos_config("")

    assert cfg_none.static == []
    assert cfg_empty.static == []
    assert cfg_none.include == []
    assert cfg_none.exclude == []
    assert cfg_none.mappings == {}


def test_parse_static_string_list() -> None:
    cfg = parse_repos_config(
        """
static:
  - repo1
  - repo2
"""
    )
    assert [repo.name for repo in cfg.static] == ["repo1", "repo2"]
    assert [repo.dst_name for repo in cfg.static] == ["repo1", "repo2"]


def test_parse_static_dict_with_repo_overrides() -> None:
    cfg = parse_repos_config(
        """
static:
  - name: repo1
    dst_name: repo1-renamed
    visibility: private
    push_strategy: force
    refs:
      branches:
        include: [main]
      tags:
        include: [v*]
"""
    )

    repo = cfg.static[0]
    assert repo.name == "repo1"
    assert repo.dst_name == "repo1-renamed"
    assert repo.visibility == RepoVisibility.PRIVATE
    assert repo.push_strategy == "force"
    assert repo.refs.branches_include == ["main"]
    assert repo.refs.tags_include == ["v*"]


def test_parse_static_mixed_list() -> None:
    cfg = parse_repos_config(
        """
static:
  - repo1
  - name: repo2
    visibility: public
"""
    )
    assert [repo.name for repo in cfg.static] == ["repo1", "repo2"]
    assert cfg.static[1].visibility == RepoVisibility.PUBLIC


def test_parse_include_exclude_and_mappings() -> None:
    cfg = parse_repos_config(
        """
include:
  - repo1
  - repo2
exclude:
  - repo2
mappings:
  repo1: repo1-dst
"""
    )
    assert cfg.include == ["repo1", "repo2"]
    assert cfg.exclude == ["repo2"]
    assert cfg.mappings == {"repo1": "repo1-dst"}


def test_parse_global_refs() -> None:
    cfg = parse_repos_config(
        """
refs:
  branches:
    include: [main, release/*]
    exclude: [feature/*]
  tags:
    include: [v*]
    exclude: [v*-rc*]
"""
    )

    refs = cfg.refs
    assert refs.branches_include == ["main", "release/*"]
    assert refs.branches_exclude == ["feature/*"]
    assert refs.tags_include == ["v*"]
    assert refs.tags_exclude == ["v*-rc*"]


def test_resolve_repo_config_per_repo_refs_override_global_refs() -> None:
    cfg = parse_repos_config(
        """
refs:
  branches:
    include: [main]
static:
  - name: repo1
    refs:
      branches:
        include: [develop]
      tags:
        include: ["*"]
"""
    )
    resolved = resolve_repo_config("repo1", cfg, DummyGlobalConfig())
    assert resolved.refs.branches_include == ["develop"]
    assert resolved.refs.tags_include == ["*"]


def test_resolve_repo_config_priority_merge() -> None:
    cfg = parse_repos_config(
        """
mappings:
  repo1: mapped-repo1
static:
  - name: repo1
    dst_name: override-repo1
    visibility: private
    push_strategy: force
"""
    )

    resolved = resolve_repo_config(
        "repo1",
        cfg,
        DummyGlobalConfig(push_strategy="safe", dst_visibility="public"),
    )

    assert resolved.dst_name == "override-repo1"
    assert resolved.visibility == RepoVisibility.PRIVATE
    assert resolved.push_strategy == "force"


def test_resolve_repo_config_fallback_to_global_defaults() -> None:
    cfg = parse_repos_config(
        """
mappings:
  repo1: mapped-repo1
"""
    )
    resolved = resolve_repo_config(
        "repo1",
        cfg,
        DummyGlobalConfig(push_strategy="force", dst_visibility="public"),
    )

    assert resolved.dst_name == "mapped-repo1"
    assert resolved.visibility == RepoVisibility.PUBLIC
    assert resolved.push_strategy == "force"


def test_dataclasses_can_serialize() -> None:
    cfg = parse_repos_config(
        """
static:
  - repo1
"""
    )
    as_dict = asdict(cfg)
    assert as_dict["static"][0]["name"] == "repo1"


@pytest.mark.parametrize(
    "raw",
    [
        "- repo1",
        "static: foo",
        "include: foo",
        "mappings: [a, b]",
        "static:\n  - name: ''",
        "static:\n  - 123",
    ],
)
def test_parse_repos_config_invalid_input(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_repos_config(raw)


def test_resolve_repo_config_refs_default() -> None:
    cfg = parse_repos_config(None)
    resolved = resolve_repo_config("repo1", cfg, DummyGlobalConfig())
    assert resolved.refs == RefsConfig()
