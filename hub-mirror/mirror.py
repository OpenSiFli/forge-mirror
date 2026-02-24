import logging
import os
import re
import shlex
import shutil
from fnmatch import fnmatch
from typing import List, Optional

import git
from tenacity import retry, stop_after_attempt, wait_exponential

from config import RefsConfig
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
        refs: Optional[RefsConfig] = None,
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
        self.refs: RefsConfig = refs or RefsConfig()
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
        logger.info("Trying fetch/reset recovery...")
        try:
            if self._uses_ssh_for_src():
                with local_repo.git.custom_environment(
                    GIT_SSH_COMMAND=self._ssh_command(self.src_key_path)
                ):
                    local_repo.git.fetch(
                        "--all", kill_after_timeout=self.timeout
                    )
                    local_repo.git.reset(
                        "--hard",
                        "origin/HEAD",
                        kill_after_timeout=self.timeout,
                    )
                    if self.lfs:
                        local_repo.git.lfs("fetch", "--all", "origin")
            else:
                local_repo.git.fetch(
                    "--all", kill_after_timeout=self.timeout
                )
                local_repo.git.reset(
                    "--hard",
                    "origin/HEAD",
                    kill_after_timeout=self.timeout,
                )
                if self.lfs:
                    local_repo.git.lfs("fetch", "--all", "origin")
        except git.exc.GitCommandError as fetch_error:
            logger.warning(
                f"Fetch/reset recovery failed for {self.src_name}: "
                f"{fetch_error}"
            )
            logger.warning(
                f"Repository may be corrupted, rebuilding {self.src_name}..."
            )
            shutil.rmtree(local_repo.working_dir)
            self._clone()

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

    def _filter_refs(
        self,
        patterns_include: List[str],
        patterns_exclude: List[str],
        ref_list: List[str],
    ) -> List[str]:
        if not patterns_include:
            return []

        filtered: List[str] = []
        for ref in ref_list:
            matched = any(
                fnmatch(ref, pattern)
                for pattern in patterns_include
            )
            if not matched:
                continue

            excluded = any(
                fnmatch(ref, pattern)
                for pattern in patterns_exclude
            )
            if not excluded:
                filtered.append(ref)

        # Keep order while de-duplicating.
        return list(dict.fromkeys(filtered))

    def _build_refspecs(
        self,
        refs_config: RefsConfig,
        local_repo: git.Repo,
    ) -> List[str]:
        branch_lines = local_repo.git.for_each_ref(
            "--format=%(refname)",
            "refs/remotes/origin",
        ).splitlines()
        branches = []
        for line in branch_lines:
            ref_name = line.strip()
            if not ref_name.startswith("refs/remotes/origin/"):
                continue
            branch = ref_name.replace("refs/remotes/origin/", "", 1)
            if branch == "HEAD":
                continue
            branches.append(branch)

        tags = [
            tag.strip()
            for tag in local_repo.git.tag("--list").splitlines()
            if tag.strip()
        ]

        filtered_branches = self._filter_refs(
            refs_config.branches_include,
            refs_config.branches_exclude,
            branches,
        )
        filtered_tags = self._filter_refs(
            refs_config.tags_include,
            refs_config.tags_exclude,
            tags,
        )

        refspecs: List[str] = []
        for branch in filtered_branches:
            refspecs.append(
                f"refs/remotes/origin/{branch}:refs/heads/{branch}"
            )
        for tag in filtered_tags:
            refspecs.append(f"refs/tags/{tag}:refs/tags/{tag}")
        return refspecs

    def _build_push_cmd(self, refspecs: List[str]) -> List[str]:
        cmd: List[str] = [self.hub.dst_type, "--prune"] + refspecs
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

        refspecs: List[str] = self._build_refspecs(self.refs, local_repo)
        if not refspecs:
            logger.info("No refs matched the filtering rules, skip pushing.")
            return

        push_cmd: List[str] = self._build_push_cmd(refspecs)
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
