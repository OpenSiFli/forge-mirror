import json
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Type
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

ALLOWED_VISIBILITY = ("auto", "public", "private")


class RepoVisibility(str, Enum):
    AUTO = "auto"
    PUBLIC = "public"
    PRIVATE = "private"

    @classmethod
    def from_str(cls, value: Any) -> "RepoVisibility":
        if isinstance(value, RepoVisibility):
            return value
        normalized = str(value).strip().lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            allowed = ", ".join(ALLOWED_VISIBILITY)
            raise ValueError(
                f"Invalid visibility '{value}'. Must be one of: {allowed}."
            ) from exc


class GitPlatform(ABC):
    name: str
    host: str
    api_base: str
    repo_field: str

    def __init__(self, endpoint: str = "") -> None:
        # Keep a uniform constructor signature for typing convenience.
        del endpoint

    def _join_account_path(self, account: str) -> str:
        return f"/{account}" if account else ""

    def get_clone_repo_base(
        self,
        account: str,
        transport: str,
        ssh_user: str = "git",
    ) -> str:
        account_path = self._join_account_path(account)
        if transport == "ssh":
            return f"ssh://{ssh_user}@{self.host}{account_path}"
        return f"https://{self.host}{account_path}"

    def get_push_repo_base(
        self,
        account: str,
        transport: str,
        token: str = "",
        ssh_user: str = "git",
    ) -> str:
        account_path = self._join_account_path(account)
        if transport == "ssh":
            return f"ssh://{ssh_user}@{self.host}{account_path}"
        if token:
            return f"https://{quote(token, safe='')}@{self.host}{account_path}"
        return f"https://{self.host}{account_path}"

    def repo_list_url(self, account: str, account_type: str) -> str:
        return f"{self.api_base}/{account_type}s/{account}/{self.repo_field}"

    def _validate_account_type(
        self,
        account_type: str,
        role: str,
        allowed: Sequence[str],
    ) -> None:
        if account_type not in allowed:
            allowed_list = "', '".join(allowed)
            raise ValueError(
                f"For {self.name}, {role} account_type must be "
                f"one of '{allowed_list}'."
            )

    @abstractmethod
    def validate_account_type(self, account_type: str, role: str) -> None:
        raise NotImplementedError

    def create_repo(
        self,
        session: requests.Session,
        account: str,
        account_type: str,
        repo_name: str,
        token: str,
        api_timeout: int,
    ) -> bool:
        logger.info(f"Creating destination repository '{repo_name}'...")
        created = self._do_create_repo(
            session,
            account,
            account_type,
            repo_name,
            token,
            api_timeout,
        )
        if created:
            logger.info("Destination repo creating accepted.")
            return True
        logger.error("Destination repo creating failed.")
        return False

    @abstractmethod
    def _do_create_repo(
        self,
        session: requests.Session,
        account: str,
        account_type: str,
        repo_name: str,
        token: str,
        api_timeout: int,
    ) -> bool:
        raise NotImplementedError

    def update_repo_visibility(
        self,
        session: requests.Session,
        account: str,
        repo_name: str,
        visibility: RepoVisibility,
        token: str,
        api_timeout: int,
    ) -> bool:
        try:
            visibility_enum = RepoVisibility.from_str(visibility)
        except ValueError as exc:
            logger.error(str(exc))
            return False

        if visibility_enum == RepoVisibility.AUTO:
            return True

        logger.info(
            f"Updating repo visibility to {visibility_enum.value}..."
        )
        updated = self._do_update_visibility(
            session,
            account,
            repo_name,
            visibility_enum,
            token,
            api_timeout,
        )
        if updated:
            logger.info("Repo visibility updated.")
            return True
        logger.error("Repo visibility update failed.")
        return False

    @abstractmethod
    def _do_update_visibility(
        self,
        session: requests.Session,
        account: str,
        repo_name: str,
        visibility: RepoVisibility,
        token: str,
        api_timeout: int,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def repo_exists(
        self,
        session: requests.Session,
        account: str,
        repo_name: str,
        token: str,
        api_timeout: int,
    ) -> bool:
        raise NotImplementedError


class GitHubPlatform(GitPlatform):
    name = "github"
    repo_field = "repos"

    def __init__(self, _endpoint: str = "") -> None:
        self.host: str = "github.com"
        self.api_base: str = "https://api.github.com"

    def validate_account_type(self, account_type: str, role: str) -> None:
        self._validate_account_type(account_type, role, ("user", "org"))

    def _do_create_repo(
        self,
        session: requests.Session,
        account: str,
        account_type: str,
        repo_name: str,
        token: str,
        api_timeout: int,
    ) -> bool:
        suffix: str = "user/repos"
        if account_type == "org":
            suffix = f"orgs/{account}/repos"
        url: str = f"{self.api_base}/{suffix}"
        data: str = json.dumps({"name": repo_name})
        response: requests.Response = session.post(
            url,
            data=data,
            headers={"Authorization": "token " + token},
            timeout=api_timeout,
        )
        if response.status_code == 201:
            return True
        logger.error(f"GitHub create repo API failed: {response.text}")
        return False

    def _do_update_visibility(
        self,
        session: requests.Session,
        account: str,
        repo_name: str,
        visibility: RepoVisibility,
        token: str,
        api_timeout: int,
    ) -> bool:
        url: str = f"{self.api_base}/repos/{account}/{repo_name}"
        response: requests.Response = session.patch(
            url,
            headers={
                "Authorization": "token " + token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"private": visibility == RepoVisibility.PRIVATE},
            timeout=api_timeout,
        )
        if response.status_code == 200:
            return True
        logger.error(f"GitHub visibility API failed: {response.text}")
        return False

    def repo_exists(
        self,
        session: requests.Session,
        account: str,
        repo_name: str,
        token: str,
        api_timeout: int,
    ) -> bool:
        url = f"{self.api_base}/repos/{account}/{repo_name}"
        headers: Dict[str, str] = {}
        if token:
            headers["Authorization"] = f"token {token}"
        response = session.get(url, headers=headers, timeout=api_timeout)
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        logger.error(f"GitHub repo_exists API failed: {response.text}")
        return False


class GiteePlatform(GitPlatform):
    name = "gitee"
    repo_field = "repos"

    def __init__(self, _endpoint: str = "") -> None:
        self.host: str = "gitee.com"
        self.api_base: str = "https://gitee.com/api/v5"

    def validate_account_type(self, account_type: str, role: str) -> None:
        self._validate_account_type(account_type, role, ("user", "org"))

    def _do_create_repo(
        self,
        session: requests.Session,
        account: str,
        account_type: str,
        repo_name: str,
        token: str,
        api_timeout: int,
    ) -> bool:
        suffix: str = "user/repos"
        if account_type == "org":
            suffix = f"orgs/{account}/repos"
        url: str = f"{self.api_base}/{suffix}"
        response: requests.Response = session.post(
            url,
            headers={"Content-Type": "application/json;charset=UTF-8"},
            params={"name": repo_name, "access_token": token},
            timeout=api_timeout,
        )
        if response.status_code == 201:
            return True
        logger.error(f"Gitee create repo API failed: {response.text}")
        return False

    def _do_update_visibility(
        self,
        session: requests.Session,
        account: str,
        repo_name: str,
        visibility: RepoVisibility,
        token: str,
        api_timeout: int,
    ) -> bool:
        url: str = f"{self.api_base}/repos/{account}/{repo_name}"
        is_private: bool = visibility == RepoVisibility.PRIVATE
        response: requests.Response = session.patch(
            url,
            headers={"Content-Type": "application/json;charset=UTF-8"},
            params={
                "access_token": token,
                "name": repo_name,
                "private": is_private,
            },
            timeout=api_timeout,
        )
        if response.status_code == 200:
            return True
        logger.error(f"Gitee visibility API failed: {response.text}")
        return False

    def repo_exists(
        self,
        session: requests.Session,
        account: str,
        repo_name: str,
        token: str,
        api_timeout: int,
    ) -> bool:
        url = f"{self.api_base}/repos/{account}/{repo_name}"
        params: Dict[str, str] = {}
        if token:
            params["access_token"] = token
        response = session.get(url, params=params, timeout=api_timeout)
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        logger.error(f"Gitee repo_exists API failed: {response.text}")
        return False


class GitcodePlatform(GitPlatform):
    name = "gitcode"
    repo_field = "repos"

    def __init__(self, _endpoint: str = "") -> None:
        self.host: str = "gitcode.com"
        self.api_base: str = "https://api.gitcode.com/api/v5"

    def validate_account_type(self, account_type: str, role: str) -> None:
        self._validate_account_type(account_type, role, ("user", "org"))

    def _do_create_repo(
        self,
        session: requests.Session,
        account: str,
        account_type: str,
        repo_name: str,
        token: str,
        api_timeout: int,
    ) -> bool:
        suffix: str = "user/repos"
        if account_type == "org":
            suffix = f"orgs/{account}/repos"
        url: str = f"{self.api_base}/{suffix}"
        response: requests.Response = session.post(
            url,
            headers={"Content-Type": "application/json;charset=UTF-8"},
            params={"name": repo_name, "access_token": token},
            timeout=api_timeout,
        )
        if response.status_code == 201:
            return True
        logger.error(f"GitCode create repo API failed: {response.text}")
        return False

    def _do_update_visibility(
        self,
        session: requests.Session,
        account: str,
        repo_name: str,
        visibility: RepoVisibility,
        token: str,
        api_timeout: int,
    ) -> bool:
        url: str = f"{self.api_base}/repos/{account}/{repo_name}"
        response: requests.Response = session.patch(
            url,
            headers={"Content-Type": "application/json;charset=UTF-8"},
            params={"access_token": token},
            json={
                "name": repo_name,
                "private": visibility == RepoVisibility.PRIVATE,
            },
            timeout=api_timeout,
        )
        if response.status_code == 200:
            return True
        logger.error(f"GitCode visibility API failed: {response.text}")
        return False

    def repo_exists(
        self,
        session: requests.Session,
        account: str,
        repo_name: str,
        token: str,
        api_timeout: int,
    ) -> bool:
        url = f"{self.api_base}/repos/{account}/{repo_name}"
        params: Dict[str, str] = {}
        if token:
            params["access_token"] = token
        response = session.get(url, params=params, timeout=api_timeout)
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        logger.error(f"GitCode repo_exists API failed: {response.text}")
        return False


class GitLabPlatform(GitPlatform):
    name = "gitlab"
    repo_field = "projects"

    def __init__(self, endpoint: str = "") -> None:
        host = (endpoint or "gitlab.com").strip().strip("/")
        api_host = host
        if ":" in host:
            maybe_host, maybe_port = host.rsplit(":", 1)
            if maybe_host and maybe_port.isdigit():
                api_host = maybe_host

        self.host: str = host
        self.api_host: str = api_host
        self.api_base: str = f"https://{api_host}/api/v4"

    def get_clone_repo_base(
        self,
        account: str,
        transport: str,
        ssh_user: str = "git",
    ) -> str:
        account_path = self._join_account_path(account)
        if transport == "ssh":
            return f"ssh://{ssh_user}@{self.host}{account_path}"
        return f"https://{self.api_host}{account_path}"

    def get_push_repo_base(
        self,
        account: str,
        transport: str,
        token: str = "",
        ssh_user: str = "git",
    ) -> str:
        account_path = self._join_account_path(account)
        if transport == "ssh":
            return f"ssh://{ssh_user}@{self.host}{account_path}"
        if token:
            return (
                f"https://{quote(token, safe='')}@"
                f"{self.api_host}{account_path}"
            )
        return f"https://{self.api_host}{account_path}"

    def validate_account_type(self, account_type: str, role: str) -> None:
        self._validate_account_type(account_type, role, ("user", "group"))

    def _do_create_repo(
        self,
        session: requests.Session,
        account: str,
        account_type: str,
        repo_name: str,
        token: str,
        api_timeout: int,
    ) -> bool:
        url: str = f"{self.api_base}/{self.repo_field}"
        headers: Dict[str, str] = {"PRIVATE-TOKEN": token}
        data: Dict[str, Any] = {"name": repo_name, "visibility": "public"}
        if account_type == "group":
            group_id: Optional[int] = self._get_group_id(
                session, account, token, api_timeout
            )
            if group_id is None:
                logger.error(
                    f"Failed to create repository '{repo_name}': "
                    f"group '{account}' not found."
                )
                return False
            data["namespace_id"] = group_id
        response: requests.Response = session.post(
            url,
            data=data,
            headers=headers,
            timeout=api_timeout,
        )
        if response.status_code == 201:
            return True
        logger.error(f"GitLab create repo API failed: {response.text}")
        return False

    def _get_group_id(
        self,
        session: requests.Session,
        group_name: str,
        token: str,
        api_timeout: int,
    ) -> Optional[int]:
        url: str = f"{self.api_base}/groups"
        headers: Dict[str, str] = {"PRIVATE-TOKEN": token}
        response: requests.Response = session.get(
            url, headers=headers, timeout=api_timeout
        )
        if response.status_code == 200:
            groups: List[Dict[str, Any]] = response.json()
            for group in groups:
                if group.get("path") == group_name:
                    return group.get("id")
            logger.warning(f"Failed to find group ID for '{group_name}'.")
        else:
            logger.error("Failed to get groups list.")
            logger.error(f"Error message: {response.text}")
        return None

    def _do_update_visibility(
        self,
        session: requests.Session,
        account: str,
        repo_name: str,
        visibility: RepoVisibility,
        token: str,
        api_timeout: int,
    ) -> bool:
        project_path = f"{account}/{repo_name}"
        encoded_project = requests.utils.quote(project_path, safe="")
        url: str = f"{self.api_base}/projects/{encoded_project}"
        headers: Dict[str, str] = {"PRIVATE-TOKEN": token}
        response: requests.Response = session.put(
            url,
            data={"visibility": visibility.value},
            headers=headers,
            timeout=api_timeout,
        )
        if response.status_code == 200:
            return True
        logger.error(f"GitLab visibility API failed: {response.text}")
        return False

    def repo_exists(
        self,
        session: requests.Session,
        account: str,
        repo_name: str,
        token: str,
        api_timeout: int,
    ) -> bool:
        project_path = f"{account}/{repo_name}"
        encoded_project = requests.utils.quote(project_path, safe="")
        url = f"{self.api_base}/projects/{encoded_project}"
        headers: Dict[str, str] = {}
        if token:
            headers["PRIVATE-TOKEN"] = token
        response = session.get(url, headers=headers, timeout=api_timeout)
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        logger.error(f"GitLab repo_exists API failed: {response.text}")
        return False


class BareGitPlatform(GitPlatform):
    name = "git"
    repo_field = ""

    def __init__(self, endpoint: str = "") -> None:
        cleaned_endpoint = endpoint.strip().strip("/")
        if not cleaned_endpoint:
            raise ValueError(
                "For git platform, endpoint is required. "
                "Example: git.example.com/my-org"
            )
        self.endpoint: str = cleaned_endpoint
        self.host: str = cleaned_endpoint
        self.api_base: str = ""

    def get_clone_repo_base(
        self,
        account: str,
        transport: str,
        ssh_user: str = "git",
    ) -> str:
        base = self.endpoint
        if account:
            base = f"{base}/{account}"
        if transport == "ssh":
            return f"ssh://{ssh_user}@{base}"
        return f"https://{base}"

    def get_push_repo_base(
        self,
        account: str,
        transport: str,
        token: str = "",
        ssh_user: str = "git",
    ) -> str:
        base = self.endpoint
        if account:
            base = f"{base}/{account}"
        if transport == "ssh":
            return f"ssh://{ssh_user}@{base}"
        if token:
            return f"https://{quote(token, safe='')}@{base}"
        return f"https://{base}"

    def repo_list_url(self, account: str, account_type: str) -> str:
        raise NotImplementedError(
            "git platform does not support dynamic listing, "
            "please provide repos.static"
        )

    def validate_account_type(self, account_type: str, role: str) -> None:
        return None

    def _do_create_repo(
        self,
        session: requests.Session,
        account: str,
        account_type: str,
        repo_name: str,
        token: str,
        api_timeout: int,
    ) -> bool:
        return True

    def _do_update_visibility(
        self,
        session: requests.Session,
        account: str,
        repo_name: str,
        visibility: RepoVisibility,
        token: str,
        api_timeout: int,
    ) -> bool:
        return True

    def repo_exists(
        self,
        session: requests.Session,
        account: str,
        repo_name: str,
        token: str,
        api_timeout: int,
    ) -> bool:
        return True


def get_platform(name: str, endpoint: str = "") -> GitPlatform:
    normalized_name = name.lower()
    platforms: Dict[str, Type[GitPlatform]] = {
        "github": GitHubPlatform,
        "gitee": GiteePlatform,
        "gitlab": GitLabPlatform,
        "gitcode": GitcodePlatform,
        "git": BareGitPlatform,
    }
    platform_cls = platforms.get(normalized_name)
    if not platform_cls:
        supported = ", ".join(sorted(platforms.keys()))
        raise ValueError(
            f"Unsupported platform_type '{name}'. Supported: {supported}"
        )
    return platform_cls(endpoint)
