from typing import List, Tuple

import hubmirror
from hubmirror import HubMirror, MirrorConfig
from platforms import RepoVisibility


class FakeHub:
    init_calls: List[dict] = []
    dynamic_called = False
    visibility_calls: List[Tuple[str, RepoVisibility]] = []

    def __init__(self, **kwargs) -> None:
        FakeHub.init_calls.append(kwargs)

    def dynamic_list(self) -> List[str]:
        FakeHub.dynamic_called = True
        return ["repo-from-api"]

    def update_dst_repo_visibility(
        self,
        repo_name: str,
        visibility: RepoVisibility,
    ) -> bool:
        FakeHub.visibility_calls.append((repo_name, visibility))
        return True


class FakeMirror:
    created: List[dict] = []

    def __init__(
        self,
        hub,
        src_name: str,
        dst_name: str,
        cache: str,
        timeout: str,
        push_strategy: str,
        dst_transport: str,
        refs,
        lfs: bool,
    ) -> None:
        FakeMirror.created.append(
            {
                "src_name": src_name,
                "dst_name": dst_name,
                "cache": cache,
                "timeout": timeout,
                "push_strategy": push_strategy,
                "dst_transport": dst_transport,
                "refs": refs,
                "lfs": lfs,
            }
        )

    def download(self) -> None:
        return None

    def create(self) -> None:
        return None

    def push(self) -> None:
        return None


def test_hubmirror_run_with_yaml_repos_config(monkeypatch) -> None:
    FakeHub.init_calls = []
    FakeHub.dynamic_called = False
    FakeHub.visibility_calls = []
    FakeMirror.created = []

    monkeypatch.setattr(hubmirror, "Hub", FakeHub)
    monkeypatch.setattr(hubmirror, "Mirror", FakeMirror)

    config = MirrorConfig(
        src_platform="github",
        src_account="src-org",
        dst_platform="gitee",
        dst_account="dst-org",
        dst_token="dst-token",
        repos="""
static:
  - repo1
  - name: repo2
    dst_name: repo-two
    visibility: private
    push_strategy: force
    refs:
      branches:
        include: [main]
include:
  - repo1
  - repo2
exclude:
  - repo1
mappings:
  repo1: mapped-repo1
""",
        push_strategy="safe",
        dst_visibility=RepoVisibility.PUBLIC,
    )

    HubMirror(config).run()

    assert FakeHub.dynamic_called is False
    assert len(FakeMirror.created) == 1

    mirror_call = FakeMirror.created[0]
    assert mirror_call["src_name"] == "repo2"
    assert mirror_call["dst_name"] == "repo-two"
    assert mirror_call["push_strategy"] == "force"
    assert mirror_call["refs"].branches_include == ["main"]

    assert FakeHub.visibility_calls == [
        ("repo-two", RepoVisibility.PRIVATE)
    ]
