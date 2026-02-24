from unittest.mock import Mock

import pytest

from platforms import (
    BareGitPlatform,
    GiteePlatform,
    GitHubPlatform,
    GitLabPlatform,
    GitcodePlatform,
    RepoVisibility,
    get_platform,
)


class FakeResponse:
    def __init__(self, status_code: int, text: str = "{}") -> None:
        self.status_code = status_code
        self.text = text

    def json(self):
        return []


@pytest.mark.parametrize(
    "platform,account_type",
    [
        (GitHubPlatform(), "user"),
        (GiteePlatform(), "user"),
        (GitcodePlatform(), "user"),
        (GitLabPlatform(), "user"),
    ],
)
def test_create_repo_success_and_failure(platform, account_type: str) -> None:
    session = Mock()
    session.post.return_value = FakeResponse(201, "created")

    assert (
        platform.create_repo(
            session,
            account="owner",
            account_type=account_type,
            repo_name="repo",
            token="token",
            api_timeout=30,
        )
        is True
    )

    session.post.return_value = FakeResponse(500, "failed")
    assert (
        platform.create_repo(
            session,
            account="owner",
            account_type=account_type,
            repo_name="repo",
            token="token",
            api_timeout=30,
        )
        is False
    )


@pytest.mark.parametrize(
    "platform,expected_path",
    [
        (GitHubPlatform(), "/repos/owner/repo"),
        (GiteePlatform(), "/repos/owner/repo"),
        (GitcodePlatform(), "/repos/owner/repo"),
        (GitLabPlatform(), "/projects/owner%2Frepo"),
    ],
)
def test_repo_exists_by_single_repo_api(platform, expected_path: str) -> None:
    session = Mock()

    session.get.return_value = FakeResponse(200)
    assert (
        platform.repo_exists(
            session,
            account="owner",
            repo_name="repo",
            token="token",
            api_timeout=30,
        )
        is True
    )
    url = session.get.call_args.args[0]
    assert expected_path in url

    session.get.return_value = FakeResponse(404)
    assert (
        platform.repo_exists(
            session,
            account="owner",
            repo_name="repo",
            token="token",
            api_timeout=30,
        )
        is False
    )


@pytest.mark.parametrize(
    "platform,http_method",
    [
        (GitHubPlatform(), "patch"),
        (GiteePlatform(), "patch"),
        (GitcodePlatform(), "patch"),
        (GitLabPlatform(), "put"),
    ],
)
def test_update_repo_visibility_success_failure_and_auto(
    platform,
    http_method: str,
) -> None:
    session = Mock()
    getattr(session, http_method).return_value = FakeResponse(200)

    assert (
        platform.update_repo_visibility(
            session,
            account="owner",
            repo_name="repo",
            visibility=RepoVisibility.PUBLIC,
            token="token",
            api_timeout=30,
        )
        is True
    )

    getattr(session, http_method).return_value = FakeResponse(500)
    assert (
        platform.update_repo_visibility(
            session,
            account="owner",
            repo_name="repo",
            visibility=RepoVisibility.PRIVATE,
            token="token",
            api_timeout=30,
        )
        is False
    )

    session_auto = Mock()
    assert (
        platform.update_repo_visibility(
            session_auto,
            account="owner",
            repo_name="repo",
            visibility=RepoVisibility.AUTO,
            token="token",
            api_timeout=30,
        )
        is True
    )
    assert not session_auto.patch.called
    assert not session_auto.put.called


def test_bare_git_platform_noop_behaviors() -> None:
    platform = BareGitPlatform("git.example.com/my-org")
    session = Mock()

    assert platform.get_clone_repo_base("", "ssh", ssh_user="git") == (
        "ssh://git@git.example.com/my-org"
    )
    assert platform.get_push_repo_base("", "https", token="token") == (
        "https://token@git.example.com/my-org"
    )

    assert (
        platform.create_repo(
            session,
            account="",
            account_type="user",
            repo_name="repo",
            token="token",
            api_timeout=30,
        )
        is True
    )
    assert (
        platform.update_repo_visibility(
            session,
            account="",
            repo_name="repo",
            visibility=RepoVisibility.PRIVATE,
            token="token",
            api_timeout=30,
        )
        is True
    )
    assert (
        platform.repo_exists(
            session,
            account="",
            repo_name="repo",
            token="token",
            api_timeout=30,
        )
        is True
    )

    with pytest.raises(NotImplementedError):
        platform.repo_list_url("", "user")


def test_gitlab_separated_endpoint_and_api_endpoint() -> None:
    platform = GitLabPlatform(
        endpoint="gitlab.sifli.com:8218",
        api_endpoint="gitlab.sifli.com",
    )

    assert platform.api_base == "https://gitlab.sifli.com/api/v4"
    assert platform.get_clone_repo_base("sifli", "ssh") == (
        "ssh://git@gitlab.sifli.com:8218/sifli"
    )
    assert platform.get_clone_repo_base("sifli", "https") == (
        "https://gitlab.sifli.com:8218/sifli"
    )
    assert platform.get_push_repo_base("sifli", "ssh") == (
        "ssh://git@gitlab.sifli.com:8218/sifli"
    )
    assert platform.get_push_repo_base(
        "sifli", "https", token="token"
    ) == "https://token@gitlab.sifli.com:8218/sifli"


def test_get_platform_factory() -> None:
    platform = get_platform("git", endpoint="git.example.com/my-org")
    assert isinstance(platform, BareGitPlatform)

    gitlab = get_platform(
        "gitlab",
        endpoint="gitlab.sifli.com:8218",
        api_endpoint="gitlab.sifli.com",
    )
    assert isinstance(gitlab, GitLabPlatform)
    assert gitlab.host == "gitlab.sifli.com:8218"
    assert gitlab.api_base == "https://gitlab.sifli.com/api/v4"

    with pytest.raises(ValueError):
        get_platform("unknown-platform")
