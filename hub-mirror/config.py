from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

from platforms import RepoVisibility

ALLOWED_PUSH_STRATEGIES = ("safe", "force", "no")


def cov2sec(value: str) -> int:
    unit_to_seconds = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }
    text = str(value).strip()
    if not text:
        raise ValueError("duration cannot be empty")
    unit = text[-1]
    if unit in unit_to_seconds:
        return int(text[:-1]) * unit_to_seconds[unit]
    return int(text)


@dataclass(frozen=True)
class RefsConfig:
    branches_include: List[str] = field(default_factory=lambda: ["*"])
    branches_exclude: List[str] = field(default_factory=list)
    tags_include: List[str] = field(default_factory=lambda: ["*"])
    tags_exclude: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RepoConfig:
    name: str
    dst_name: str = ""
    visibility: RepoVisibility = RepoVisibility.AUTO
    push_strategy: str = "safe"
    refs: RefsConfig = field(default_factory=RefsConfig)
    has_dst_name_override: bool = False
    has_visibility_override: bool = False
    has_push_strategy_override: bool = False
    has_refs_override: bool = False

    def __post_init__(self) -> None:
        repo_name = self.name.strip()
        if not repo_name:
            raise ValueError("repo name cannot be empty")
        object.__setattr__(self, "name", repo_name)

        dst_name = self.dst_name.strip() if self.dst_name else repo_name
        if not dst_name:
            raise ValueError("repo dst_name cannot be empty")
        object.__setattr__(self, "dst_name", dst_name)

        push_strategy = self.push_strategy.strip().lower()
        if push_strategy not in ALLOWED_PUSH_STRATEGIES:
            allowed = ", ".join(ALLOWED_PUSH_STRATEGIES)
            raise ValueError(
                f"Invalid push_strategy '{self.push_strategy}', "
                f"must be one of: {allowed}."
            )
        object.__setattr__(self, "push_strategy", push_strategy)


@dataclass(frozen=True)
class ReposConfig:
    static: List[RepoConfig] = field(default_factory=list)
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    mappings: Dict[str, str] = field(default_factory=dict)
    refs: RefsConfig = field(default_factory=RefsConfig)


def _as_str_list(
    value: Any,
    field_name: str,
    default: Optional[List[str]] = None,
) -> List[str]:
    if value is None:
        return list(default or [])
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings")

    result: List[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(
                f"{field_name}[{index}] must be a string, got {type(item)}"
            )
        stripped = item.strip()
        if not stripped:
            raise ValueError(f"{field_name}[{index}] cannot be empty")
        result.append(stripped)
    return result


def _parse_refs_config(value: Any, field_name: str = "refs") -> RefsConfig:
    if value is None:
        return RefsConfig()
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a mapping")

    branches = value.get("branches")
    tags = value.get("tags")

    if branches is None:
        branches = {}
    if tags is None:
        tags = {}

    if not isinstance(branches, dict):
        raise ValueError(f"{field_name}.branches must be a mapping")
    if not isinstance(tags, dict):
        raise ValueError(f"{field_name}.tags must be a mapping")

    return RefsConfig(
        branches_include=_as_str_list(
            branches.get("include"),
            f"{field_name}.branches.include",
            default=["*"],
        ),
        branches_exclude=_as_str_list(
            branches.get("exclude"),
            f"{field_name}.branches.exclude",
            default=[],
        ),
        tags_include=_as_str_list(
            tags.get("include"),
            f"{field_name}.tags.include",
            default=["*"],
        ),
        tags_exclude=_as_str_list(
            tags.get("exclude"),
            f"{field_name}.tags.exclude",
            default=[],
        ),
    )


def _parse_mappings(value: Any) -> Dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("mappings must be a string-to-string mapping")

    mappings: Dict[str, str] = {}
    for key, mapped_value in value.items():
        if not isinstance(key, str) or not isinstance(mapped_value, str):
            raise ValueError("mappings must be a string-to-string mapping")
        stripped_key = key.strip()
        stripped_value = mapped_value.strip()
        if not stripped_key or not stripped_value:
            raise ValueError("mappings entries cannot be empty")
        mappings[stripped_key] = stripped_value
    return mappings


def _parse_static(value: Any) -> List[RepoConfig]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("static must be a list")

    repos: List[RepoConfig] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            repos.append(RepoConfig(name=item))
            continue

        if not isinstance(item, dict):
            raise ValueError(
                f"static[{index}] must be a string or mapping, "
                f"got {type(item)}"
            )

        supported_keys = {
            "name",
            "dst_name",
            "visibility",
            "push_strategy",
            "refs",
        }
        unknown_keys = set(item.keys()) - supported_keys
        if unknown_keys:
            unknown = ", ".join(sorted(unknown_keys))
            raise ValueError(
                f"static[{index}] has unsupported keys: {unknown}"
            )

        name = item.get("name")
        if not isinstance(name, str):
            raise ValueError(f"static[{index}].name must be a string")

        dst_name = item.get("dst_name")
        if dst_name is not None and not isinstance(dst_name, str):
            raise ValueError(f"static[{index}].dst_name must be a string")

        try:
            visibility = RepoVisibility.from_str(
                item.get("visibility", RepoVisibility.AUTO)
            )
        except ValueError as exc:
            raise ValueError(f"static[{index}].visibility: {exc}") from exc

        push_strategy = item.get("push_strategy", "safe")
        if not isinstance(push_strategy, str):
            raise ValueError(
                f"static[{index}].push_strategy must be a string"
            )

        refs = RefsConfig()
        has_refs_override = "refs" in item
        if has_refs_override:
            refs = _parse_refs_config(
                item.get("refs"),
                f"static[{index}].refs",
            )

        repos.append(
            RepoConfig(
                name=name,
                dst_name=dst_name or name,
                visibility=visibility,
                push_strategy=push_strategy,
                refs=refs,
                has_dst_name_override="dst_name" in item,
                has_visibility_override="visibility" in item,
                has_push_strategy_override="push_strategy" in item,
                has_refs_override=has_refs_override,
            )
        )

    return repos


def parse_repos_config(raw: Optional[str]) -> ReposConfig:
    if raw is None or not raw.strip():
        return ReposConfig()

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse repos YAML: {exc}") from exc

    if parsed is None:
        return ReposConfig()

    if not isinstance(parsed, dict):
        raise ValueError("repos must be a YAML mapping")

    return ReposConfig(
        static=_parse_static(parsed.get("static")),
        include=_as_str_list(parsed.get("include"), "include", default=[]),
        exclude=_as_str_list(parsed.get("exclude"), "exclude", default=[]),
        mappings=_parse_mappings(parsed.get("mappings")),
        refs=_parse_refs_config(parsed.get("refs"), "refs"),
    )


def resolve_repo_config(
    repo_name: str,
    repos_config: ReposConfig,
    global_config: Any,
) -> RepoConfig:
    repo_override: Optional[RepoConfig] = next(
        (repo for repo in repos_config.static if repo.name == repo_name),
        None,
    )

    dst_name = repos_config.mappings.get(repo_name, repo_name)
    if repo_override:
        if repo_override.has_dst_name_override:
            dst_name = repo_override.dst_name
        elif dst_name == repo_name:
            dst_name = repo_override.dst_name

    visibility: RepoVisibility = RepoVisibility.from_str(
        getattr(global_config, "dst_visibility", RepoVisibility.AUTO)
    )
    if repo_override and repo_override.has_visibility_override:
        visibility = repo_override.visibility

    push_strategy = str(getattr(global_config, "push_strategy", "safe"))
    push_strategy = push_strategy.strip().lower()
    if push_strategy not in ALLOWED_PUSH_STRATEGIES:
        push_strategy = "safe"
    if repo_override and repo_override.has_push_strategy_override:
        push_strategy = repo_override.push_strategy

    refs = repos_config.refs
    has_refs_override = False
    if repo_override and repo_override.has_refs_override:
        refs = repo_override.refs
        has_refs_override = True

    return RepoConfig(
        name=repo_name,
        dst_name=dst_name,
        visibility=visibility,
        push_strategy=push_strategy,
        refs=refs,
        has_dst_name_override=bool(
            repo_override and repo_override.has_dst_name_override
        ),
        has_visibility_override=bool(
            repo_override and repo_override.has_visibility_override
        ),
        has_push_strategy_override=bool(
            repo_override and repo_override.has_push_strategy_override
        ),
        has_refs_override=has_refs_override,
    )
