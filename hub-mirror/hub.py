import logging
import time
from typing import Any, Dict, List, Tuple

import requests

from platforms import GitPlatform, RepoVisibility, get_platform

logger = logging.getLogger(__name__)


class Hub(object):
    def __init__(
        self,
        src_platform: str,
        src_account: str,
        dst_platform: str,
        dst_account: str,
        dst_token: str,
        src_token: str = "",
        src_account_type: str = "user",
        dst_account_type: str = "user",
        src_endpoint: str = "",
        dst_endpoint: str = "",
        src_transport: str = "https",
        dst_transport: str = "ssh",
        ssh_user: str = "git",
        api_timeout: int = 60,
        dst_visibility: RepoVisibility = RepoVisibility.AUTO,
    ) -> None:
        self.api_timeout: int = api_timeout
        self.src_account_type: str = src_account_type
        self.dst_account_type: str = dst_account_type
        self.dst_visibility: RepoVisibility = dst_visibility
        self.src_type: str = src_platform
        self.dst_type: str = dst_platform
        self.src_account: str = src_account
        self.dst_account: str = dst_account
        self.src_transport: str = src_transport
        self.dst_transport: str = dst_transport
        self.ssh_user: str = ssh_user

        self.src_platform: GitPlatform = get_platform(
            self.src_type, endpoint=src_endpoint
        )
        self.dst_platform: GitPlatform = get_platform(
            self.dst_type, endpoint=dst_endpoint
        )
        self.src_platform.validate_account_type(
            self.src_account_type, "source"
        )
        self.dst_platform.validate_account_type(
            self.dst_account_type, "destination"
        )

        self.src_token: str = src_token
        self.dst_token: str = dst_token
        self.session: requests.Session = requests.Session()
        self.src_repo_base: str = self.src_platform.get_clone_repo_base(
            self.src_account,
            self.src_transport,
            ssh_user=self.ssh_user,
        )
        self.dst_repo_base: str = self.dst_platform.get_push_repo_base(
            self.dst_account,
            self.dst_transport,
            token=self.dst_token,
            ssh_user=self.ssh_user,
        )

    def has_dst_repo(self, repo_name: str) -> bool:
        return self.dst_platform.repo_exists(
            self.session,
            self.dst_account,
            repo_name,
            self.dst_token,
            self.api_timeout,
        )

    def create_dst_repo(self, repo_name: str) -> bool:
        created: bool = False
        if not self.has_dst_repo(repo_name):
            logger.info(f"{repo_name} doesn't exist, create it...")
            created = self.dst_platform.create_repo(
                self.session,
                self.dst_account,
                self.dst_account_type,
                repo_name,
                self.dst_token,
                self.api_timeout,
            )
        else:
            logger.info(f"{repo_name} repo exist, skip creating...")
        if created:
            time.sleep(2)
        return created

    def dynamic_list(self) -> List[str]:
        try:
            url: str = self.src_platform.repo_list_url(
                self.src_account, self.src_account_type
            )
        except NotImplementedError as exc:
            raise ValueError(str(exc)) from exc
        return self._get_all_repo_names(url)

    def update_dst_repo_visibility(
        self,
        repo_name: str,
        visibility: RepoVisibility = RepoVisibility.AUTO,
    ) -> bool:
        target_visibility = (
            visibility
            if visibility != RepoVisibility.AUTO
            else self.dst_visibility
        )
        return self.dst_platform.update_repo_visibility(
            self.session,
            self.dst_account,
            repo_name,
            target_visibility,
            self.dst_token,
            self.api_timeout,
        )

    def _get_all_repo_names(self, url: str, page: int = 1) -> List[str]:
        per_page: int = 60
        all_items: List[str] = []
        headers, params = self._get_src_auth()

        while True:
            query = {
                "page": page,
                "per_page": per_page,
            }
            query.update(params)
            response: requests.Response = self.session.get(
                url,
                headers=headers,
                params=query,
                timeout=self.api_timeout,
            )
            if response.status_code != 200:
                logger.error(f"Repo getting failed: {response.text}")
                return all_items

            items: List[Dict[str, Any]] = response.json()
            if not items:
                return all_items

            all_items.extend([i["name"] for i in items])
            page += 1

    def _get_src_auth(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        if not self.src_token:
            return {}, {}

        platform_name = self.src_platform.name
        if platform_name == "github":
            return {"Authorization": f"token {self.src_token}"}, {}
        if platform_name in ("gitee", "gitcode"):
            return {}, {"access_token": self.src_token}
        if platform_name == "gitlab":
            return {"PRIVATE-TOKEN": self.src_token}, {}
        return {}, {}
