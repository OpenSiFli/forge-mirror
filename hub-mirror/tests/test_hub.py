import pytest

from hub import Hub


def test_src_token_auth_headers_by_platform() -> None:
    github = Hub(
        src_platform="github",
        src_account="src",
        dst_platform="github",
        dst_account="dst",
        dst_token="dst-token",
        src_token="src-token",
    )
    assert github._get_src_auth() == (
        {"Authorization": "token src-token"},
        {},
    )

    gitee = Hub(
        src_platform="gitee",
        src_account="src",
        dst_platform="github",
        dst_account="dst",
        dst_token="dst-token",
        src_token="src-token",
    )
    assert gitee._get_src_auth() == ({}, {"access_token": "src-token"})

    gitcode = Hub(
        src_platform="gitcode",
        src_account="src",
        dst_platform="github",
        dst_account="dst",
        dst_token="dst-token",
        src_token="src-token",
    )
    assert gitcode._get_src_auth() == ({}, {"access_token": "src-token"})

    gitlab = Hub(
        src_platform="gitlab",
        src_account="src",
        dst_platform="github",
        dst_account="dst",
        dst_token="dst-token",
        src_token="src-token",
    )
    assert gitlab._get_src_auth() == (
        {"PRIVATE-TOKEN": "src-token"},
        {},
    )


def test_src_token_ignored_for_bare_git_platform() -> None:
    hub = Hub(
        src_platform="git",
        src_account="",
        dst_platform="github",
        dst_account="dst",
        dst_token="dst-token",
        src_token="src-token",
        src_endpoint="git.example.com/my-org",
    )
    assert hub._get_src_auth() == ({}, {})


def test_dynamic_list_not_supported_for_bare_git_platform() -> None:
    hub = Hub(
        src_platform="git",
        src_account="",
        dst_platform="github",
        dst_account="dst",
        dst_token="dst-token",
        src_endpoint="git.example.com/my-org",
    )

    with pytest.raises(ValueError, match="dynamic listing"):
        hub.dynamic_list()
