from unittest.mock import Mock, patch

from git.exc import GitCommandError

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


def test_retry_configuration() -> None:
    assert hasattr(Mirror._clone, "retry")
    assert Mirror._clone.retry.stop.max_attempt_number == 3
    assert hasattr(Mirror._update, "retry")
    assert Mirror._update.retry.stop.max_attempt_number == 3
    assert not hasattr(Mirror.download, "retry")


def test_update_success_does_not_rebuild_repo() -> None:
    mirror = make_mirror()
    local_repo = Mock()
    local_repo.git.fetch.return_value = ""
    local_repo.git.reset.return_value = ""

    mirror._clone = Mock()

    with patch("mirror.shutil.rmtree") as mocked_rmtree:
        mirror._update(local_repo)

    mocked_rmtree.assert_not_called()
    mirror._clone.assert_not_called()


def test_update_fetch_failure_triggers_rebuild() -> None:
    mirror = make_mirror()
    local_repo = Mock()
    local_repo.working_dir = "/tmp/fake-repo"
    local_repo.git.fetch.side_effect = GitCommandError("fetch", 128)

    mirror._clone = Mock()

    with patch("mirror.shutil.rmtree") as mocked_rmtree:
        mirror._update(local_repo)

    mocked_rmtree.assert_called_once_with("/tmp/fake-repo")
    mirror._clone.assert_called_once()
