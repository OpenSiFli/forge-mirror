from unittest.mock import Mock

from config import RefsConfig
from mirror import Mirror


class DummyHub:
    src_repo_base = "https://src.example.com/org"
    dst_repo_base = "https://dst.example.com/org"
    dst_type = "dst"

    def create_dst_repo(self, repo_name: str) -> None:
        return None


def make_mirror() -> Mirror:
    return Mirror(
        DummyHub(),
        "source-repo",
        "target-repo",
        push_strategy="safe",
        dst_transport="https",
    )


def test_filter_refs_include_exclude_patterns() -> None:
    mirror = make_mirror()
    refs = ["main", "release/v1", "feature/x", "dependabot/npm"]

    filtered = mirror._filter_refs(
        patterns_include=["main", "release/*", "feature/*"],
        patterns_exclude=["feature/*", "dependabot/*"],
        ref_list=refs,
    )

    assert filtered == ["main", "release/v1"]


def test_filter_refs_include_all() -> None:
    mirror = make_mirror()
    refs = ["main", "dev"]

    filtered = mirror._filter_refs(
        patterns_include=["*"],
        patterns_exclude=[],
        ref_list=refs,
    )
    assert filtered == refs


def test_filter_refs_include_empty_matches_none() -> None:
    mirror = make_mirror()
    refs = ["main", "dev"]

    filtered = mirror._filter_refs(
        patterns_include=[],
        patterns_exclude=[],
        ref_list=refs,
    )
    assert filtered == []


def test_filter_refs_exclude_takes_precedence() -> None:
    mirror = make_mirror()
    refs = ["main", "release/v1"]

    filtered = mirror._filter_refs(
        patterns_include=["*"],
        patterns_exclude=["main"],
        ref_list=refs,
    )
    assert filtered == ["release/v1"]


def test_build_refspecs_from_refs_config() -> None:
    mirror = make_mirror()
    local_repo = Mock()
    local_repo.git.for_each_ref.return_value = "\n".join(
        [
            "refs/remotes/origin/HEAD",
            "refs/remotes/origin/main",
            "refs/remotes/origin/release/v1",
            "refs/remotes/origin/feature/x",
        ]
    )
    local_repo.git.tag.return_value = "\n".join(
        ["v1.0.0", "v1.0.0-rc1", "v2.0.0"]
    )

    refs_cfg = RefsConfig(
        branches_include=["main", "release/*"],
        branches_exclude=["feature/*"],
        tags_include=["v*"],
        tags_exclude=["v*-rc*"],
    )

    refspecs = mirror._build_refspecs(refs_cfg, local_repo)

    assert "refs/remotes/origin/main:refs/heads/main" in refspecs
    assert "refs/remotes/origin/release/v1:refs/heads/release/v1" in refspecs
    assert "refs/remotes/origin/feature/x:refs/heads/feature/x" not in refspecs
    assert "refs/tags/v1.0.0:refs/tags/v1.0.0" in refspecs
    assert "refs/tags/v1.0.0-rc1:refs/tags/v1.0.0-rc1" not in refspecs


def test_build_refspecs_main_branch_only() -> None:
    mirror = make_mirror()
    local_repo = Mock()
    local_repo.git.for_each_ref.return_value = "\n".join(
        [
            "refs/remotes/origin/main",
            "refs/remotes/origin/develop",
        ]
    )
    local_repo.git.tag.return_value = "\n".join(["v1.0.0", "v2.0.0"])

    refs_cfg = RefsConfig(
        branches_include=["main"],
        branches_exclude=[],
        tags_include=[],
        tags_exclude=[],
    )

    refspecs = mirror._build_refspecs(refs_cfg, local_repo)

    assert refspecs == ["refs/remotes/origin/main:refs/heads/main"]
