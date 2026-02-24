import logging
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

import click

from hub import Hub
from mirror import Mirror
from platforms import ALLOWED_VISIBILITY, RepoVisibility
from utils import cov2sec

logger = logging.getLogger(__name__)

ALLOWED_PLATFORMS: Sequence[str] = (
    "github",
    "gitee",
    "gitlab",
    "gitcode",
    "git",
)
ALLOWED_TRANSPORTS: Sequence[str] = ("https", "ssh")
ALLOWED_PUSH_STRATEGIES: Sequence[str] = ("safe", "force", "no")
ALLOWED_LOG_LEVELS: Sequence[str] = ("DEBUG", "INFO", "WARNING", "ERROR")


@dataclass(frozen=True)
class MirrorConfig:
    src_account: str
    dst_platform: str
    dst_account: str
    dst_token: str
    src_platform: str = "github"
    src_account_type: str = "user"
    dst_account_type: str = "user"
    src_endpoint: str = ""
    dst_endpoint: str = ""
    src_transport: str = "https"
    dst_transport: str = "ssh"
    ssh_user: str = "git"
    cache_path: str = "hub-mirror-cache"
    repos: str = ""
    push_strategy: str = "safe"
    log_level: str = "INFO"
    timeout: str = "30m"
    api_timeout: str = "60"
    lfs: bool = False
    dst_visibility: RepoVisibility = RepoVisibility.AUTO
    src_token: str = ""


class HubMirror(object):
    def __init__(self, config: MirrorConfig) -> None:
        self.config: MirrorConfig = config
        # Phase 1 占位: Phase 2 将由 YAML repos 配置驱动。
        self.white_list: List[str] = []
        self.black_list: List[str] = []
        self.static_list: List[str] = []
        self.mappings: Dict[str, str] = {}

    def test_black_white_list(self, repo: str) -> bool:
        if repo in self.black_list:
            logger.info(f"Skip, {repo} in black list: {self.black_list}")
            return False

        if self.white_list and repo not in self.white_list:
            logger.info(f"Skip, {repo} not in white list: {self.white_list}")
            return False

        return True

    def run(self) -> None:
        config = self.config
        hub = Hub(
            src_platform=config.src_platform,
            src_account=config.src_account,
            dst_platform=config.dst_platform,
            dst_account=config.dst_account,
            dst_token=config.dst_token,
            src_token=config.src_token,
            src_account_type=config.src_account_type,
            dst_account_type=config.dst_account_type,
            src_endpoint=config.src_endpoint,
            dst_endpoint=config.dst_endpoint,
            src_transport=config.src_transport,
            dst_transport=config.dst_transport,
            ssh_user=config.ssh_user,
            api_timeout=parse_duration_seconds(config.api_timeout),
            dst_visibility=config.dst_visibility,
        )

        repos: List[str] = self.static_list
        src_repos: List[str] = repos if repos else hub.dynamic_list()

        total: int = len(src_repos)
        succeeded: int = 0
        skip: int = 0
        failed_list: List[str] = []
        for src_repo in src_repos:
            dst_repo: str = self.mappings.get(src_repo, src_repo)
            logger.info(f"Map {src_repo} to {dst_repo}")
            if self.test_black_white_list(src_repo):
                logger.info(f"Backup {src_repo}")
                try:
                    mirror = Mirror(
                        hub,
                        src_repo,
                        dst_repo,
                        cache=config.cache_path,
                        timeout=config.timeout,
                        push_strategy=config.push_strategy,
                        dst_transport=config.dst_transport,
                        lfs=config.lfs,
                    )
                    mirror.download()
                    mirror.create()
                    mirror.push()
                    if not hub.update_dst_repo_visibility(dst_repo):
                        raise RuntimeError(
                            f"Failed to update repo visibility for {dst_repo}"
                        )
                    succeeded += 1
                except Exception as e:
                    logger.error(f"Mirror failed for {src_repo}: {e}")
                    logger.debug("Mirror failure details", exc_info=True)
                    failed_list.append(src_repo)
            else:
                skip += 1
        failed: int = total - succeeded - skip
        summary = (
            f"Total: {total}, skip: {skip}, succeeded: {succeeded}, "
            f"failed: {failed}."
        )
        logger.info(summary)
        logger.info(f"Failed: {failed_list}")
        if failed_list:
            sys.exit(1)


def add_options(
    options: List[Callable[[Callable[..., None]], Callable[..., None]]],
) -> Callable[[Callable[..., None]], Callable[..., None]]:
    def decorator(func: Callable[..., None]) -> Callable[..., None]:
        for option in reversed(options):
            func = option(func)
        return func

    return decorator


CLI_OPTIONS = [
    click.option(
        "--src-platform",
        default="github",
        type=click.Choice(ALLOWED_PLATFORMS, case_sensitive=False),
        show_default=True,
        help="Source platform type.",
    ),
    click.option("--src-account", required=True, help="Source account name."),
    click.option(
        "--dst-platform",
        required=True,
        type=click.Choice(ALLOWED_PLATFORMS, case_sensitive=False),
        help="Destination platform type.",
    ),
    click.option(
        "--dst-account", required=True, help="Destination account name."
    ),
    click.option(
        "--dst-token",
        required=True,
        help="Token for destination hub.",
    ),
    click.option(
        "--src-token",
        default="",
        show_default=True,
        help="Token for source hub API.",
    ),
    click.option("--src-account-type", default="user", show_default=True),
    click.option("--dst-account-type", default="user", show_default=True),
    click.option("--src-endpoint", default="", show_default=True),
    click.option("--dst-endpoint", default="", show_default=True),
    click.option(
        "--src-transport",
        default="https",
        type=click.Choice(ALLOWED_TRANSPORTS, case_sensitive=False),
        show_default=True,
    ),
    click.option(
        "--dst-transport",
        default="ssh",
        type=click.Choice(ALLOWED_TRANSPORTS, case_sensitive=False),
        show_default=True,
    ),
    click.option("--ssh-user", default="git", show_default=True),
    click.option(
        "--cache-path",
        default="hub-mirror-cache",
        show_default=True,
    ),
    click.option("--repos", default="", show_default=True),
    click.option(
        "--push-strategy",
        default="safe",
        type=click.Choice(ALLOWED_PUSH_STRATEGIES, case_sensitive=False),
        show_default=True,
    ),
    click.option(
        "--log-level",
        default="INFO",
        type=click.Choice(ALLOWED_LOG_LEVELS, case_sensitive=False),
        show_default=True,
        help="Log level (DEBUG, INFO, WARNING, ERROR).",
    ),
    click.option("--timeout", default="30m", show_default=True),
    click.option("--api-timeout", default="60", show_default=True),
    click.option("--lfs", default=False, type=click.BOOL, show_default=True),
    click.option(
        "--dst-visibility",
        default="auto",
        type=click.Choice(ALLOWED_VISIBILITY, case_sensitive=False),
        show_default=True,
        help="Set destination repo visibility (public, private, or auto).",
    ),
]


def parse_log_level(value: Optional[Any]) -> int:
    text = str(value or "").strip().upper()
    if text not in ALLOWED_LOG_LEVELS:
        allowed = ", ".join(ALLOWED_LOG_LEVELS)
        raise ValueError(
            f"Invalid log level '{value}'. Must be one of: {allowed}."
        )
    return int(getattr(logging, text))


def parse_duration_seconds(value: Any) -> int:
    text = str(value or "").strip()
    if not re.match(r"^\d+[wdhms]?$", text):
        raise ValueError(
            f"Invalid duration '{value}'. Expected like '60', '2m', '1h'."
        )
    return cov2sec(text)


@click.command()
@add_options(CLI_OPTIONS)
def main(**params: Any) -> None:
    params["src_platform"] = params["src_platform"].lower()
    params["dst_platform"] = params["dst_platform"].lower()
    params["src_transport"] = params["src_transport"].lower()
    params["dst_transport"] = params["dst_transport"].lower()
    params["push_strategy"] = params["push_strategy"].lower()
    params["log_level"] = params["log_level"].upper()

    try:
        log_level = parse_log_level(params.get("log_level"))
    except ValueError as exc:
        raise click.BadParameter(str(exc))

    logging.basicConfig(level=log_level)

    params["dst_visibility"] = RepoVisibility.from_str(
        params["dst_visibility"]
    )
    config = MirrorConfig(**params)
    mirror = HubMirror(config)
    mirror.run()


if __name__ == "__main__":
    main()
