import logging
import os
import re
import shlex
import shutil
from typing import List

import git
from tenacity import retry, stop_after_attempt, wait_exponential

from hub import Hub
from utils import cov2sec

logger = logging.getLogger(__name__)


class Mirror(object):
    def __init__(
        self,
        hub: Hub,
        src_name: str,
        dst_name: str,
        cache: str = ".",
        timeout: str = "0",
        push_strategy: str = "safe",
        dst_transport: str = "ssh",
        lfs: bool = False,
    ) -> None:
        self.hub: Hub = hub
        self.src_name: str = src_name
        self.dst_name: str = dst_name
        self.src_url: str = hub.src_repo_base + "/" + src_name + ".git"
        self.dst_url: str = hub.dst_repo_base + "/" + dst_name + ".git"
        self.repo_path: str = os.path.join(cache, src_name)
        self.src_key_path: str = os.path.expanduser("~/.ssh/id_rsa_src")
        self.dst_key_path: str = os.path.expanduser("~/.ssh/id_rsa_dst")
        self.timeout: int = 0
        if re.match(r"^\d+[dhms]?$", timeout):
            self.timeout = cov2sec(timeout)

        normalized_push_strategy = push_strategy.lower().strip()
        if normalized_push_strategy not in ("safe", "force", "no"):
            raise ValueError(
                "Invalid push strategy. Must be one of: safe, force, no."
            )
        self.push_strategy: str = normalized_push_strategy

        normalized_dst_transport = dst_transport.lower().strip()
        if normalized_dst_transport not in ("https", "ssh"):
            raise ValueError(
                "Invalid destination transport. Must be https or ssh."
            )
        self.dst_transport: str = normalized_dst_transport
        self.lfs: bool = lfs

    def _ssh_command(self, key_path: str) -> str:
        options: List[str] = [
            "-i",
            key_path,
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
        ]
        return "ssh " + " ".join(shlex.quote(option) for option in options)

    def _uses_ssh_for_src(self) -> bool:
        return self.src_url.startswith("ssh://")

    @retry(wait=wait_exponential(), reraise=True, stop=stop_after_attempt(3))
    def _clone(self) -> None:
        # TODO: process empty repo
        logger.info(f"Starting git clone {self.src_url}")
        mygit: git.cmd.Git = git.cmd.Git(os.getcwd())
        if self._uses_ssh_for_src():
            with mygit.custom_environment(
                GIT_SSH_COMMAND=self._ssh_command(self.src_key_path)
            ):
                mygit.clone(
                    git.cmd.Git.polish_url(self.src_url),
                    self.repo_path,
                    kill_after_timeout=self.timeout,
                )
        else:
            mygit.clone(
                git.cmd.Git.polish_url(self.src_url),
                self.repo_path,
                kill_after_timeout=self.timeout,
            )
        local_repo: git.Repo = git.Repo(self.repo_path)
        if self.lfs:
            if self._uses_ssh_for_src():
                with local_repo.git.custom_environment(
                    GIT_SSH_COMMAND=self._ssh_command(self.src_key_path)
                ):
                    local_repo.git.lfs("fetch", "--all", "origin")
            else:
                local_repo.git.lfs("fetch", "--all", "origin")
        logger.info(f"Clone completed: {os.getcwd() + self.repo_path}")

    @retry(wait=wait_exponential(), reraise=True, stop=stop_after_attempt(3))
    def _update(self, local_repo: git.Repo) -> None:
        try:
            if self._uses_ssh_for_src():
                with local_repo.git.custom_environment(
                    GIT_SSH_COMMAND=self._ssh_command(self.src_key_path)
                ):
                    local_repo.git.pull(kill_after_timeout=self.timeout)
                    if self.lfs:
                        local_repo.git.lfs("fetch", "--all", "origin")
            else:
                local_repo.git.pull(kill_after_timeout=self.timeout)
                if self.lfs:
                    local_repo.git.lfs("fetch", "--all", "origin")
        except git.exc.GitCommandError:
            logger.warning(f"Updating failed, re-clone {self.src_name}")
            shutil.rmtree(local_repo.working_dir)
            self._clone()

    @retry(wait=wait_exponential(), reraise=True, stop=stop_after_attempt(3))
    def download(self) -> None:
        logger.info("(1/3) Downloading...")
        try:
            local_repo: git.Repo = git.Repo(self.repo_path)
        except git.exc.NoSuchPathError:
            self._clone()
        else:
            logger.info("Updating repo...")
            self._update(local_repo)

    def create(self) -> None:
        logger.info("(2/3) Creating...")
        self.hub.create_dst_repo(self.dst_name)

    def _check_empty(self, repo: git.Repo) -> bool:
        cmd: List[str] = ["-n", "1", "--all"]
        if repo.git.rev_list(*cmd):
            return False
        return True

    def _build_push_cmd(self) -> List[str]:
        cmd: List[str] = [
            self.hub.dst_type,
            "refs/remotes/origin/*:refs/heads/*",
            "--tags",
            "--prune",
        ]
        if self.push_strategy == "force":
            return ["-f"] + cmd
        if self.push_strategy == "safe":
            return ["--force-with-lease"] + cmd
        return cmd

    @retry(wait=wait_exponential(), reraise=True, stop=stop_after_attempt(3))
    def push(self) -> None:
        local_repo: git.Repo = git.Repo(self.repo_path)
        git_cmd: git.cmd.Git = local_repo.git
        if self._check_empty(local_repo):
            logger.info(f"Empty repo {self.src_url}, skip pushing.")
            return

        cmd: List[str] = ["set-head", "origin", "-d"]
        if self._uses_ssh_for_src():
            with local_repo.git.custom_environment(
                GIT_SSH_COMMAND=self._ssh_command(self.src_key_path)
            ):
                local_repo.git.remote(*cmd)
        else:
            local_repo.git.remote(*cmd)

        try:
            local_repo.create_remote(self.hub.dst_type, self.dst_url)
        except git.exc.GitCommandError:
            logger.info(
                f"Remote exists, re-create: set {self.hub.dst_type} "
                f"to {self.dst_url}"
            )
            local_repo.delete_remote(self.hub.dst_type)
            local_repo.create_remote(self.hub.dst_type, self.dst_url)

        push_cmd: List[str] = self._build_push_cmd()
        logger.info(f"(3/3) Pushing with strategy={self.push_strategy}...")

        if self.dst_transport == "ssh":
            with git_cmd.custom_environment(
                GIT_SSH_COMMAND=self._ssh_command(self.dst_key_path)
            ):
                git_cmd.push(*push_cmd, kill_after_timeout=self.timeout)
                if self.lfs:
                    git_cmd.lfs("push", self.hub.dst_type, "--all")
        else:
            git_cmd.push(*push_cmd, kill_after_timeout=self.timeout)
            if self.lfs:
                git_cmd.lfs("push", self.hub.dst_type, "--all")
