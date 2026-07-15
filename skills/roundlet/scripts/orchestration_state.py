#!/usr/bin/env python3
"""Deterministic, repository-scoped state helpers for Roundlet.

This module deliberately has no third-party dependencies and performs no GitHub
operations.  The root Orchestrator owns connector calls; this module validates
their targets, records receipts, and guards the few local Git mutations that a
reviewed command-rule installation may permit.
"""

from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence
from urllib.parse import urlparse


SKILL_NAME = "roundlet"
SKILL_SOURCE_REPOSITORY = "ythdelmar68/roundlet"
DOCUMENTATION_ONLY_OPERATOR_GUIDE_PATH = "skills/roundlet/references/operator-guide.md"
STATE_DIRECTORY = Path(".codex-log/roundlet")
STATE_FILENAME = "state.json"
SUMMARY_FILENAME = "last-scope-summary.json"
MAILBOX_NAMES = {
    "github-context": "github-context.json",
    "worker-handoff": "worker-handoff.json",
    "supervisor-review": "supervisor-review.json",
}

GITHUB_OPERATION_FLAGS = {
    "create-draft-pr": "create_draft_prs",
    "mark-ready": "mark_ready_for_review",
    "merge-pr": "merge_commit_after_all_gates",
    "close-issue": "close_completed_sub_issues",
    "delete-remote-branch": "delete_proven_task_owned_resources",
}
MAX_GITHUB_MUTATION_RECEIPTS = 32

ROLE_ISOLATION_PROFILES = {
    "orchestrator": {
        "environment_type": "local",
        "forked": False,
        "filesystem_write": True,
        "github_connector": True,
    },
    "worker": {
        "environment_type": "worktree",
        "forked": False,
        "filesystem_write": True,
        "github_connector": False,
        "shell_network": False,
        "web_access": False,
        "gh_access": False,
    },
    "supervisor": {
        "environment_type": "local",
        "forked": False,
        "filesystem_write": False,
        "github_connector": False,
        "shell_network": False,
        "web_access": False,
        "gh_access": False,
    },
}

ROLE_NAMES = frozenset(ROLE_ISOLATION_PROFILES)
ROLE_MODEL_CONFIG_NAME = "role-models.json"
ROLE_MODEL_CONFIG_RELATIVE_PATH = Path("assets") / ROLE_MODEL_CONFIG_NAME
REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})
MODEL_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
# Canonical digest of the immutable policy-3 role profile.  Pinning the digest
# keeps migration compatible without carrying duplicate model literals in code.
POLICY3_ROLE_MODEL_SNAPSHOT_DIGEST = "be1680d41063b90e22fef16e5a207fa6aea59004624be5e5bfb08d8de07c77bf"

SCHEMA_VERSION = 5
PROTOCOL_VERSION = "3"
REVIEW_CONTRACT_VERSION = "3"
POLICY_VERSION = "4"
VERSION_KEYS = {"schema", "protocol", "review_contract", "policy"}
LOCAL_CLEANUP_KEYS = {
    "worktree_removed",
    "local_branch_deleted",
    "remote_branch_deleted",
    "worker_archived",
    "supervisors_archived",
}
MAX_STATE_BYTES = 1_048_576
MAX_MAILBOX_BYTES = 131_072
MAX_RECEIPT_BYTES = 65_536

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
CONTENT_DIGEST = re.compile(r"^[0-9a-f]{64}$")
OWNER_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH_NAME = re.compile(r"^(?![-/])(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9._/-]+(?<![./])$")

PHASES = {
    "idle",
    "scope-preflight",
    "selecting-task",
    "waiting-dependency",
    "worker-running",
    "draft-pr",
    "supervisor-running",
    "worker-repair",
    "pass-follow-up",
    "ready",
    "final-supervisor",
    "pre-merge",
    "merging",
    "closing-issue",
    "cleanup",
    "sync-base",
    "task-done",
    "maintenance-requested",
    "maintenance-draining",
    "paused-maintenance",
    "maintenance-validating",
    "resuming-maintenance",
    "scope-complete",
    "blocked",
}

TERMINAL_PHASES = {"scope-complete", "blocked"}
MAINTENANCE_ENTRY_PHASES = PHASES - {
    "maintenance-requested",
    "maintenance-draining",
    "paused-maintenance",
    "maintenance-validating",
    "resuming-maintenance",
    "scope-complete",
    "blocked",
}

LEGAL_TRANSITIONS = {
    "idle": {"scope-preflight"},
    "scope-preflight": {"selecting-task", "blocked"},
    "selecting-task": {"waiting-dependency", "worker-running", "scope-complete", "blocked"},
    "waiting-dependency": {"selecting-task", "blocked"},
    "worker-running": {"draft-pr", "blocked"},
    "draft-pr": {"supervisor-running", "blocked"},
    "supervisor-running": {"worker-repair", "pass-follow-up", "blocked"},
    "worker-repair": {"supervisor-running", "final-supervisor", "blocked"},
    "pass-follow-up": {"worker-repair", "ready", "blocked"},
    "ready": {"final-supervisor", "pre-merge", "blocked"},
    "final-supervisor": {"worker-repair", "ready", "blocked"},
    "pre-merge": {"worker-repair", "merging", "blocked"},
    "merging": {"closing-issue", "blocked"},
    "closing-issue": {"cleanup", "blocked"},
    "cleanup": {"sync-base", "blocked"},
    "sync-base": {"task-done", "blocked"},
    "task-done": {"selecting-task", "scope-complete", "blocked"},
    "maintenance-requested": {"maintenance-draining", "blocked"},
    "maintenance-draining": {"paused-maintenance", "blocked"},
    "paused-maintenance": {"maintenance-validating", "blocked"},
    "maintenance-validating": {"resuming-maintenance", "paused-maintenance", "blocked"},
    "resuming-maintenance": PHASES - {
        "idle",
        "scope-preflight",
        "maintenance-requested",
        "maintenance-draining",
        "paused-maintenance",
        "maintenance-validating",
        "resuming-maintenance",
    },
    "scope-complete": set(),
    "blocked": set(),
}

ALLOWED_OPERATION_KEYS = (
    "create_task_branches",
    "create_draft_prs",
    "mark_ready_for_review",
    "merge_commit_after_all_gates",
    "close_completed_sub_issues",
    "delete_proven_task_owned_resources",
)

FORBIDDEN_ACTIVATION_KEYS = {
    "repository",
    "repositories",
    "repository_url",
    "repo",
    "repo_url",
    "organization",
    "org",
    "account",
}


class RoundletError(RuntimeError):
    """Base error for fail-closed Roundlet operations."""


class ValidationError(RoundletError):
    """Input or persisted data violates the protocol."""


class ScopeError(RoundletError):
    """An operation would escape the activated current repository or scope."""


class TransitionError(RoundletError):
    """A requested state transition is illegal."""


class MailboxError(RoundletError):
    """A mailbox payload is stale, malformed, or ambiguous."""


class SelectionBlocked(RoundletError):
    """Dependency or ownership evidence requires the active scope to block."""


class GuardError(RoundletError):
    """A guarded Git operation cannot prove its safety conditions."""


class MigrationError(RoundletError):
    """A state document cannot be migrated without losing integrity."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z",
        value,
    ):
        raise ValidationError(f"{label} is malformed")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValidationError(f"{label} is malformed") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValidationError(f"{label} must use UTC")
    return parsed


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _validate_role_model_snapshot(snapshot: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Validate the only configurable portion of a role profile."""
    if not isinstance(snapshot, Mapping) or set(snapshot) != ROLE_NAMES:
        raise ValidationError("role model snapshot must contain exactly the three Roundlet roles")
    normalized: dict[str, dict[str, str]] = {}
    for role in sorted(ROLE_NAMES):
        profile = snapshot.get(role)
        if not isinstance(profile, Mapping) or set(profile) != {"model", "reasoning_effort"}:
            raise ValidationError(f"{role} model profile must contain exactly model and reasoning_effort")
        model = profile.get("model")
        effort = profile.get("reasoning_effort")
        if not isinstance(model, str) or not MODEL_ID.fullmatch(model):
            raise ValidationError(f"{role} model ID is malformed")
        if not isinstance(effort, str) or effort not in REASONING_EFFORTS:
            raise ValidationError(f"{role} reasoning effort is unsupported")
        normalized[role] = {"model": model, "reasoning_effort": effort}
    return normalized


def load_role_model_config(skill_root: str | os.PathLike[str]) -> dict[str, Any]:
    """Read the strict, dependency-free model configuration from one skill payload."""
    path = Path(skill_root).resolve() / ROLE_MODEL_CONFIG_RELATIVE_PATH
    try:
        content = path.read_bytes().decode("utf-8")
    except FileNotFoundError as exc:
        raise ValidationError("Roundlet role-model configuration is missing") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ValidationError("Roundlet role-model configuration is unreadable") from exc
    try:
        raw = json.loads(content, object_pairs_hook=_reject_duplicate_json_keys)
    except json.JSONDecodeError as exc:
        raise ValidationError("Roundlet role-model configuration is unreadable") from exc
    if not isinstance(raw, Mapping) or set(raw) != {"schema_version", "defaults", "legacy_profiles"}:
        raise ValidationError("role-model configuration has unknown or missing fields")
    if type(raw.get("schema_version")) is not int or raw.get("schema_version") != 1:
        raise ValidationError("role-model configuration schema is unsupported")
    defaults = _validate_role_model_snapshot(raw.get("defaults", {}))
    legacy_raw = raw.get("legacy_profiles")
    if not isinstance(legacy_raw, Mapping) or set(legacy_raw) != {"policy_3"}:
        raise ValidationError("role-model configuration legacy profiles are unsupported")
    legacy_profiles = {"policy_3": _validate_role_model_snapshot(legacy_raw["policy_3"])}
    canonical = {
        "schema_version": 1,
        "defaults": defaults,
        "legacy_profiles": legacy_profiles,
    }
    return {**canonical, "config_digest": digest_json(canonical)}


def load_stable_role_model_config(
    skill_root: str | os.PathLike[str], expected_digest: str
) -> dict[str, Any]:
    """Bind configuration bytes to one stable full-payload digest observation."""
    expected = require_content_digest(expected_digest, "expected installed digest")
    first_digest = skill_content_digest(skill_root)
    if first_digest != expected:
        raise GuardError("installed skill root does not match the declared digest")
    config = load_role_model_config(skill_root)
    if skill_content_digest(skill_root) != first_digest:
        raise GuardError("installed skill content changed while role configuration was read")
    return config


def role_model_snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    return digest_json(_validate_role_model_snapshot(snapshot))


def _reject_duplicate_json_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValidationError("role-model configuration contains duplicate JSON keys")
        value[key] = item
    return value


def fold_archive_digest(previous_digest: str, entries: Sequence[Mapping[str, Any]]) -> str:
    require_content_digest(previous_digest, "archive digest")
    return digest_json({"previous_digest": previous_digest, "entries": list(entries)})


def require_full_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not FULL_SHA.fullmatch(value):
        raise ValidationError(f"{label} must be a lowercase 40-character Git SHA")
    return value


def require_content_digest(value: Any, label: str = "installed_roundlet_digest") -> str:
    if not isinstance(value, str) or not CONTENT_DIGEST.fullmatch(value):
        raise ValidationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def validate_owner_actor(actor: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the connector-verified human actor that authorized this scope."""
    if not isinstance(actor, Mapping) or set(actor) != {
        "id",
        "login",
        "account_type",
        "verified_by_connector",
    }:
        raise ValidationError("owner actor requires exact connector identity evidence")
    actor_id = require_positive_issue(actor.get("id"), "owner actor ID")
    login = actor.get("login")
    if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", login):
        raise ValidationError("owner actor login is malformed")
    if actor.get("account_type") != "User" or actor.get("verified_by_connector") is not True:
        raise ScopeError("scope activation requires a connector-verified human owner actor")
    return {
        "id": actor_id,
        "login": login,
        "account_type": "User",
        "verified_by_connector": True,
    }


def validate_capability_preflight(preflight: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "verified_by_service": True,
        "per_thread_receipts": True,
        "worker_profile_enforceable": True,
        "supervisor_profile_enforceable": True,
        "connector_read_adapter_receipts": True,
    }
    if not isinstance(preflight, Mapping) or set(preflight) != set(required):
        raise ValidationError("capability preflight must contain the exact isolation proof fields")
    if any(preflight.get(key) is not expected for key, expected in required.items()):
        raise ScopeError("installed Codex surface cannot prove Worker/Supervisor isolation")
    return dict(required)


def validate_role_creation_receipt(
    receipt: Mapping[str, Any],
    *,
    role: str,
    thread_id: str,
    project_identity: str,
    parent_thread_id: str | None,
    role_model_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Require service-returned capability metadata; prompts are not capability proof."""
    isolation_profile = ROLE_ISOLATION_PROFILES.get(role)
    if isolation_profile is None:
        raise ValidationError("unknown Roundlet role capability profile")
    snapshot = _validate_role_model_snapshot(role_model_snapshot)
    required_keys = {
        "verified_by_service",
        "role",
        "thread_id",
        "model",
        "reasoning_effort",
        "environment_type",
        "project_identity",
        "parent_thread_id",
        "forked",
        "permission_profile",
        "filesystem_write",
        "github_connector",
        "shell_network",
        "web_access",
        "gh_access",
        "created_at",
    }
    if not isinstance(receipt, Mapping) or set(receipt) != required_keys:
        raise ValidationError(f"{role} requires an exact service capability receipt")
    if receipt.get("verified_by_service") is not True or receipt.get("role") != role:
        raise ScopeError(f"{role} creation was not verified by the Codex service")
    if receipt.get("thread_id") != thread_id or receipt.get("project_identity") != project_identity:
        raise ScopeError(f"{role} receipt is bound to another thread or project")
    if receipt.get("parent_thread_id") != parent_thread_id:
        raise ScopeError(f"{role} parent/fork identity is mismatched")
    for key, expected in {**isolation_profile, **snapshot[role]}.items():
        if receipt.get(key) != expected:
            raise ScopeError(f"{role} capability {key} is not isolated as required")
    permission = receipt.get("permission_profile")
    if role == "supervisor" and permission != "read-only":
        raise ScopeError("Supervisor permission profile must be read-only")
    if role == "worker" and permission not in {"workspace-write", "worktree-write"}:
        raise ScopeError("Worker permission profile must be task-worktree scoped")
    if role == "orchestrator" and permission not in {"workspace-write", "danger-full-access"}:
        raise ScopeError("Orchestrator permission profile cannot support the activated project")
    parse_utc_timestamp(receipt.get("created_at"), f"{role} creation receipt timestamp")
    return copy.deepcopy(dict(receipt))


def validate_versions(versions: Mapping[str, Any]) -> None:
    if not isinstance(versions, Mapping) or set(versions) != VERSION_KEYS:
        raise ValidationError("versions must contain exactly schema, protocol, review_contract, and policy")
    if versions.get("schema") != SCHEMA_VERSION:
        raise ValidationError(f"state schema must be {SCHEMA_VERSION}")
    for key in ("protocol", "review_contract", "policy"):
        if not isinstance(versions.get(key), str) or not versions[key]:
            raise ValidationError(f"versions.{key} must be a non-empty string")


def require_positive_issue(value: Any, label: str = "issue") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(f"{label} must be a positive integer")
    return value


def validate_branch_name(value: Any, label: str = "branch") -> str:
    if not isinstance(value, str) or not BRANCH_NAME.fullmatch(value):
        raise ValidationError(f"{label} is not a safe Git branch name")
    return value


def normalize_owner_name(value: str) -> str:
    value = value.strip()
    if value.endswith(".git"):
        value = value[:-4]
    if not OWNER_NAME.fullmatch(value):
        raise ValidationError("repository identity must be canonical owner/name")
    owner, name = value.split("/", 1)
    return f"{owner.lower()}/{name.lower()}"


def _origin_host_and_path(origin_url: str) -> tuple[str, str]:
    raw = origin_url.strip()
    scp = re.fullmatch(r"(?:(git)@)?([^/:]+):(.+)", raw)
    if scp and "://" not in raw:
        user, host, path = scp.groups()
        if user not in {None, "git"}:
            raise ValidationError("SCP-like origin user must be git")
        return host.casefold(), path
    parsed = urlparse(raw)
    if parsed.scheme not in {"https", "ssh", "git"}:
        raise ValidationError("origin URL scheme is unsupported or ambiguous")
    if not parsed.hostname or parsed.port is not None:
        raise ValidationError("origin URL host/port is missing or ambiguous")
    if parsed.scheme == "https" and (parsed.username is not None or parsed.password is not None):
        raise ValidationError("HTTPS origin must not embed credentials")
    if parsed.scheme in {"ssh", "git"} and parsed.username not in {None, "git"}:
        raise ValidationError("SSH origin user must be git")
    return parsed.hostname.casefold(), parsed.path


def owner_name_from_origin(
    origin_url: str,
    *,
    allowed_hosts: Sequence[str] = ("github.com",),
) -> str:
    """Parse HTTPS, ssh://, or SCP-like GitHub origin URLs without network I/O."""
    if not isinstance(origin_url, str) or not origin_url.strip():
        raise ValidationError("origin URL is missing")
    host, path = _origin_host_and_path(origin_url)
    allowed = {item.casefold() for item in allowed_hosts}
    if host not in allowed:
        raise ValidationError(f"origin host {host!r} is not an allowed GitHub host")
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) != 2:
        raise ValidationError("origin URL must identify exactly one owner/repository")
    return normalize_owner_name(f"{parts[0]}/{parts[1]}")


def origin_fingerprint(origin_url: str) -> str:
    return hashlib.sha256(origin_url.strip().encode("utf-8")).hexdigest()


class CommandRunner:
    """Small injectable subprocess adapter used only by local Git guards."""

    def run(self, args: Sequence[str], cwd: Path | None = None) -> str:
        try:
            completed = subprocess.run(
                list(args),
                cwd=str(cwd) if cwd else None,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            stderr = getattr(exc, "stderr", "") or ""
            raise GuardError(f"command failed: {' '.join(args)}: {stderr.strip()}") from exc
        return completed.stdout.strip()


@dataclass(frozen=True)
class RepositoryIdentity:
    owner_name: str
    repository_id: int | None
    git_root: str
    git_common_dir: str
    git_common_dir_fingerprint: str
    origin_fingerprint: str
    origin_push_fingerprint: str
    origin_host: str
    base_branch: str
    head_sha: str
    local_base_sha: str
    remote_base_sha: str
    current_branch: str | None = None
    base_branch_owner_worktree: str | None = None

    def scope_fields(self) -> dict[str, Any]:
        return {
            "owner_name": self.owner_name,
            "repository_id": self.repository_id,
            "git_common_dir_fingerprint": self.git_common_dir_fingerprint,
            "origin_fingerprint": self.origin_fingerprint,
            "origin_push_fingerprint": self.origin_push_fingerprint,
            "origin_host": self.origin_host,
            "base_branch": self.base_branch,
        }


def resolve_repository_identity(
    project_path: str | os.PathLike[str],
    base_branch: str,
    *,
    repository_id: int | None = None,
    require_synchronized: bool = True,
    runner: CommandRunner | None = None,
    allowed_origin_hosts: Sequence[str] = ("github.com",),
) -> RepositoryIdentity:
    """Resolve exactly one current Git repository from the active project path."""
    validate_branch_name(base_branch, "base_branch")
    if repository_id is not None:
        require_positive_issue(repository_id, "repository_id")
    run = runner or CommandRunner()
    project = Path(project_path).resolve()
    root = Path(run.run(["git", "rev-parse", "--show-toplevel"], project)).resolve()
    common_raw = run.run(["git", "rev-parse", "--git-common-dir"], root)
    common = (root / common_raw).resolve() if not os.path.isabs(common_raw) else Path(common_raw).resolve()
    fetch_urls = [
        item for item in run.run(["git", "remote", "get-url", "--all", "origin"], root).splitlines() if item
    ]
    push_urls = [
        item
        for item in run.run(["git", "remote", "get-url", "--push", "--all", "origin"], root).splitlines()
        if item
    ]
    if len(fetch_urls) != 1 or len(push_urls) != 1:
        raise GuardError("origin must have exactly one fetch URL and one push URL")
    origin = fetch_urls[0]
    push_origin = push_urls[0]
    owner_name = owner_name_from_origin(origin, allowed_hosts=allowed_origin_hosts)
    push_owner_name = owner_name_from_origin(push_origin, allowed_hosts=allowed_origin_hosts)
    if push_owner_name != owner_name:
        raise GuardError("origin fetch and push repository identities differ")
    origin_host, _ = _origin_host_and_path(origin)
    push_host, _ = _origin_host_and_path(push_origin)
    if push_host != origin_host:
        raise GuardError("origin fetch and push hosts differ")
    head = require_full_sha(run.run(["git", "rev-parse", "HEAD"], root), "HEAD")
    local_base = require_full_sha(
        run.run(["git", "rev-parse", f"refs/heads/{base_branch}"], root),
        "local base",
    )
    remote_base = require_full_sha(
        run.run(["git", "rev-parse", f"refs/remotes/origin/{base_branch}"], root),
        "remote base",
    )
    dirty = run.run(["git", "status", "--porcelain=v1"], root)
    if dirty:
        raise GuardError("the current-repository orchestration checkout is dirty")
    current_branch = run.run(["git", "branch", "--show-current"], root)
    base_owner: str | None = None
    if current_branch == "":
        worktrees = run.run(["git", "worktree", "list", "--porcelain"], root)
        for block in worktrees.split("\n\n"):
            lines = set(block.splitlines())
            worktree_lines = [line for line in lines if line.startswith("worktree ")]
            if f"branch refs/heads/{base_branch}" in lines and len(worktree_lines) == 1:
                base_owner = str(Path(worktree_lines[0].removeprefix("worktree ")).resolve())
                break
    if require_synchronized and len({head, local_base, remote_base}) != 1:
        raise GuardError("require HEAD == local base == origin/base before activation")
    return RepositoryIdentity(
        owner_name=owner_name,
        repository_id=repository_id,
        git_root=str(root),
        git_common_dir=str(common),
        git_common_dir_fingerprint=hashlib.sha256(str(common).encode("utf-8")).hexdigest(),
        origin_fingerprint=origin_fingerprint(origin),
        origin_push_fingerprint=origin_fingerprint(push_origin),
        origin_host=origin_host,
        base_branch=base_branch,
        head_sha=head,
        local_base_sha=local_base,
        remote_base_sha=remote_base,
        current_branch=current_branch,
        base_branch_owner_worktree=base_owner,
    )


def repository_identity_has_effective_base(identity: RepositoryIdentity) -> bool:
    if identity.current_branch == identity.base_branch:
        return len({identity.head_sha, identity.local_base_sha, identity.remote_base_sha}) == 1
    if identity.current_branch != "" or identity.head_sha != identity.remote_base_sha:
        return False
    if not identity.base_branch_owner_worktree:
        return False
    return Path(identity.base_branch_owner_worktree).resolve() != Path(identity.git_root).resolve()


def assert_repository_target(
    activation_repository: Mapping[str, Any],
    target_owner_name: str,
    *,
    target_repository_id: int | None = None,
) -> None:
    expected = normalize_owner_name(str(activation_repository.get("owner_name", "")))
    actual = normalize_owner_name(target_owner_name)
    if actual != expected:
        raise ScopeError(f"cross-repository target rejected: expected {expected}, got {actual}")
    expected_id = activation_repository.get("repository_id")
    if expected_id is not None:
        if target_repository_id is None:
            raise ScopeError("repository ID is required for this activated current repository")
        if expected_id != target_repository_id:
            raise ScopeError("repository ID does not match the activated current repository")


def normalize_activation_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the owner contract while rejecting every repository selector."""
    if not isinstance(request, Mapping):
        raise ValidationError("activation request must be an object")
    lowered = {str(key).lower() for key in request}
    forbidden = sorted(lowered & FORBIDDEN_ACTIVATION_KEYS)
    if forbidden:
        raise ScopeError(f"repository selectors are forbidden: {', '.join(forbidden)}")
    allowed_top = {"mode", "base_branch", "umbrella_issues", "authorize"}
    unknown = sorted(set(request) - allowed_top)
    if unknown:
        raise ValidationError(f"unknown activation fields: {', '.join(map(str, unknown))}")
    if request.get("mode") != "start":
        raise ValidationError("activation mode must be 'start'")
    base = validate_branch_name(request.get("base_branch"), "base_branch")
    umbrellas_raw = request.get("umbrella_issues")
    if not isinstance(umbrellas_raw, list) or not umbrellas_raw:
        raise ValidationError("umbrella_issues must be a non-empty ordered list")
    umbrellas = [require_positive_issue(item, "umbrella issue") for item in umbrellas_raw]
    if len(set(umbrellas)) != len(umbrellas):
        raise ValidationError("umbrella_issues must not contain duplicates")
    authorize = request.get("authorize")
    if not isinstance(authorize, Mapping):
        raise ValidationError("authorize must be an object")
    unknown_ops = sorted(set(authorize) - set(ALLOWED_OPERATION_KEYS))
    missing_ops = sorted(set(ALLOWED_OPERATION_KEYS) - set(authorize))
    if unknown_ops or missing_ops:
        details = []
        if unknown_ops:
            details.append(f"unknown: {', '.join(unknown_ops)}")
        if missing_ops:
            details.append(f"missing: {', '.join(missing_ops)}")
        raise ValidationError("authorize keys mismatch (" + "; ".join(details) + ")")
    operations: dict[str, bool] = {}
    for key in ALLOWED_OPERATION_KEYS:
        value = authorize[key]
        if not isinstance(value, bool):
            raise ValidationError(f"authorize.{key} must be boolean")
        operations[key] = value
    return {
        "mode": "start",
        "base_branch": base,
        "umbrella_issues": umbrellas,
        "authorize": operations,
    }


def compute_scope_digest(
    repository: Mapping[str, Any],
    base_branch: str,
    umbrella_issues: Sequence[int],
    allowed_operations: Mapping[str, bool],
    installed_roundlet_digest: str,
    *,
    owner_actor: Mapping[str, Any],
    capability_preflight: Mapping[str, Any],
    orchestrator_creation_receipt: Mapping[str, Any],
    role_model_snapshot: Mapping[str, Any],
    role_model_snapshot_digest: str,
    protocol_version: str = PROTOCOL_VERSION,
    policy_version: str = POLICY_VERSION,
) -> str:
    require_content_digest(installed_roundlet_digest)
    snapshot = _validate_role_model_snapshot(role_model_snapshot)
    if role_model_snapshot_digest != digest_json(snapshot):
        raise ScopeError("role model snapshot digest does not match the snapshot")
    normalized_repo = {
        "owner_name": normalize_owner_name(str(repository["owner_name"])),
        "repository_id": repository.get("repository_id"),
        "git_common_dir_fingerprint": repository["git_common_dir_fingerprint"],
        "origin_fingerprint": repository["origin_fingerprint"],
        "origin_push_fingerprint": repository["origin_push_fingerprint"],
        "origin_host": repository["origin_host"],
    }
    payload = {
        "repository": normalized_repo,
        "base_branch": validate_branch_name(base_branch, "base_branch"),
        "umbrella_issues": [require_positive_issue(item) for item in umbrella_issues],
        "allowed_operations": {key: bool(allowed_operations[key]) for key in ALLOWED_OPERATION_KEYS},
        "owner_actor": validate_owner_actor(owner_actor),
        "capability_preflight": validate_capability_preflight(capability_preflight),
        "orchestrator_creation_receipt_digest": digest_json(orchestrator_creation_receipt),
        "role_model_snapshot_digest": role_model_snapshot_digest,
        "installed_roundlet_digest": installed_roundlet_digest,
        "protocol_version": str(protocol_version),
        "policy_version": str(policy_version),
    }
    return digest_json(payload)


def compute_policy3_scope_digest(
    repository: Mapping[str, Any],
    base_branch: str,
    umbrella_issues: Sequence[int],
    allowed_operations: Mapping[str, bool],
    installed_roundlet_digest: str,
    *,
    owner_actor: Mapping[str, Any],
    capability_preflight: Mapping[str, Any],
    orchestrator_creation_receipt: Mapping[str, Any],
) -> str:
    """Preserve the exact schema-4/policy-3 scope algorithm for migration."""
    require_content_digest(installed_roundlet_digest)
    normalized_repo = {
        "owner_name": normalize_owner_name(str(repository["owner_name"])),
        "repository_id": repository.get("repository_id"),
        "git_common_dir_fingerprint": repository["git_common_dir_fingerprint"],
        "origin_fingerprint": repository["origin_fingerprint"],
        "origin_push_fingerprint": repository["origin_push_fingerprint"],
        "origin_host": repository["origin_host"],
    }
    return digest_json(
        {
            "repository": normalized_repo,
            "base_branch": validate_branch_name(base_branch, "base_branch"),
            "umbrella_issues": [require_positive_issue(item) for item in umbrella_issues],
            "allowed_operations": {key: bool(allowed_operations[key]) for key in ALLOWED_OPERATION_KEYS},
            "owner_actor": validate_owner_actor(owner_actor),
            "capability_preflight": validate_capability_preflight(capability_preflight),
            "orchestrator_creation_receipt_digest": digest_json(orchestrator_creation_receipt),
            "installed_roundlet_digest": installed_roundlet_digest,
            "protocol_version": "3",
            "policy_version": "3",
        }
    )


def validate_legacy_policy3_state(document: Mapping[str, Any], role_model_snapshot: Mapping[str, Any]) -> None:
    """Reject any tampering before deriving a schema-5 document from schema 4."""
    if not isinstance(document, Mapping):
        raise MigrationError("schema-4 migration input must be an object")
    if document.get("skill", {}).get("name") != SKILL_NAME:
        raise MigrationError("schema-4 state does not belong to Roundlet")
    if document.get("skill", {}).get("source_repository") != SKILL_SOURCE_REPOSITORY:
        raise MigrationError("schema-4 state has an untrusted source repository")
    if document.get("versions") != {
        "schema": 4,
        "protocol": "3",
        "review_contract": "3",
        "policy": "3",
    }:
        raise MigrationError("schema-4 state does not use the required policy-3 version contract")
    activation = document.get("activation")
    if not isinstance(activation, Mapping) or not isinstance(activation.get("repository"), Mapping):
        raise MigrationError("schema-4 activation identity is missing")
    repository = activation["repository"]
    try:
        snapshot = _validate_role_model_snapshot(role_model_snapshot)
        owner_actor = validate_owner_actor(activation.get("owner_actor", {}))
        capability_preflight = validate_capability_preflight(activation.get("capability_preflight", {}))
        validate_role_creation_receipt(
            activation.get("orchestrator_creation_receipt", {}),
            role="orchestrator",
            thread_id=str(activation.get("orchestrator_thread_id", "")),
            project_identity=str(repository.get("git_common_dir_fingerprint", "")),
            parent_thread_id=None,
            role_model_snapshot=snapshot,
        )
        task = document.get("task")
        if isinstance(task, Mapping):
            validate_role_creation_receipt(
                task.get("worker_creation_receipt", {}),
                role="worker",
                thread_id=str(task.get("worker_thread_id", "")),
                project_identity=str(repository.get("git_common_dir_fingerprint", "")),
                parent_thread_id=activation.get("orchestrator_thread_id"),
                role_model_snapshot=snapshot,
            )
        review = document.get("review", {})
        if not isinstance(review, Mapping):
            raise ValidationError("schema-4 review identity is missing")
        for receipt in review.get("supervisor_creation_receipts", []):
            validate_role_creation_receipt(
                receipt,
                role="supervisor",
                thread_id=str(receipt.get("thread_id", "")),
                project_identity=str(repository.get("git_common_dir_fingerprint", "")),
                parent_thread_id=activation.get("orchestrator_thread_id"),
                role_model_snapshot=snapshot,
            )
        expected_scope = compute_policy3_scope_digest(
            repository,
            activation.get("base_branch"),
            activation.get("umbrella_issues", []),
            activation.get("allowed_operations", {}),
            require_content_digest(document.get("skill", {}).get("content_digest")),
            owner_actor=owner_actor,
            capability_preflight=capability_preflight,
            orchestrator_creation_receipt=activation.get("orchestrator_creation_receipt", {}),
        )
    except RoundletError as exc:
        raise MigrationError("schema-4 state cannot prove its legacy activation scope") from exc
    if activation.get("scope_digest") != expected_scope:
        raise MigrationError("schema-4 legacy scope digest is mismatched")


def new_state(
    request: Mapping[str, Any],
    identity: RepositoryIdentity,
    *,
    activation_id: str,
    orchestrator_thread_id: str,
    installed_roundlet_digest: str,
    owner_actor: Mapping[str, Any],
    capability_preflight: Mapping[str, Any],
    orchestrator_creation_receipt: Mapping[str, Any],
    skill_root: str | os.PathLike[str],
    now: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_activation_request(request)
    if normalized["base_branch"] != identity.base_branch:
        raise ScopeError("requested base branch differs from the resolved synchronized base")
    if not repository_identity_has_effective_base(identity):
        raise GuardError("activation requires an exact checked-out or proven detached base identity")
    if not isinstance(activation_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{7,127}", activation_id):
        raise ValidationError("activation_id must be a stable 8-128 character identifier")
    if not isinstance(orchestrator_thread_id, str) or not orchestrator_thread_id.strip():
        raise ValidationError("orchestrator_thread_id is required")
    digest = require_content_digest(installed_roundlet_digest)
    config = load_stable_role_model_config(skill_root, digest)
    role_snapshot = config["defaults"]
    snapshot_digest = role_model_snapshot_digest(role_snapshot)
    timestamp = now or utc_now()
    normalized_owner = validate_owner_actor(owner_actor)
    normalized_preflight = validate_capability_preflight(capability_preflight)
    orchestrator_receipt = validate_role_creation_receipt(
        orchestrator_creation_receipt,
        role="orchestrator",
        thread_id=orchestrator_thread_id,
        project_identity=identity.git_common_dir_fingerprint,
        parent_thread_id=None,
        role_model_snapshot=role_snapshot,
    )
    repository = {
        **identity.scope_fields(),
        "git_root": identity.git_root,
        "git_common_dir": identity.git_common_dir,
    }
    scope_digest = compute_scope_digest(
        repository,
        identity.base_branch,
        normalized["umbrella_issues"],
        normalized["authorize"],
        digest,
        owner_actor=normalized_owner,
        capability_preflight=normalized_preflight,
        orchestrator_creation_receipt=orchestrator_receipt,
        role_model_snapshot=role_snapshot,
        role_model_snapshot_digest=snapshot_digest,
    )
    state = {
        "skill": {
            "name": SKILL_NAME,
            "source_repository": SKILL_SOURCE_REPOSITORY,
            "content_digest": digest,
        },
        "versions": {
            "schema": SCHEMA_VERSION,
            "protocol": PROTOCOL_VERSION,
            "review_contract": REVIEW_CONTRACT_VERSION,
            "policy": POLICY_VERSION,
        },
        "activation": {
            "id": activation_id,
            "orchestrator_thread_id": orchestrator_thread_id,
            "orchestrator_creation_receipt": orchestrator_receipt,
            "owner_actor": normalized_owner,
            "capability_preflight": normalized_preflight,
            "role_model_snapshot": role_snapshot,
            "role_model_snapshot_digest": snapshot_digest,
            "repository": repository,
            "base_branch": identity.base_branch,
            "base_sha": identity.head_sha,
            "umbrella_issues": normalized["umbrella_issues"],
            "allowed_operations": normalized["authorize"],
            "scope_digest": scope_digest,
            "started_at": timestamp,
        },
        "phase": "scope-preflight",
        "selection": None,
        "task": None,
        "review": {
            "round": 0,
            "last_result": None,
            "pass_identity": None,
            "current_supervisor_thread_id": None,
            "supervisor_thread_ids": [],
            "supervisor_creation_receipts": [],
            "unarchived_supervisor_thread_ids": [],
            "archived_supervisor_count": 0,
            "archived_supervisor_digest": "0" * 64,
            "last_supervisor_created_at": None,
        },
        "receipts": {},
        "github_mutations": {"pending": None, "receipts": {}},
        "receipt_archive": {"count": 0, "digest": "0" * 64},
        "mailbox_high_water": {kind: 0 for kind in sorted(MAILBOX_NAMES)},
        "maintenance": {
            "requested": False,
            "reason": None,
            "checkpoint_id": None,
            "previous_phase": None,
            "schedule_id": None,
            "schedule_state": None,
            "stored_versions": None,
            "pending_action": None,
            "resume_worker": False,
            "migrated_from_versions": None,
            "migration_receipt": None,
        },
        "retry": None,
        "blocker": None,
        "completed_tasks": [],
        "timestamps": {"created_at": timestamp, "updated_at": timestamp},
    }
    validate_state(state)
    return state


def validate_state(state: Mapping[str, Any]) -> None:
    if not isinstance(state, Mapping):
        raise ValidationError("state must be an object")
    try:
        if len(canonical_json(state).encode("utf-8")) > MAX_STATE_BYTES:
            raise ValidationError("state exceeds the durable artifact size limit")
    except (TypeError, ValueError) as exc:
        raise ValidationError("state must be canonical JSON data") from exc
    if state.get("skill", {}).get("name") != SKILL_NAME:
        raise ValidationError("state does not belong to Roundlet")
    if state.get("skill", {}).get("source_repository") != SKILL_SOURCE_REPOSITORY:
        raise ValidationError("state is not bound to the reviewed Roundlet source repository")
    versions = state.get("versions")
    validate_versions(versions)
    phase = state.get("phase")
    if phase not in PHASES:
        raise ValidationError(f"unknown state phase: {phase!r}")
    activation = state.get("activation")
    if not isinstance(activation, Mapping):
        raise ValidationError("state activation is missing")
    repository = activation.get("repository")
    if not isinstance(repository, Mapping):
        raise ValidationError("activation repository identity is missing")
    normalize_owner_name(str(repository.get("owner_name", "")))
    owner_actor = validate_owner_actor(activation.get("owner_actor", {}))
    capability_preflight = validate_capability_preflight(activation.get("capability_preflight", {}))
    role_snapshot = _validate_role_model_snapshot(activation.get("role_model_snapshot", {}))
    snapshot_digest = activation.get("role_model_snapshot_digest")
    if snapshot_digest != digest_json(role_snapshot):
        raise ScopeError("activation role-model snapshot digest is mismatched")
    validate_role_creation_receipt(
        activation.get("orchestrator_creation_receipt", {}),
        role="orchestrator",
        thread_id=str(activation.get("orchestrator_thread_id", "")),
        project_identity=str(repository.get("git_common_dir_fingerprint", "")),
        parent_thread_id=None,
        role_model_snapshot=role_snapshot,
    )
    digest = state.get("skill", {}).get("content_digest")
    require_content_digest(digest)
    try:
        expected_scope = compute_scope_digest(
            repository,
            activation.get("base_branch"),
            activation.get("umbrella_issues", []),
            activation.get("allowed_operations", {}),
            digest,
            owner_actor=owner_actor,
            capability_preflight=capability_preflight,
            orchestrator_creation_receipt=activation.get("orchestrator_creation_receipt", {}),
            role_model_snapshot=role_snapshot,
            role_model_snapshot_digest=str(snapshot_digest),
            protocol_version=str(versions.get("protocol")),
            policy_version=str(versions.get("policy")),
        )
    except (KeyError, TypeError) as exc:
        raise ValidationError("activation scope identity is incomplete") from exc
    if activation.get("scope_digest") != expected_scope:
        raise ScopeError("scope digest does not match the persisted activation")
    selection = state.get("selection")
    if selection is not None:
        validate_selection_receipt(state, selection)
    if phase == "scope-complete" and (
        not isinstance(selection, Mapping) or selection.get("status") != "complete"
    ):
        raise ValidationError("scope-complete requires a final complete refresh receipt")
    task = state.get("task")
    task_required = phase in {
        "worker-running",
        "draft-pr",
        "supervisor-running",
        "worker-repair",
        "pass-follow-up",
        "ready",
        "final-supervisor",
        "pre-merge",
        "merging",
        "closing-issue",
        "cleanup",
        "sync-base",
    }
    if task_required and not isinstance(task, Mapping):
        raise ValidationError(f"phase {phase} requires one active task")
    if isinstance(task, Mapping):
        require_positive_issue(task.get("umbrella_issue"), "task umbrella")
        require_positive_issue(task.get("issue"), "task issue")
        if task.get("umbrella_issue") not in activation.get("umbrella_issues", []):
            raise ScopeError("active task umbrella is outside the activation")
        validate_role_creation_receipt(
            task.get("worker_creation_receipt", {}),
            role="worker",
            thread_id=str(task.get("worker_thread_id", "")),
            project_identity=str(repository.get("git_common_dir_fingerprint", "")),
            parent_thread_id=activation.get("orchestrator_thread_id"),
            role_model_snapshot=role_snapshot,
        )
        if task.get("branch") is not None:
            branch = validate_branch_name(task["branch"])
            if not branch.startswith("codex/"):
                raise ScopeError("task branch must use the codex/ prefix")
        for key in ("base_sha", "candidate_sha"):
            if task.get(key) is not None:
                require_full_sha(task[key], f"task {key}")
        role = task.get("active_role")
        if role not in {None, "worker", "supervisor"}:
            raise ValidationError("only one Worker or Supervisor role turn may be active")
        cleanup = task.get("cleanup")
        if not isinstance(cleanup, Mapping) or set(cleanup) != LOCAL_CLEANUP_KEYS:
            raise ValidationError("task cleanup proof must contain the exact bounded cleanup flags")
        if any(not isinstance(cleanup[key], bool) for key in LOCAL_CLEANUP_KEYS):
            raise ValidationError("task cleanup proof flags must be boolean")
    review = state.get("review")
    if not isinstance(review, Mapping):
        raise ValidationError("review state is missing")
    thread_ids = review.get("supervisor_thread_ids")
    if not isinstance(thread_ids, list) or len(thread_ids) != len(set(thread_ids)):
        raise ValidationError("Supervisor thread identities must be unique")
    creation_receipts = review.get("supervisor_creation_receipts")
    if not isinstance(creation_receipts, list) or len(creation_receipts) > 64:
        raise ValidationError("Supervisor capability receipt ledger is malformed")
    receipt_thread_ids: list[str] = []
    for receipt in creation_receipts:
        if not isinstance(receipt, Mapping):
            raise ValidationError("Supervisor capability receipt is malformed")
        normalized = validate_role_creation_receipt(
            receipt,
            role="supervisor",
            thread_id=str(receipt.get("thread_id", "")),
            project_identity=str(repository.get("git_common_dir_fingerprint", "")),
            parent_thread_id=activation.get("orchestrator_thread_id"),
            role_model_snapshot=role_snapshot,
        )
        receipt_thread_ids.append(normalized["thread_id"])
    if receipt_thread_ids and receipt_thread_ids != thread_ids[-len(receipt_thread_ids) :]:
        raise ValidationError("Supervisor capability receipts differ from the freshness ledger")
    unarchived_thread_ids = review.get("unarchived_supervisor_thread_ids")
    if (
        not isinstance(unarchived_thread_ids, list)
        or len(unarchived_thread_ids) != len(set(unarchived_thread_ids))
        or any(thread_id not in thread_ids for thread_id in unarchived_thread_ids)
    ):
        raise ValidationError("unarchived Supervisor identities are malformed")
    archived_count = review.get("archived_supervisor_count")
    if (
        isinstance(archived_count, bool)
        or not isinstance(archived_count, int)
        or archived_count < 0
        or not CONTENT_DIGEST.fullmatch(str(review.get("archived_supervisor_digest", "")))
    ):
        raise ValidationError("archived Supervisor summary is malformed")
    review_round = review.get("round")
    if isinstance(review_round, bool) or not isinstance(review_round, int) or review_round < 0:
        raise ValidationError("Supervisor round must be a non-negative integer")
    if review_round != archived_count + len(unarchived_thread_ids):
        raise ValidationError("Supervisor round count differs from archived and active receipts")
    last_created_at = review.get("last_supervisor_created_at")
    if review.get("round") == 0:
        if last_created_at is not None:
            raise ValidationError("empty review history cannot have a Supervisor creation time")
    else:
        parse_utc_timestamp(
            last_created_at,
            "latest verified Supervisor creation receipt timestamp",
        )
    current_supervisor = review.get("current_supervisor_thread_id")
    if phase in {"supervisor-running", "final-supervisor"}:
        if not isinstance(task, Mapping) or task.get("active_role") != "supervisor":
            raise ValidationError(f"phase {phase} requires the Supervisor as the only active role")
        if not isinstance(current_supervisor, str) or current_supervisor not in thread_ids:
            raise ValidationError(f"phase {phase} requires the current fresh Supervisor thread")
    else:
        if isinstance(task, Mapping) and task.get("active_role") == "supervisor":
            raise ValidationError("Supervisor role is active outside a Supervisor phase")
        if current_supervisor is not None:
            raise ValidationError("current Supervisor thread is set outside a Supervisor phase")
    if phase in {"draft-pr", "pre-merge", "merging", "closing-issue", "cleanup", "sync-base"}:
        if isinstance(task, Mapping) and task.get("active_role") is not None:
            raise ValidationError(f"phase {phase} cannot have an active child role")
    if phase == "ready" and isinstance(task, Mapping) and task.get("active_role") not in {None, "worker"}:
        raise ValidationError("ready phase permits only the final Worker confirmation role")
    if phase in {"ready", "final-supervisor", "pre-merge", "merging", "closing-issue", "cleanup", "sync-base"}:
        if not isinstance(task, Mapping) or task.get("pr_ready") is not True:
            raise ValidationError(f"phase {phase} requires a confirmed ready PR")
    if phase == "pre-merge":
        if task.get("worker_ready_to_merge") is not True:
            raise ValidationError("pre-merge requires durable Worker READY_TO_MERGE")
    if phase in {"sync-base", "task-done"} and isinstance(task, Mapping):
        if not all(task["cleanup"].values()):
            raise ValidationError(f"phase {phase} requires complete task-owned cleanup proof")
    receipts = state.get("receipts")
    if not isinstance(receipts, Mapping) or len(receipts) > 128:
        raise ValidationError("receipts must be a bounded object")
    receipt_sequences: list[tuple[str, int, str]] = []
    for key, receipt in receipts.items():
        if not isinstance(key, str) or not isinstance(receipt, Mapping):
            raise ValidationError("receipt entries are malformed")
        if receipt.get("status") not in {"pending", "complete"}:
            raise ValidationError("receipt status must be pending or complete")
        if receipt.get("kind") not in MAILBOX_NAMES or not CONTENT_DIGEST.fullmatch(
            str(receipt.get("payload_digest", ""))
        ):
            raise ValidationError("receipt mailbox binding is malformed")
        if receipt.get("status") == "complete" and not isinstance(receipt.get("receipt"), Mapping):
            raise ValidationError("completed receipt payload is missing")
        try:
            receipt_sequences.append((receipt["kind"], mailbox_sequence(key), receipt["status"]))
        except MailboxError as exc:
            raise ValidationError(str(exc)) from exc
    receipt_archive = state.get("receipt_archive")
    if (
        not isinstance(receipt_archive, Mapping)
        or isinstance(receipt_archive.get("count"), bool)
        or not isinstance(receipt_archive.get("count"), int)
        or receipt_archive.get("count") < 0
        or not CONTENT_DIGEST.fullmatch(str(receipt_archive.get("digest", "")))
    ):
        raise ValidationError("receipt archive summary is malformed")
    high_water = state.get("mailbox_high_water")
    if not isinstance(high_water, Mapping) or set(high_water) != set(MAILBOX_NAMES):
        raise ValidationError("mailbox high-water state is malformed")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in high_water.values()):
        raise ValidationError("mailbox high-water values must be non-negative integers")
    seen_sequences: set[tuple[str, int]] = set()
    for kind, sequence, status in receipt_sequences:
        identity = (kind, sequence)
        if identity in seen_sequences:
            raise ValidationError("mailbox receipt sequences must be unique per kind")
        seen_sequences.add(identity)
        if sequence > high_water[kind]:
            raise ValidationError("mailbox receipt sequence exceeds its durable high-water mark")
        if status == "pending" and sequence != high_water[kind]:
            raise ValidationError("pending mailbox intent must be the latest sequence for its kind")
    github_mutations = state.get("github_mutations")
    if not isinstance(github_mutations, Mapping) or set(github_mutations) != {"pending", "receipts"}:
        raise ValidationError("GitHub mutation ledger is malformed")
    github_receipts = github_mutations.get("receipts")
    if not isinstance(github_receipts, Mapping) or len(github_receipts) > MAX_GITHUB_MUTATION_RECEIPTS:
        raise ValidationError("GitHub mutation receipt ledger is unbounded or malformed")
    for key, receipt in github_receipts.items():
        if (
            not isinstance(key, str)
            or not isinstance(receipt, Mapping)
            or receipt.get("status") != "complete"
            or receipt.get("operation") not in GITHUB_OPERATION_FLAGS
            or not CONTENT_DIGEST.fullmatch(str(receipt.get("target_digest", "")))
            or not isinstance(receipt.get("receipt"), Mapping)
        ):
            raise ValidationError("GitHub mutation receipt is malformed")
    pending_github = github_mutations.get("pending")
    if pending_github is not None and (
        not isinstance(pending_github, Mapping)
        or pending_github.get("operation") not in GITHUB_OPERATION_FLAGS
        or not CONTENT_DIGEST.fullmatch(str(pending_github.get("target_digest", "")))
        or not isinstance(pending_github.get("target"), Mapping)
    ):
        raise ValidationError("pending GitHub mutation intent is malformed")
    if isinstance(pending_github, Mapping):
        expected_phase = {
            "create-draft-pr": "worker-running",
            "mark-ready": "pass-follow-up",
            "merge-pr": "merging",
            "close-issue": "closing-issue",
            "delete-remote-branch": "cleanup",
        }[pending_github["operation"]]
        if (
            pending_github.get("activation_id") != activation.get("id")
            or pending_github.get("target_digest") != digest_json(pending_github["target"])
            or phase != expected_phase
            or activation.get("allowed_operations", {}).get(
                GITHUB_OPERATION_FLAGS[pending_github["operation"]]
            )
            is not True
        ):
            raise ValidationError("pending GitHub mutation intent is stale or unauthorized")
        parse_utc_timestamp(pending_github.get("started_at"), "GitHub mutation intent timestamp")
    maintenance = state.get("maintenance")
    if not isinstance(maintenance, Mapping) or not isinstance(maintenance.get("resume_worker"), bool):
        raise ValidationError("maintenance Worker continuation marker is malformed")
    if phase == "paused-maintenance" and (
        maintenance.get("schedule_state") != "paused"
        or not isinstance(maintenance.get("checkpoint_id"), str)
        or not isinstance(maintenance.get("schedule_id"), str)
    ):
        raise ValidationError("paused-maintenance requires the exact paused schedule checkpoint")
    pass_identity = review.get("pass_identity")
    if pass_identity is not None:
        if not isinstance(task, Mapping):
            raise ValidationError("PASS cannot exist without an active task")
        if pass_identity.get("candidate_sha") != task.get("candidate_sha"):
            raise ValidationError("PASS identity is stale for the current candidate")
        expected_pass_fields = {
            "activation_id": activation.get("id"),
            "repository": repository.get("owner_name"),
            "issue": task.get("issue"),
            "base_sha": task.get("base_sha"),
            "candidate_sha": task.get("candidate_sha"),
            "review_contract": versions.get("review_contract"),
        }
        for key, expected in expected_pass_fields.items():
            if pass_identity.get(key) != expected:
                raise ValidationError(f"PASS identity field {key} is stale")
        if pass_identity.get("supervisor_thread_id") not in thread_ids:
            raise ValidationError("PASS Supervisor identity is not in the bounded freshness ledger")
        if pass_identity.get("review_round") != review.get("round"):
            raise ValidationError("PASS review round is not the latest Supervisor round")


def atomic_write_json(
    path: str | os.PathLike[str],
    value: Any,
    *,
    max_bytes: int | None = None,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if max_bytes is not None and len(data.encode("utf-8")) > max_bytes:
        raise ValidationError(f"JSON artifact exceeds its {max_bytes}-byte limit")
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def read_json(path: str | os.PathLike[str], *, max_bytes: int | None = None) -> Any:
    try:
        source = Path(path)
        if max_bytes is not None and source.stat().st_size > max_bytes:
            raise ValidationError(f"JSON artifact exceeds its {max_bytes}-byte limit")
        with source.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except ValidationError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read valid JSON from {path}") from exc


class StateStore:
    def __init__(self, state_directory: str | os.PathLike[str]):
        self.directory = Path(state_directory)
        self.path = self.directory / STATE_FILENAME

    @contextmanager
    def single_writer(self):
        """Serialize one activation's read/intent/mutation/receipt critical section."""
        self.directory.mkdir(parents=True, exist_ok=True)
        lock_path = self.directory / ".single-writer.lock"
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def load(self) -> dict[str, Any]:
        state = read_json(self.path, max_bytes=MAX_STATE_BYTES)
        validate_state(state)
        return state

    def save(self, state: Mapping[str, Any]) -> None:
        mutable = copy.deepcopy(dict(state))
        mutable.setdefault("timestamps", {})["updated_at"] = utc_now()
        validate_state(mutable)
        atomic_write_json(self.path, mutable, max_bytes=MAX_STATE_BYTES)

    def initialize(self, state: Mapping[str, Any], *, replace_completed_scope: bool = False) -> None:
        replacement = copy.deepcopy(dict(state))
        if self.path.exists():
            existing = self.load()
            if not replace_completed_scope or existing.get("phase") != "scope-complete":
                raise ValidationError("state already exists; explicit reconciliation is required")
            if existing["activation"]["id"] == state.get("activation", {}).get("id"):
                raise ValidationError("next activation must use a fresh activation ID")
            old_activation = existing["activation"]
            new_activation = replacement.get("activation", {})
            if old_activation.get("orchestrator_thread_id") != new_activation.get("orchestrator_thread_id"):
                raise ScopeError("completed scope replacement must reuse the dedicated Orchestrator task")
            old_repo = old_activation.get("repository", {})
            new_repo = new_activation.get("repository", {})
            for key in ("owner_name", "repository_id", "git_common_dir_fingerprint"):
                if old_repo.get(key) != new_repo.get(key):
                    raise ScopeError("completed scope replacement cannot cross repository identity")
            replacement.setdefault("maintenance", {})["schedule_id"] = existing.get("maintenance", {}).get(
                "schedule_id"
            )
        self.save(replacement)

    def transition(self, new_phase: str, *, expected_phase: str | None = None) -> dict[str, Any]:
        state = self.load()
        transition_state(state, new_phase, expected_phase=expected_phase)
        self.save(state)
        return state

    def _compact_completed_receipts(
        self,
        state: MutableMapping[str, Any],
        *,
        keep: int = 32,
        target_bytes: int = MAX_STATE_BYTES * 3 // 4,
    ) -> None:
        protected_keys: set[str] = set()
        mailbox_directory = self.directory / "mailbox"
        for filename in MAILBOX_NAMES.values():
            path = mailbox_directory / filename
            if not path.exists():
                continue
            payload = read_json(path, max_bytes=MAX_MAILBOX_BYTES)
            if not isinstance(payload, Mapping) or not isinstance(payload.get("idempotency_key"), str):
                raise MailboxError("cannot compact receipts while a mailbox identity is malformed")
            protected_keys.add(payload["idempotency_key"])
        receipts = state.setdefault("receipts", {})
        completed = sorted(
            (
                (key, receipt)
                for key, receipt in receipts.items()
                if receipt.get("status") == "complete" and key not in protected_keys
            ),
            key=lambda item: (str(item[1].get("completed_at", "")), item[0]),
        )
        removable: list[tuple[str, Mapping[str, Any]]] = []
        remaining = list(completed)
        while remaining and (
            len(state.get("receipts", {})) > 96
            or len(remaining) > keep
            or len(canonical_json(state).encode("utf-8")) > target_bytes
        ):
            key, receipt = remaining.pop(0)
            removable.append((key, receipt))
            del receipts[key]
        if not removable:
            return
        archive = state.setdefault("receipt_archive", {"count": 0, "digest": "0" * 64})
        entries = [{"idempotency_key": key, **copy.deepcopy(dict(receipt))} for key, receipt in removable]
        archive["digest"] = fold_archive_digest(archive["digest"], entries)
        archive["count"] += len(entries)

    def begin_mailbox_intent(
        self,
        idempotency_key: str,
        kind: str,
        payload_digest: str,
    ) -> dict[str, Any]:
        if not isinstance(idempotency_key, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,200}", idempotency_key):
            raise ValidationError("idempotency key is malformed")
        if kind not in MAILBOX_NAMES or not CONTENT_DIGEST.fullmatch(payload_digest):
            raise ValidationError("mailbox intent kind or payload digest is malformed")
        state = self.load()
        receipts = state.setdefault("receipts", {})
        self._compact_completed_receipts(state)
        receipts = state["receipts"]
        existing = receipts.get(idempotency_key)
        intent = {
            "status": "pending",
            "kind": kind,
            "payload_digest": payload_digest,
            "started_at": utc_now(),
        }
        if existing is not None:
            if existing.get("kind") != kind or existing.get("payload_digest") != payload_digest:
                raise MailboxError("idempotency key is already bound to another mailbox payload")
            return state
        sequence = mailbox_sequence(idempotency_key)
        high_water = state["mailbox_high_water"][kind]
        if sequence <= high_water:
            raise MailboxError("mailbox idempotency key was already consumed and archived")
        if sequence != high_water + 1:
            raise MailboxError("mailbox idempotency sequence must be the next value for its kind")
        if any(
            receipt.get("kind") == kind and receipt.get("status") == "pending"
            for receipt in receipts.values()
        ):
            raise MailboxError("reconcile the pending mailbox intent before beginning another")
        receipts[idempotency_key] = intent
        state["mailbox_high_water"][kind] = sequence
        if len(receipts) > 128:
            raise ValidationError("receipt bound exceeded; compact before continuing")
        self.save(state)
        return state

    def complete_mailbox_intent(
        self,
        idempotency_key: str,
        kind: str,
        payload_digest: str,
        receipt: Mapping[str, Any],
        *,
        update: Callable[[MutableMapping[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        state = self.load()
        receipts = state.setdefault("receipts", {})
        existing = receipts.get(idempotency_key)
        if not isinstance(existing, Mapping):
            raise MailboxError("mailbox intent is missing before completion")
        if existing.get("kind") != kind or existing.get("payload_digest") != payload_digest:
            raise MailboxError("mailbox completion differs from its durable intent")
        normalized = copy.deepcopy(dict(receipt))
        if len(canonical_json(normalized).encode("utf-8")) > MAX_RECEIPT_BYTES:
            raise MailboxError("mutation receipt exceeds the bounded receipt limit")
        if existing.get("status") == "complete":
            if existing.get("receipt") != normalized:
                raise MailboxError("completed idempotency key has a different receipt")
            return state
        receipts[idempotency_key] = {
            "status": "complete",
            "kind": kind,
            "payload_digest": payload_digest,
            "receipt": normalized,
            "completed_at": utc_now(),
        }
        if update is not None:
            update(state)
        self._compact_completed_receipts(state)
        self.save(state)
        return state

    def migrate(
        self,
        *,
        activation_id: str,
        checkpoint_id: str,
        schedule_id: str,
        expected_installed_digest: str,
        expected_from_schema: int,
        target_version: int = SCHEMA_VERSION,
        skill_root: str | os.PathLike[str],
    ) -> dict[str, Any]:
        """Durably migrate only inside the exact reviewed paused-maintenance checkpoint."""
        with self.single_writer():
            original = read_json(self.path, max_bytes=MAX_STATE_BYTES)
            maintenance = original.get("maintenance", {})
            versions = original.get("versions", {})
            if original.get("phase") != "paused-maintenance":
                raise MigrationError("durable migration is permitted only in paused-maintenance")
            if original.get("activation", {}).get("id") != activation_id:
                raise MigrationError("migration activation identity is mismatched")
            if maintenance.get("checkpoint_id") != checkpoint_id:
                raise MigrationError("migration checkpoint identity is mismatched")
            if maintenance.get("schedule_id") != schedule_id or maintenance.get("schedule_state") != "paused":
                raise MigrationError("migration requires the exact paused schedule receipt")
            digest = require_content_digest(expected_installed_digest, "expected installed digest")
            if maintenance.get("installed_digest") != original.get("skill", {}).get("content_digest"):
                raise MigrationError("migration checkpoint does not bind the original installed digest")
            try:
                role_model_config = load_stable_role_model_config(skill_root, digest)
            except RoundletError as exc:
                raise MigrationError("migration skill root does not match the reviewed installed digest") from exc
            if maintenance.get("stored_versions") != versions:
                raise MigrationError("migration checkpoint versions differ from the stored document")
            if versions.get("schema") != expected_from_schema or target_version <= expected_from_schema:
                raise MigrationError("migration old/new schema contract is mismatched")
            if any(receipt.get("status") == "pending" for receipt in original.get("receipts", {}).values()):
                raise MigrationError("migration requires every mutation receipt to be reconciled")
            if original.get("github_mutations", {}).get("pending") is not None:
                raise MigrationError("migration requires every GitHub mutation to be reconciled")
            migrated = _migrate_state_document(
                original,
                target_version,
                role_model_config=role_model_config,
                installed_roundlet_digest=digest,
            )
            validate_state(migrated)
            atomic_write_json(self.path, migrated, max_bytes=MAX_STATE_BYTES)
            return migrated


def transition_state(
    state: MutableMapping[str, Any],
    new_phase: str,
    *,
    expected_phase: str | None = None,
    now: str | None = None,
) -> None:
    old = state.get("phase")
    if expected_phase is not None and old != expected_phase:
        raise TransitionError(f"expected phase {expected_phase}, found {old}")
    if new_phase not in PHASES:
        raise TransitionError(f"unknown phase: {new_phase}")
    if new_phase == "maintenance-requested" and old in MAINTENANCE_ENTRY_PHASES:
        pass
    elif new_phase not in LEGAL_TRANSITIONS.get(str(old), set()):
        raise TransitionError(f"illegal transition: {old} -> {new_phase}")
    if old == "cleanup" and new_phase == "sync-base":
        task = state.get("task")
        if not isinstance(task, Mapping) or not all(task.get("cleanup", {}).values()):
            raise TransitionError("cleanup must be durably complete before base synchronization")
    if old == "pre-merge" and new_phase == "merging":
        pending = state.get("github_mutations", {}).get("pending")
        if not isinstance(pending, Mapping) or pending.get("operation") != "merge-pr":
            raise TransitionError("merge requires a durable authorized connector intent")
    if new_phase == "scope-complete":
        selection = state.get("selection")
        if state.get("task") is not None:
            raise TransitionError("scope completion requires no owned task resources")
        if not isinstance(selection, Mapping) or selection.get("status") != "complete":
            raise TransitionError("scope completion requires a final complete refresh receipt")
        validate_selection_receipt(state, selection)
    state["phase"] = new_phase
    state.setdefault("timestamps", {})["updated_at"] = now or utc_now()


def assign_task(
    state: MutableMapping[str, Any],
    *,
    umbrella_issue: int,
    issue: int,
    branch: str,
    worktree: str,
    worker_thread_id: str,
    worker_creation_receipt: Mapping[str, Any],
    base_sha: str,
) -> None:
    if state.get("phase") != "selecting-task" or state.get("task") is not None:
        raise TransitionError("assign a task only from an unassigned selecting-task phase")
    umbrella = require_positive_issue(umbrella_issue, "umbrella issue")
    selected = require_positive_issue(issue, "selected issue")
    selection = state.get("selection")
    activation = state.get("activation", {})
    if activation.get("allowed_operations", {}).get("create_task_branches") is not True:
        raise ScopeError("Worker branch and task creation were not authorized")
    if not isinstance(selection, Mapping) or selection.get("status") != "selected":
        raise TransitionError("task assignment requires one durable selected receipt")
    validate_selection_receipt(state, selection)
    if selection.get("activation_id") != activation.get("id"):
        raise ScopeError("selection receipt belongs to another activation")
    if selection.get("selected_umbrella") != umbrella or selection.get("selected_issue") != selected:
        raise ScopeError("task assignment differs from the deterministic selection receipt")
    if selection.get("base_sha") != activation.get("base_sha"):
        raise ScopeError("selection receipt base is stale for the activation")
    if umbrella not in state["activation"]["umbrella_issues"]:
        raise ScopeError("selected umbrella is not authorized")
    branch_name = validate_branch_name(branch)
    if not branch_name.startswith("codex/"):
        raise ScopeError("Worker branch must use the codex/ prefix")
    base = require_full_sha(base_sha, "base_sha")
    if base != selection.get("base_sha"):
        raise ScopeError("Worker base differs from the deterministic selection receipt")
    if not all(isinstance(item, str) and item for item in (worktree, worker_thread_id)):
        raise ValidationError("worktree and Worker thread identities are required")
    worker_receipt = validate_role_creation_receipt(
        worker_creation_receipt,
        role="worker",
        thread_id=worker_thread_id,
        project_identity=state["activation"]["repository"]["git_common_dir_fingerprint"],
        parent_thread_id=state["activation"]["orchestrator_thread_id"],
        role_model_snapshot=state["activation"]["role_model_snapshot"],
    )
    state["task"] = {
        "umbrella_issue": umbrella,
        "issue": selected,
        "branch": branch_name,
        "worktree": str(Path(worktree).resolve()),
        "worker_thread_id": worker_thread_id,
        "worker_creation_receipt": worker_receipt,
        "base_sha": base,
        "candidate_sha": None,
        "pr_number": None,
        "pr_url": None,
        "draft_pr_receipt": None,
        "active_role": "worker",
        "merge_sha": None,
        "merged_head_sha": None,
        "merge_receipt": None,
        "issue_close_receipt": None,
        "pr_ready": False,
        "worker_ready_to_merge": False,
        "cleanup": {key: False for key in sorted(LOCAL_CLEANUP_KEYS)},
    }
    state["review"] = {
        "round": 0,
        "last_result": None,
        "pass_identity": None,
        "current_supervisor_thread_id": None,
        "supervisor_thread_ids": [],
        "supervisor_creation_receipts": [],
        "unarchived_supervisor_thread_ids": [],
        "archived_supervisor_count": 0,
        "archived_supervisor_digest": "0" * 64,
        "last_supervisor_created_at": None,
    }
    transition_state(state, "worker-running")


def set_candidate(state: MutableMapping[str, Any], candidate_sha: str, *, clean: bool) -> None:
    task = state.get("task")
    if not isinstance(task, MutableMapping):
        raise TransitionError("candidate requires an active task")
    if state.get("phase") not in {"worker-running", "worker-repair", "pass-follow-up"}:
        raise TransitionError("candidate handoff is not accepted in this phase")
    if task.get("active_role") != "worker":
        raise TransitionError("candidate handoff requires the active Worker")
    if not clean:
        raise GuardError("candidate worktree must be clean before handoff")
    candidate = require_full_sha(candidate_sha, "candidate_sha")
    changed = task.get("candidate_sha") != candidate
    if changed:
        task["candidate_sha"] = candidate
        state["review"]["pass_identity"] = None
        state["review"]["last_result"] = None
        task["worker_ready_to_merge"] = False
    task["active_role"] = None
    if changed and state.get("phase") == "pass-follow-up":
        transition_state(state, "worker-repair")


def begin_supervisor(
    state: MutableMapping[str, Any],
    thread_id: str,
    *,
    creation_receipt: Mapping[str, Any],
    final: bool = False,
) -> None:
    task = state.get("task")
    if not isinstance(task, MutableMapping) or not task.get("candidate_sha"):
        raise TransitionError("Supervisor requires an immutable candidate")
    if task.get("active_role") is not None:
        raise TransitionError("another role turn is already active")
    if not isinstance(thread_id, str) or not thread_id:
        raise ValidationError("Supervisor thread ID is required")
    phase = state.get("phase")
    if final:
        if phase not in {"ready", "worker-repair"} or task.get("pr_ready") is not True:
            raise TransitionError("final Supervisor requires a ready PR candidate")
    elif phase not in {"draft-pr", "worker-repair"} or task.get("pr_ready") is True:
        raise TransitionError("initial Supervisor requires a draft PR candidate")
    review = state["review"]
    if review.get("unarchived_supervisor_thread_ids"):
        raise TransitionError("archive the previous Supervisor before creating another")
    if thread_id in review["supervisor_thread_ids"]:
        raise ValidationError("every Supervisor review must use a fresh thread")
    expected_creation = {
        "activation_id": state["activation"]["id"],
        "issue": task["issue"],
        "generation": review["round"] + 1,
        "created": True,
    }
    if not isinstance(creation_receipt, Mapping) or set(creation_receipt) != set(expected_creation) | {"service_receipt"}:
        raise ValidationError("Supervisor requires an exact externally verified fresh-task creation receipt")
    if any(creation_receipt.get(key) != value for key, value in expected_creation.items()):
        raise ValidationError("Supervisor fresh-task creation receipt identity is mismatched")
    service_receipt = validate_role_creation_receipt(
        creation_receipt.get("service_receipt", {}),
        role="supervisor",
        thread_id=thread_id,
        project_identity=state["activation"]["repository"]["git_common_dir_fingerprint"],
        parent_thread_id=state["activation"]["orchestrator_thread_id"],
        role_model_snapshot=state["activation"]["role_model_snapshot"],
    )
    created_at = service_receipt.get("created_at")
    created_time = parse_utc_timestamp(created_at, "Supervisor creation receipt timestamp")
    previous_created_at = review.get("last_supervisor_created_at")
    if isinstance(previous_created_at, str):
        previous_time = parse_utc_timestamp(
            previous_created_at,
            "previous Supervisor creation receipt timestamp",
        )
        if created_time <= previous_time:
            raise ValidationError("Supervisor creation receipt is not newer than the previous fresh task")
    review["supervisor_thread_ids"].append(thread_id)
    if len(review["supervisor_thread_ids"]) > 64:
        review["supervisor_thread_ids"] = review["supervisor_thread_ids"][-64:]
    review["supervisor_creation_receipts"].append(service_receipt)
    if len(review["supervisor_creation_receipts"]) > 64:
        review["supervisor_creation_receipts"] = review["supervisor_creation_receipts"][-64:]
    review["unarchived_supervisor_thread_ids"].append(thread_id)
    review["current_supervisor_thread_id"] = thread_id
    review["round"] += 1
    review["last_supervisor_created_at"] = created_at
    task["active_role"] = "supervisor"
    desired = "final-supervisor" if final else "supervisor-running"
    if state["phase"] != desired:
        transition_state(state, desired)


def accept_supervisor_result(
    state: MutableMapping[str, Any],
    *,
    thread_id: str,
    candidate_sha: str,
    result: str,
    non_blocking_items: Sequence[str] | None = None,
) -> None:
    if state.get("phase") not in {"supervisor-running", "final-supervisor"}:
        raise TransitionError("Supervisor result is not expected in this phase")
    task = state.get("task")
    review = state.get("review")
    if not isinstance(task, MutableMapping) or not isinstance(review, MutableMapping):
        raise ValidationError("active task/review state is missing")
    if thread_id != review.get("current_supervisor_thread_id"):
        raise MailboxError("Supervisor result source thread does not match")
    candidate = require_full_sha(candidate_sha, "Supervisor candidate_sha")
    if candidate != task.get("candidate_sha"):
        raise MailboxError("stale Supervisor candidate identity")
    if result not in {"PASS", "FINDINGS"}:
        raise ValidationError("Supervisor result must be exact PASS or FINDINGS")
    task["active_role"] = None
    review["current_supervisor_thread_id"] = None
    review["last_result"] = result
    was_final = state["phase"] == "final-supervisor"
    if result == "FINDINGS":
        review["pass_identity"] = None
        task["active_role"] = "worker"
        transition_state(state, "worker-repair")
        return
    items = list(non_blocking_items or [])
    review["pass_identity"] = {
        "activation_id": state["activation"]["id"],
        "repository": state["activation"]["repository"]["owner_name"],
        "issue": task["issue"],
        "base_sha": task["base_sha"],
        "candidate_sha": candidate,
        "supervisor_thread_id": thread_id,
        "review_round": review["round"],
        "review_contract": state["versions"]["review_contract"],
        "non_blocking_items": items,
        "accepted_at": utc_now(),
        "stage": "final" if was_final else "initial",
    }
    if was_final:
        task["active_role"] = "worker"
        transition_state(state, "ready")
    else:
        task["active_role"] = "worker"
        transition_state(state, "pass-follow-up")


def record_supervisor_archived(
    state: MutableMapping[str, Any],
    *,
    supervisor_thread_id: str,
) -> None:
    review = state.get("review")
    if not isinstance(review, MutableMapping):
        raise ValidationError("review state is missing")
    if review.get("current_supervisor_thread_id") is not None:
        raise TransitionError("the currently active Supervisor cannot be archived")
    thread_ids = review.get("supervisor_thread_ids")
    unarchived = review.get("unarchived_supervisor_thread_ids")
    if (
        not isinstance(thread_ids, list)
        or not isinstance(unarchived, list)
        or supervisor_thread_id not in unarchived
    ):
        raise ScopeError("Supervisor archival receipt does not match an unarchived review thread")
    review["unarchived_supervisor_thread_ids"] = [
        thread_id for thread_id in unarchived if thread_id != supervisor_thread_id
    ]
    review["archived_supervisor_digest"] = fold_archive_digest(
        review["archived_supervisor_digest"],
        [{"thread_id": supervisor_thread_id}],
    )
    review["archived_supervisor_count"] += 1


def _validate_exact_pr_identity(state: Mapping[str, Any], live: Mapping[str, Any]) -> None:
    task = state.get("task") or {}
    activation = state.get("activation") or {}
    repository = activation.get("repository", {})
    for name_key, id_key in (
        ("repository", "repository_id"),
        ("base_repository", "base_repository_id"),
        ("head_repository", "head_repository_id"),
    ):
        assert_repository_target(
            repository,
            str(live.get(name_key, "")),
            target_repository_id=live.get(id_key),
        )
    if live.get("base_branch") != activation.get("base_branch"):
        raise ScopeError("PR base branch differs from the activated base branch")
    if live.get("head_ref") != task.get("branch"):
        raise ScopeError("PR head ref differs from the task-owned branch")
    if live.get("base_sha") != task.get("base_sha"):
        raise ScopeError("PR base SHA differs from the selected task")
    if live.get("head_sha") != task.get("candidate_sha"):
        raise ScopeError("PR head SHA differs from the reviewed candidate")


def _require_pending_github_intent(
    state: Mapping[str, Any],
    *,
    intent_key: str,
    operation: str,
) -> Mapping[str, Any]:
    pending = state.get("github_mutations", {}).get("pending")
    if (
        not isinstance(pending, Mapping)
        or pending.get("idempotency_key") != intent_key
        or pending.get("operation") != operation
    ):
        raise TransitionError(f"{operation} receipt requires its durable gateway intent")
    return pending


def begin_github_mutation_intent(
    state: MutableMapping[str, Any],
    *,
    operation: str,
    idempotency_key: str,
    target: Mapping[str, Any],
) -> None:
    if operation not in GITHUB_OPERATION_FLAGS:
        raise ValidationError("unknown GitHub mutation operation")
    if not isinstance(idempotency_key, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,200}", idempotency_key):
        raise ValidationError("GitHub mutation idempotency key is malformed")
    if not isinstance(target, Mapping):
        raise ValidationError("GitHub mutation target is missing")
    ledger = state.get("github_mutations")
    if not isinstance(ledger, MutableMapping):
        raise ValidationError("GitHub mutation ledger is missing")
    target_digest = digest_json(target)
    completed = ledger.get("receipts", {}).get(idempotency_key)
    if completed is not None:
        if completed.get("operation") != operation or completed.get("target_digest") != target_digest:
            raise MailboxError("GitHub mutation key is bound to another exact target")
        return
    if len(ledger.get("receipts", {})) >= MAX_GITHUB_MUTATION_RECEIPTS:
        raise ValidationError("compact the completed task before another GitHub mutation")
    if ledger.get("pending") is not None:
        raise MailboxError("reconcile the pending GitHub mutation before another connector write")
    flag = GITHUB_OPERATION_FLAGS[operation]
    if state["activation"]["allowed_operations"].get(flag) is not True:
        raise ScopeError(f"GitHub operation {operation} was not authorized")
    task = state.get("task")
    if not isinstance(task, Mapping):
        raise TransitionError("GitHub mutation requires one active selected task")
    phase = state.get("phase")
    expected_phases = {
        "create-draft-pr": "worker-running",
        "mark-ready": "pass-follow-up",
        "merge-pr": "pre-merge",
        "close-issue": "closing-issue",
        "delete-remote-branch": "cleanup",
    }
    if phase != expected_phases[operation]:
        raise TransitionError(f"{operation} is not permitted from phase {phase}")
    if operation in {"create-draft-pr", "mark-ready", "merge-pr"}:
        _validate_exact_pr_identity(state, target)
        if operation != "create-draft-pr":
            if target.get("pr_number") != task.get("pr_number") or target.get("pr_url") != task.get("pr_url"):
                raise ScopeError("GitHub mutation PR differs from the active task")
        if operation == "merge-pr":
            assert_premerge_gates(state, target)
    elif operation == "close-issue":
        assert_repository_target(
            state["activation"]["repository"],
            str(target.get("repository", "")),
            target_repository_id=target.get("repository_id"),
        )
        if target.get("issue") != task.get("issue") or not isinstance(task.get("merge_receipt"), Mapping):
            raise ScopeError("issue-close target is not the exact merged selected issue")
    else:
        assert_repository_target(
            state["activation"]["repository"],
            str(target.get("repository", "")),
            target_repository_id=target.get("repository_id"),
        )
        if target.get("branch") != task.get("branch"):
            raise ScopeError("remote deletion target is not the task-owned branch")
    ledger["pending"] = {
        "idempotency_key": idempotency_key,
        "operation": operation,
        "activation_id": state["activation"]["id"],
        "target": copy.deepcopy(dict(target)),
        "target_digest": target_digest,
        "started_at": utc_now(),
    }
    if operation == "merge-pr":
        transition_state(state, "merging")


def complete_github_mutation_intent(
    state: MutableMapping[str, Any],
    *,
    idempotency_key: str,
    receipt: Mapping[str, Any],
) -> None:
    ledger = state.get("github_mutations")
    if not isinstance(ledger, MutableMapping):
        raise ValidationError("GitHub mutation ledger is missing")
    pending = ledger.get("pending")
    if not isinstance(pending, Mapping) or pending.get("idempotency_key") != idempotency_key:
        raise MailboxError("GitHub mutation completion has no matching durable intent")
    if not isinstance(receipt, Mapping) or not receipt:
        raise MailboxError("connector live-state receipt is missing")
    operation = str(pending["operation"])
    kwargs = copy.deepcopy(dict(receipt))
    kwargs["intent_key"] = idempotency_key
    if operation == "create-draft-pr":
        record_draft_pr(state, **kwargs)
    elif operation == "mark-ready":
        record_pr_ready(state, **kwargs)
    elif operation == "merge-pr":
        record_merge_receipt(state, **kwargs)
    elif operation == "close-issue":
        record_issue_close_receipt(state, **kwargs)
    elif operation == "delete-remote-branch":
        record_remote_branch_deleted(state, **kwargs)
    else:
        raise ValidationError("unknown pending GitHub operation")
    receipts = ledger.setdefault("receipts", {})
    if len(receipts) >= MAX_GITHUB_MUTATION_RECEIPTS:
        raise ValidationError("GitHub mutation receipt bound exceeded before task compaction")
    receipts[idempotency_key] = {
        "status": "complete",
        "operation": operation,
        "target_digest": pending["target_digest"],
        "receipt": copy.deepcopy(dict(receipt)),
        "completed_at": utc_now(),
    }
    ledger["pending"] = None


def execute_github_mutation(
    state_store: StateStore,
    *,
    operation: str,
    idempotency_key: str,
    target: Mapping[str, Any],
    mutate: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    reconcile: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
) -> Mapping[str, Any]:
    """The only connector-write gateway: authorize, intent, mutate, live receipt, advance."""
    with state_store.single_writer():
        state = state_store.load()
        existing = state.get("github_mutations", {}).get("receipts", {}).get(idempotency_key)
        if isinstance(existing, Mapping):
            if existing.get("operation") != operation or existing.get("target_digest") != digest_json(target):
                raise MailboxError("GitHub mutation key is bound to another exact target")
            return existing["receipt"]
        pending = state.get("github_mutations", {}).get("pending")
        if pending is None:
            begin_github_mutation_intent(
                state,
                operation=operation,
                idempotency_key=idempotency_key,
                target=target,
            )
            state_store.save(state)
            result = mutate(target)
        else:
            if (
                pending.get("idempotency_key") != idempotency_key
                or pending.get("operation") != operation
                or pending.get("target_digest") != digest_json(target)
            ):
                raise MailboxError("another GitHub mutation is pending reconciliation")
            if reconcile is None:
                raise MailboxError("pending GitHub mutation requires connector reconciliation")
            result = reconcile(target)
            if result is None:
                raise MailboxError("connector mutation identity remains ambiguous")
        if not isinstance(result, Mapping):
            raise MailboxError("connector mutation did not return live-state evidence")
        complete_github_mutation_intent(state, idempotency_key=idempotency_key, receipt=result)
        state_store.save(state)
        return result


def record_pr_ready(
    state: MutableMapping[str, Any],
    *,
    intent_key: str,
    repository: str,
    repository_id: int | None,
    pr_number: int,
    pr_url: str,
    pr_state: str,
    draft: bool,
    base_repository: str,
    base_repository_id: int | None,
    base_branch: str,
    base_sha: str,
    head_repository: str,
    head_repository_id: int | None,
    head_ref: str,
    head_sha: str,
) -> None:
    _require_pending_github_intent(state, intent_key=intent_key, operation="mark-ready")
    if state.get("phase") != "pass-follow-up":
        raise TransitionError("PR readiness is expected only after initial PASS follow-up")
    task = state.get("task")
    review = state.get("review")
    if not isinstance(task, MutableMapping) or not isinstance(review, MutableMapping):
        raise ValidationError("active task/review is missing")
    if task.get("active_role") is not None:
        raise TransitionError("Worker PASS follow-up handoff is not complete")
    if state["activation"]["allowed_operations"].get("mark_ready_for_review") is not True:
        raise ScopeError("ready-for-review transition was not authorized")
    assert_repository_target(
        state["activation"]["repository"],
        repository,
        target_repository_id=repository_id,
    )
    if require_positive_issue(pr_number, "pr_number") != task.get("pr_number"):
        raise ScopeError("ready receipt PR does not match the selected task")
    live_identity = {
        "repository": repository,
        "repository_id": repository_id,
        "base_repository": base_repository,
        "base_repository_id": base_repository_id,
        "base_branch": base_branch,
        "base_sha": base_sha,
        "head_repository": head_repository,
        "head_repository_id": head_repository_id,
        "head_ref": head_ref,
        "head_sha": head_sha,
    }
    _validate_exact_pr_identity(state, live_identity)
    if pr_url != task.get("pr_url") or not isinstance(pr_state, str) or pr_state.casefold() != "open":
        raise GuardError("ready receipt requires the exact open PR live state")
    if draft is not False:
        raise GuardError("ready receipt requires connector read-back proving draft=false")
    head = require_full_sha(head_sha, "ready head_sha")
    pass_identity = review.get("pass_identity")
    if (
        review.get("last_result") != "PASS"
        or not isinstance(pass_identity, Mapping)
        or pass_identity.get("candidate_sha") != head
        or pass_identity.get("stage") != "initial"
        or task.get("candidate_sha") != head
    ):
        raise GuardError("ready transition requires an unchanged initial Supervisor PASS")
    task["pr_ready"] = True
    transition_state(state, "ready")


def record_worker_ready_to_merge(
    state: MutableMapping[str, Any],
    *,
    worker_thread_id: str,
    head_sha: str,
    clean: bool,
) -> None:
    if state.get("phase") != "ready":
        raise TransitionError("Worker merge-readiness is expected only after final PASS")
    task = state.get("task")
    review = state.get("review")
    if not isinstance(task, MutableMapping) or not isinstance(review, Mapping):
        raise ValidationError("active task/review is missing")
    if task.get("active_role") != "worker" or worker_thread_id != task.get("worker_thread_id"):
        raise ScopeError("merge-readiness must come from the same active Worker")
    if not clean:
        raise GuardError("Worker worktree must be clean for merge-readiness")
    head = require_full_sha(head_sha, "Worker READY_TO_MERGE head")
    pass_identity = review.get("pass_identity")
    if (
        review.get("last_result") != "PASS"
        or not isinstance(pass_identity, Mapping)
        or pass_identity.get("stage") != "final"
        or pass_identity.get("candidate_sha") != head
        or task.get("candidate_sha") != head
    ):
        raise GuardError("Worker readiness requires an unchanged final Supervisor PASS")
    task["worker_ready_to_merge"] = True
    task["active_role"] = None
    transition_state(state, "pre-merge")


def record_draft_pr(
    state: MutableMapping[str, Any],
    *,
    intent_key: str,
    repository: str,
    repository_id: int | None,
    issue: int,
    pr_number: int,
    pr_url: str,
    pr_state: str,
    draft: bool,
    base_repository: str,
    base_repository_id: int | None,
    base_branch: str,
    base_sha: str,
    head_repository: str,
    head_repository_id: int | None,
    head_ref: str,
    head_sha: str,
) -> None:
    _require_pending_github_intent(state, intent_key=intent_key, operation="create-draft-pr")
    if state.get("phase") != "worker-running":
        raise TransitionError("record a draft PR only after the initial Worker handoff")
    if state["activation"]["allowed_operations"].get("create_draft_prs") is not True:
        raise ScopeError("draft PR creation was not authorized")
    task = state.get("task")
    if not isinstance(task, MutableMapping):
        raise ValidationError("active task is missing")
    assert_repository_target(
        state["activation"]["repository"],
        repository,
        target_repository_id=repository_id,
    )
    if require_positive_issue(issue) != task.get("issue"):
        raise ScopeError("draft PR issue does not match the selected task")
    number = require_positive_issue(pr_number, "pr_number")
    expected_url = f"https://github.com/{normalize_owner_name(repository)}/pull/{number}"
    if pr_url.casefold() != expected_url.casefold():
        raise ValidationError("draft PR URL does not match the exact repository and PR")
    if not isinstance(pr_state, str) or pr_state.casefold() != "open":
        raise GuardError("draft PR receipt requires connector read-back proving the PR is open")
    if draft is not True:
        raise GuardError("draft PR receipt requires connector read-back proving draft state")
    live_identity = {
        "repository": repository,
        "repository_id": repository_id,
        "base_repository": base_repository,
        "base_repository_id": base_repository_id,
        "base_branch": base_branch,
        "base_sha": require_full_sha(base_sha, "PR base_sha"),
        "head_repository": head_repository,
        "head_repository_id": head_repository_id,
        "head_ref": validate_branch_name(head_ref, "PR head_ref"),
        "head_sha": require_full_sha(head_sha, "PR head_sha"),
    }
    _validate_exact_pr_identity(state, live_identity)
    task.update(
        {
            "pr_number": number,
            "pr_url": pr_url,
            "active_role": None,
            "draft_pr_receipt": {
                "repository": normalize_owner_name(repository),
                "repository_id": repository_id,
                "issue": issue,
                "pr_number": number,
                "pr_url": pr_url,
                "base_sha": base_sha,
                "base_repository": normalize_owner_name(base_repository),
                "base_repository_id": base_repository_id,
                "base_branch": base_branch,
                "head_sha": head_sha,
                "head_repository": normalize_owner_name(head_repository),
                "head_repository_id": head_repository_id,
                "head_ref": head_ref,
                "state": "open",
                "draft": draft,
            },
        }
    )
    transition_state(state, "draft-pr")


def record_merge_receipt(
    state: MutableMapping[str, Any],
    *,
    intent_key: str,
    repository: str,
    repository_id: int | None,
    pr_number: int,
    pr_url: str,
    pr_state: str,
    merged: bool,
    base_repository: str,
    base_repository_id: int | None,
    base_branch: str,
    base_sha: str,
    head_repository: str,
    head_repository_id: int | None,
    head_ref: str,
    head_sha: str,
    expected_head_sha: str,
    merge_sha: str,
    merge_method: str,
) -> None:
    _require_pending_github_intent(state, intent_key=intent_key, operation="merge-pr")
    if state.get("phase") != "merging":
        raise TransitionError("merge receipt is expected only in merging")
    task = state.get("task")
    if not isinstance(task, MutableMapping):
        raise ValidationError("active task is missing")
    assert_repository_target(
        state["activation"]["repository"],
        repository,
        target_repository_id=repository_id,
    )
    if require_positive_issue(pr_number, "pr_number") != task.get("pr_number"):
        raise ScopeError("merge receipt PR does not match the active task")
    live_identity = {
        "repository": repository,
        "repository_id": repository_id,
        "base_repository": base_repository,
        "base_repository_id": base_repository_id,
        "base_branch": base_branch,
        "base_sha": base_sha,
        "head_repository": head_repository,
        "head_repository_id": head_repository_id,
        "head_ref": head_ref,
        "head_sha": head_sha,
    }
    _validate_exact_pr_identity(state, live_identity)
    if pr_url != task.get("pr_url") or merged is not True or str(pr_state).casefold() != "closed":
        raise GuardError("merge receipt requires connector proof that the exact PR is merged and closed")
    expected = require_full_sha(expected_head_sha, "expected_head_sha")
    if expected != task.get("candidate_sha"):
        raise ScopeError("merge receipt head differs from the reviewed candidate")
    if require_full_sha(head_sha, "merged PR head_sha") != expected:
        raise ScopeError("merged PR live head differs from the expected reviewed candidate")
    if merge_method != "merge":
        raise ScopeError("Roundlet permits merge commits only")
    merged = require_full_sha(merge_sha, "merge_sha")
    receipt = {
        "repository": normalize_owner_name(repository),
        "repository_id": repository_id,
        "pr_number": pr_number,
        "pr_url": pr_url,
        "state": "closed",
        "merged": True,
        "base_repository": normalize_owner_name(base_repository),
        "base_repository_id": base_repository_id,
        "base_branch": base_branch,
        "base_sha": base_sha,
        "head_repository": normalize_owner_name(head_repository),
        "head_repository_id": head_repository_id,
        "head_ref": head_ref,
        "expected_head_sha": expected,
        "merge_sha": merged,
        "merge_method": "merge",
    }
    task.update(
        {
            "merge_sha": merged,
            "merged_head_sha": expected,
            "merge_receipt": receipt,
        }
    )
    transition_state(state, "closing-issue")


def record_issue_close_receipt(
    state: MutableMapping[str, Any],
    *,
    intent_key: str,
    repository: str,
    repository_id: int | None,
    issue: int,
    issue_state: str,
    state_reason: str,
) -> None:
    _require_pending_github_intent(state, intent_key=intent_key, operation="close-issue")
    if state.get("phase") != "closing-issue":
        raise TransitionError("issue-close receipt is expected only in closing-issue")
    if state["activation"]["allowed_operations"].get("close_completed_sub_issues") is not True:
        raise ScopeError("issue closure was not authorized")
    task = state.get("task")
    if not isinstance(task, MutableMapping) or not isinstance(task.get("merge_receipt"), Mapping):
        raise ValidationError("confirmed merge receipt is required before issue closure")
    assert_repository_target(
        state["activation"]["repository"],
        repository,
        target_repository_id=repository_id,
    )
    selected = require_positive_issue(issue)
    if selected != task.get("issue"):
        raise ScopeError("only the exact selected issue may be closed")
    if state_reason != "completed":
        raise ScopeError("selected issue must close as completed")
    if not isinstance(issue_state, str) or issue_state.casefold() != "closed":
        raise GuardError("issue-close receipt requires connector read-back proving state=closed")
    task["issue_close_receipt"] = {
        "repository": normalize_owner_name(repository),
        "repository_id": repository_id,
        "issue": selected,
        "state": "closed",
        "state_reason": "completed",
    }
    transition_state(state, "cleanup")


def record_remote_branch_deleted(
    state: MutableMapping[str, Any],
    *,
    intent_key: str,
    repository: str,
    repository_id: int | None,
    branch: str,
    absent: bool,
) -> None:
    _require_pending_github_intent(state, intent_key=intent_key, operation="delete-remote-branch")
    if state.get("phase") != "cleanup" or absent is not True:
        raise TransitionError("remote branch deletion proof is expected only during cleanup")
    if state["activation"]["allowed_operations"].get("delete_proven_task_owned_resources") is not True:
        raise ScopeError("task-owned remote branch deletion was not authorized")
    task = state.get("task")
    if not isinstance(task, MutableMapping):
        raise ValidationError("active cleanup task is missing")
    assert_repository_target(
        state["activation"]["repository"],
        repository,
        target_repository_id=repository_id,
    )
    if validate_branch_name(branch) != task.get("branch"):
        raise ScopeError("remote branch deletion does not match the task-owned branch")
    cleanup = task.get("cleanup", {})
    if not all(
        cleanup.get(key) is True
        for key in ("worker_archived", "supervisors_archived", "worktree_removed", "local_branch_deleted")
    ):
        raise GuardError("archive children and finish proven local cleanup before remote branch deletion")
    task["cleanup"]["remote_branch_deleted"] = True


def record_children_archived(
    state: MutableMapping[str, Any],
    *,
    worker_thread_id: str,
    supervisor_thread_ids: Sequence[str],
) -> None:
    if state.get("phase") != "cleanup":
        raise TransitionError("child archival proof is expected only during cleanup")
    task = state.get("task")
    review = state.get("review")
    if not isinstance(task, MutableMapping) or not isinstance(review, Mapping):
        raise ValidationError("active cleanup task/review is missing")
    if worker_thread_id != task.get("worker_thread_id"):
        raise ScopeError("archived Worker differs from the task-owned Worker")
    expected_supervisors = review.get("unarchived_supervisor_thread_ids", [])
    if (
        not isinstance(supervisor_thread_ids, Sequence)
        or isinstance(supervisor_thread_ids, (str, bytes))
        or len(supervisor_thread_ids) != len(set(supervisor_thread_ids))
        or set(supervisor_thread_ids) != set(expected_supervisors)
    ):
        raise ScopeError("archived Supervisors differ from the exact review threads")
    if expected_supervisors:
        review["archived_supervisor_digest"] = fold_archive_digest(
            review["archived_supervisor_digest"],
            [{"thread_id": thread_id} for thread_id in sorted(expected_supervisors)],
        )
        review["archived_supervisor_count"] += len(expected_supervisors)
        review["unarchived_supervisor_thread_ids"] = []
    if review.get("archived_supervisor_count") != review.get("round"):
        raise GuardError("every Supervisor round must have a durable archival receipt")
    task["cleanup"]["worker_archived"] = True
    task["cleanup"]["supervisors_archived"] = True


def verify_premerge_gates(state: Mapping[str, Any], live: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        validate_state(state)
    except RoundletError as exc:
        return [f"persisted state is invalid: {exc}"]
    task = state.get("task") or {}
    review = state.get("review") or {}
    activation = state.get("activation") or {}
    required_true = {
        "scope_valid": "activation scope is invalid",
        "membership_valid": "selected issue membership is not unambiguous",
        "worktree_clean": "Worker worktree is dirty",
        "tests_passed": "required tests are not passing or justified",
        "checks_passed": "required GitHub checks are not passing",
        "pr_ready": "pull request is not ready for review",
        "mergeable": "pull request is not mergeable",
        "no_conflict": "pull request has a merge conflict",
        "no_new_blocker": "new comments or review state contain a blocker",
        "no_maintenance_request": "maintenance is pending",
    }
    for key, message in required_true.items():
        if live.get(key) is not True:
            errors.append(message)
    if state.get("phase") != "pre-merge":
        errors.append("state phase is not pre-merge")
    if task.get("worker_ready_to_merge") is not True:
        errors.append("Worker did not return durable READY_TO_MERGE")
    if activation.get("allowed_operations", {}).get("merge_commit_after_all_gates") is not True:
        errors.append("merge operation was not authorized")
    pass_identity = review.get("pass_identity")
    if review.get("last_result") != "PASS" or not isinstance(pass_identity, Mapping):
        errors.append("latest fresh Supervisor result is not PASS")
    candidate = task.get("candidate_sha")
    if live.get("head_sha") != candidate:
        errors.append("PR head differs from the active candidate")
    if isinstance(pass_identity, Mapping) and pass_identity.get("candidate_sha") != candidate:
        errors.append("Supervisor PASS is stale")
    try:
        _validate_exact_pr_identity(state, live)
    except (ScopeError, ValidationError) as exc:
        errors.append(str(exc))
    if live.get("issue") != task.get("issue"):
        errors.append("merge target does not match the selected issue")
    if not isinstance(task.get("pr_number"), int) or task.get("pr_number") <= 0:
        errors.append("active task has no recorded PR")
    elif live.get("pr_number") != task.get("pr_number"):
        errors.append("merge target does not match the selected PR")
    if live.get("pr_url") != task.get("pr_url"):
        errors.append("merge target PR URL differs from the selected task")
    if str(live.get("pr_state", "")).casefold() != "open" or live.get("draft") is not False:
        errors.append("merge target must be the exact open ready PR")
    if live.get("merge_method") != "merge":
        errors.append("merge method must be merge")
    if state.get("maintenance", {}).get("requested"):
        errors.append("maintenance is pending")
    if not isinstance(pass_identity, Mapping) or pass_identity.get("stage") != "final":
        errors.append("latest Supervisor PASS is not the fresh post-ready review")
    return errors


def assert_premerge_gates(state: Mapping[str, Any], live: Mapping[str, Any]) -> None:
    errors = verify_premerge_gates(state, live)
    if errors:
        raise GuardError("pre-merge gates failed: " + "; ".join(errors))


def request_maintenance(state: MutableMapping[str, Any], reason: str) -> None:
    if state.get("phase") not in MAINTENANCE_ENTRY_PHASES:
        raise TransitionError("maintenance cannot be requested from this phase")
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("maintenance reason is required")
    previous = state["phase"]
    maintenance = state["maintenance"]
    maintenance.update(
        {
            "requested": True,
            "reason": reason.strip(),
            "previous_phase": previous,
            "resume_worker": False,
        }
    )
    transition_state(state, "maintenance-requested")


def drain_worker_for_maintenance(
    state: MutableMapping[str, Any],
    *,
    worker_thread_id: str,
    candidate_sha: str | None,
    clean: bool,
) -> None:
    if state.get("phase") != "maintenance-requested":
        raise TransitionError("maintenance Worker drain is not expected")
    task = state.get("task")
    if not isinstance(task, MutableMapping) or task.get("active_role") != "worker":
        raise TransitionError("maintenance Worker drain requires the active Worker")
    if worker_thread_id != task.get("worker_thread_id"):
        raise ScopeError("maintenance Worker drain came from another task")
    if not clean:
        raise GuardError("maintenance Worker checkpoint requires a clean worktree")
    if candidate_sha is not None:
        candidate = require_full_sha(candidate_sha, "maintenance Worker candidate_sha")
        if candidate != task.get("candidate_sha"):
            if state["maintenance"].get("previous_phase") == "ready":
                raise GuardError("a ready candidate cannot change during maintenance drain")
            task["candidate_sha"] = candidate
            state["review"]["pass_identity"] = None
            state["review"]["last_result"] = None
            task["worker_ready_to_merge"] = False
            if state["maintenance"].get("previous_phase") == "pass-follow-up":
                state["maintenance"]["previous_phase"] = "worker-repair"
    task["active_role"] = None
    state["maintenance"]["resume_worker"] = True
    transition_state(state, "maintenance-draining")


def discard_supervisor_for_maintenance(
    state: MutableMapping[str, Any],
    *,
    supervisor_thread_id: str,
) -> None:
    if state.get("phase") != "maintenance-requested":
        raise TransitionError("maintenance Supervisor discard is not expected")
    task = state.get("task")
    review = state.get("review")
    if not isinstance(task, MutableMapping) or not isinstance(review, MutableMapping):
        raise ValidationError("maintenance Supervisor state is missing")
    if task.get("active_role") != "supervisor" or review.get("current_supervisor_thread_id") != supervisor_thread_id:
        raise ScopeError("maintenance discard differs from the active Supervisor")
    previous_phase = state["maintenance"].get("previous_phase")
    if previous_phase == "supervisor-running":
        state["maintenance"]["previous_phase"] = "draft-pr"
    elif previous_phase == "final-supervisor":
        state["maintenance"]["previous_phase"] = "ready"
    else:
        raise TransitionError("maintenance Supervisor phase cannot be restored safely")
    task["active_role"] = None
    review["current_supervisor_thread_id"] = None
    state["maintenance"]["resume_worker"] = False
    record_supervisor_archived(state, supervisor_thread_id=supervisor_thread_id)
    transition_state(state, "maintenance-draining")


def create_maintenance_checkpoint(
    state: MutableMapping[str, Any],
    *,
    checkpoint_id: str,
    schedule_id: str,
    schedule_state: str,
    pending_action: Mapping[str, Any] | None = None,
) -> None:
    if state.get("phase") not in {"maintenance-requested", "maintenance-draining"}:
        raise TransitionError("maintenance checkpoint is not expected")
    if not isinstance(checkpoint_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{8,128}", checkpoint_id):
        raise ValidationError("checkpoint_id is malformed")
    if not isinstance(schedule_id, str) or not schedule_id:
        raise ValidationError("schedule_id is required")
    if schedule_state != "paused":
        raise GuardError("maintenance checkpoint requires connector proof that the schedule is paused")
    task = state.get("task")
    if isinstance(task, Mapping) and task.get("active_role") is not None:
        raise TransitionError("cannot checkpoint while a child role is mutating or unresolved")
    if any(receipt.get("status") == "pending" for receipt in state.get("receipts", {}).values()):
        raise MailboxError("reconcile pending mutation receipts before maintenance checkpoint")
    if state.get("github_mutations", {}).get("pending") is not None:
        raise MailboxError("reconcile pending GitHub mutation before maintenance checkpoint")
    if state.get("phase") == "maintenance-requested":
        transition_state(state, "maintenance-draining")
    maintenance = state["maintenance"]
    maintenance.update(
        {
            "checkpoint_id": checkpoint_id,
            "schedule_id": schedule_id,
            "schedule_state": "paused",
            "stored_versions": copy.deepcopy(state["versions"]),
            "installed_digest": state["skill"]["content_digest"],
            "pending_action": copy.deepcopy(pending_action),
            "migrated_from_versions": None,
            "migration_receipt": None,
            "checkpointed_at": utc_now(),
        }
    )
    transition_state(state, "paused-maintenance")


def documentation_only_resume_evidence(
    state: Mapping[str, Any],
    *,
    installed_roundlet_digest: str,
    current_versions: Mapping[str, Any],
    schedule_id: str,
    reviewed_source_repository: str,
    reviewed_source_repository_id: int | None,
    reviewed_source_commit: str,
    reviewed_source_pr_url: str,
    changed_paths: Sequence[str],
) -> dict[str, Any]:
    """Build the exact evidence envelope that the Orchestrator must verify externally."""
    if normalize_owner_name(reviewed_source_repository) != state["skill"].get("source_repository"):
        raise ScopeError("documentation evidence belongs to another Roundlet source repository")
    if reviewed_source_repository_id is not None:
        require_positive_issue(reviewed_source_repository_id, "reviewed source repository ID")
    commit = require_full_sha(reviewed_source_commit, "reviewed source commit")
    if not isinstance(changed_paths, Sequence) or isinstance(changed_paths, (str, bytes)):
        raise ValidationError("documentation-only changed paths must be a list")
    normalized_paths = list(changed_paths)
    if normalized_paths != [DOCUMENTATION_ONLY_OPERATOR_GUIDE_PATH]:
        raise ValidationError("PASS preservation permits only the reviewed operator-guide documentation path")
    repository = normalize_owner_name(reviewed_source_repository)
    if not re.fullmatch(rf"https://github\.com/{re.escape(repository)}/pull/[1-9]\d*", reviewed_source_pr_url):
        raise ValidationError("documentation-only source PR URL is not exact")
    return {
        "source_change_class": "reviewed-documentation-only",
        "activation_id": state["activation"]["id"],
        "previous_installed_digest": state["skill"]["content_digest"],
        "reviewed_installed_digest": require_content_digest(installed_roundlet_digest),
        "candidate_sha": (state.get("task") or {}).get("candidate_sha"),
        "versions": copy.deepcopy(dict(current_versions)),
        "schedule_id": schedule_id,
        "pending_action_digest": digest_json(state.get("maintenance", {}).get("pending_action")),
        "receipts_digest": digest_json(state.get("receipts", {})),
        "reviewed_source_repository": repository,
        "reviewed_source_repository_id": reviewed_source_repository_id,
        "reviewed_source_commit": commit,
        "reviewed_source_pr_url": reviewed_source_pr_url,
        "changed_paths": normalized_paths,
        "installed_content_digest": require_content_digest(installed_roundlet_digest),
    }


def resume_maintenance(
    state: MutableMapping[str, Any],
    *,
    checkpoint_id: str,
    installed_roundlet_digest: str,
    current_versions: Mapping[str, Any],
    repository_identity: RepositoryIdentity,
    schedule_id: str,
    candidate_identity_certain: bool = True,
    documentation_evidence: Mapping[str, Any] | None = None,
) -> None:
    """Validate an explicit resume signal and restore the recorded durable phase."""
    original = copy.deepcopy(state)
    try:
        if state.get("phase") != "paused-maintenance":
            raise TransitionError("resume requires paused-maintenance")
        maintenance = state.get("maintenance", {})
        if checkpoint_id != maintenance.get("checkpoint_id"):
            raise ValidationError("checkpoint_id does not match")
        new_digest = require_content_digest(installed_roundlet_digest)
        if maintenance.get("installed_digest") != state["skill"]["content_digest"]:
            raise ValidationError("checkpoint installed digest differs from paused state")
        if maintenance.get("stored_versions") != state.get("versions"):
            raise ValidationError("checkpoint version contract differs from paused state")
        if schedule_id != maintenance.get("schedule_id"):
            raise ValidationError("existing schedule ID differs from the checkpoint")
        if any(receipt.get("status") == "pending" for receipt in state.get("receipts", {}).values()):
            raise MailboxError("reconcile pending mutation receipts before maintenance resume")
        if state.get("github_mutations", {}).get("pending") is not None:
            raise MailboxError("reconcile pending GitHub mutation before maintenance resume")
        repo = state["activation"]["repository"]
        assert_repository_target(repo, repository_identity.owner_name, target_repository_id=repository_identity.repository_id)
        if repo.get("git_common_dir_fingerprint") != repository_identity.git_common_dir_fingerprint:
            raise ScopeError("Git common directory identity changed during maintenance")
        if repo.get("origin_fingerprint") != repository_identity.origin_fingerprint:
            raise ScopeError("origin identity changed during maintenance")
        if repo.get("origin_push_fingerprint") != repository_identity.origin_push_fingerprint:
            raise ScopeError("origin push identity changed during maintenance")
        if repo.get("origin_host") != repository_identity.origin_host:
            raise ScopeError("origin host changed during maintenance")
        if state["activation"]["base_branch"] != repository_identity.base_branch:
            raise ScopeError("base branch changed during maintenance")
        if not repository_identity_has_effective_base(repository_identity):
            raise GuardError("resume requires an exact effective synchronized base identity")
        transition_state(state, "maintenance-validating")
        try:
            validate_versions(current_versions)
        except ValidationError as exc:
            raise MigrationError("state must use a complete supported version contract before resume") from exc
        versions_changed = any(
            current_versions.get(key) != state["versions"].get(key)
            for key in ("protocol", "review_contract", "policy")
        )
        digest_changed = new_digest != state["skill"]["content_digest"]
        documentation_only_verified = False
        if documentation_evidence is not None:
            try:
                expected_evidence = documentation_only_resume_evidence(
                    state,
                    installed_roundlet_digest=new_digest,
                    current_versions=current_versions,
                    schedule_id=schedule_id,
                    reviewed_source_repository=str(documentation_evidence["reviewed_source_repository"]),
                    reviewed_source_repository_id=documentation_evidence["reviewed_source_repository_id"],
                    reviewed_source_commit=str(documentation_evidence["reviewed_source_commit"]),
                    reviewed_source_pr_url=str(documentation_evidence["reviewed_source_pr_url"]),
                    changed_paths=documentation_evidence["changed_paths"],
                )
            except (KeyError, TypeError) as exc:
                raise ValidationError("documentation-only maintenance evidence is incomplete") from exc
            if canonical_json(documentation_evidence) != canonical_json(expected_evidence):
                raise ValidationError("documentation-only maintenance evidence is incomplete or mismatched")
            if versions_changed:
                raise ValidationError("documentation-only maintenance cannot change protocol, review, or policy")
            documentation_only_verified = True
        if (
            versions_changed
            or not candidate_identity_certain
            or (digest_changed and not documentation_only_verified)
        ):
            state["review"]["pass_identity"] = None
            state["review"]["last_result"] = None
        state["versions"] = dict(current_versions)
        state["skill"]["content_digest"] = new_digest
        state["activation"]["scope_digest"] = compute_scope_digest(
            state["activation"]["repository"],
            state["activation"]["base_branch"],
            state["activation"]["umbrella_issues"],
            state["activation"]["allowed_operations"],
            new_digest,
            owner_actor=state["activation"]["owner_actor"],
            capability_preflight=state["activation"]["capability_preflight"],
            orchestrator_creation_receipt=state["activation"]["orchestrator_creation_receipt"],
            role_model_snapshot=state["activation"]["role_model_snapshot"],
            role_model_snapshot_digest=state["activation"]["role_model_snapshot_digest"],
            protocol_version=str(state["versions"]["protocol"]),
            policy_version=str(state["versions"]["policy"]),
        )
        transition_state(state, "resuming-maintenance")
        restored = maintenance.get("previous_phase")
        if restored not in PHASES or restored in TERMINAL_PHASES:
            raise TransitionError("checkpoint previous phase cannot be resumed")
        if state["review"].get("pass_identity") is None:
            if restored in {"pass-follow-up", "supervisor-running"}:
                restored = "draft-pr"
            elif restored in {"final-supervisor", "pre-merge", "merging"}:
                restored = "ready"
        maintenance["requested"] = False
        maintenance["resumed_at"] = utc_now()
        transition_state(state, restored)
        if (
            maintenance.get("resume_worker") is True
            and restored in {"draft-pr", "ready"}
            and state["review"].get("pass_identity") is None
        ):
            maintenance["resume_worker"] = False
        elif maintenance.get("resume_worker") is True:
            task = state.get("task")
            if not isinstance(task, MutableMapping) or restored not in {
                "worker-running",
                "worker-repair",
                "pass-follow-up",
                "ready",
            }:
                raise TransitionError("maintenance Worker continuation cannot be restored safely")
            task["active_role"] = "worker"
            maintenance["resume_worker"] = False
        validate_state(state)
    except BaseException:
        state.clear()
        state.update(original)
        raise


def _migrate_state_document(
    document: Mapping[str, Any],
    target_version: int = SCHEMA_VERSION,
    *,
    role_model_config: Mapping[str, Any] | None = None,
    installed_roundlet_digest: str | None = None,
) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        raise MigrationError("state migration input must be an object")
    result = copy.deepcopy(dict(document))
    versions = result.get("versions")
    if not isinstance(versions, MutableMapping):
        raise MigrationError("state versions are missing")
    current = versions.get("schema")
    original_versions = copy.deepcopy(dict(versions))
    config = (
        load_role_model_config(Path(__file__).resolve().parents[1])
        if role_model_config is None
        else dict(role_model_config)
    )
    if current == target_version:
        return result
    if current == 1 and target_version >= 2:
        skill = result.setdefault("skill", {})
        if not isinstance(skill, MutableMapping):
            raise MigrationError("legacy skill identity is malformed")
        skill.setdefault("source_repository", SKILL_SOURCE_REPOSITORY)
        result.setdefault("completed_tasks", [])
        result.setdefault("retry", None)
        result.setdefault("blocker", None)
        review = result.setdefault("review", {})
        if not isinstance(review, MutableMapping):
            raise MigrationError("legacy review state is malformed")
        review.setdefault("supervisor_thread_ids", [])
        review.setdefault("current_supervisor_thread_id", None)
        if review.get("round", 0) and any(
            key not in review
            for key in (
                "unarchived_supervisor_thread_ids",
                "archived_supervisor_count",
                "archived_supervisor_digest",
                "last_supervisor_created_at",
                "supervisor_creation_receipts",
            )
        ):
            raise MigrationError("legacy review history lacks immutable freshness and archival evidence")
        review.setdefault("unarchived_supervisor_thread_ids", [])
        review.setdefault("archived_supervisor_count", 0)
        review.setdefault("archived_supervisor_digest", "0" * 64)
        review.setdefault("last_supervisor_created_at", None)
        review.setdefault("supervisor_creation_receipts", [])
        result.setdefault("receipt_archive", {"count": 0, "digest": "0" * 64})
        if "mailbox_high_water" not in result:
            high_water = {kind: 0 for kind in sorted(MAILBOX_NAMES)}
            for key, receipt in result.get("receipts", {}).items():
                try:
                    high_water[receipt["kind"]] = max(high_water[receipt["kind"]], mailbox_sequence(key))
                except (KeyError, TypeError, MailboxError) as exc:
                    raise MigrationError("legacy mailbox receipts cannot establish monotonic identity") from exc
            result["mailbox_high_water"] = high_water
        maintenance = result.setdefault("maintenance", {})
        maintenance.setdefault("pending_action", None)
        maintenance.setdefault("resume_worker", False)
        maintenance.setdefault("migrated_from_versions", None)
        maintenance.setdefault("migration_receipt", None)
        task = result.get("task")
        if isinstance(task, MutableMapping):
            task.setdefault("cleanup", {key: False for key in sorted(LOCAL_CLEANUP_KEYS)})
        versions["schema"] = 2
        if result.get("phase") == "paused-maintenance":
            if maintenance.get("stored_versions") != original_versions:
                raise MigrationError("paused checkpoint versions do not match the migration input")
            maintenance["migrated_from_versions"] = original_versions
            maintenance["stored_versions"] = copy.deepcopy(dict(versions))
            maintenance["migration_receipt"] = {
                "from_schema": 1,
                "to_schema": 2,
                "input_digest": digest_json(document),
                "migrated_at": utc_now(),
            }
        current = 2
    if current == 2 and target_version >= 3:
        activation = result.get("activation")
        if not isinstance(activation, Mapping):
            raise MigrationError("schema-2 activation identity is missing")
        try:
            validate_owner_actor(activation.get("owner_actor", {}))
            validate_capability_preflight(activation.get("capability_preflight", {}))
            validate_role_creation_receipt(
                activation.get("orchestrator_creation_receipt", {}),
                role="orchestrator",
                thread_id=str(activation.get("orchestrator_thread_id", "")),
                project_identity=str(
                    activation.get("repository", {}).get("git_common_dir_fingerprint", "")
                ),
                parent_thread_id=None,
                role_model_snapshot=config["legacy_profiles"]["policy_3"],
            )
        except RoundletError as exc:
            raise MigrationError(
                "schema-2 state lacks externally verified owner/capability activation evidence"
            ) from exc
        review = result.get("review")
        if not isinstance(review, Mapping) or "supervisor_creation_receipts" not in review:
            raise MigrationError("schema-2 state lacks service-returned Supervisor capability receipts")
        task = result.get("task")
        if isinstance(task, Mapping) and "worker_creation_receipt" not in task:
            raise MigrationError("schema-2 task lacks a service-returned Worker capability receipt")
        github_mutations = result.get("github_mutations")
        if not isinstance(github_mutations, Mapping) or set(github_mutations) != {"pending", "receipts"}:
            raise MigrationError("schema-2 state cannot prove the GitHub mutation intent ledger")
        maintenance = result.setdefault("maintenance", {})
        if result.get("phase") == "paused-maintenance":
            if maintenance.get("stored_versions") != versions:
                raise MigrationError("paused checkpoint versions do not match schema-2 input")
            if maintenance.get("schedule_state") != "paused":
                raise MigrationError("schema-2 checkpoint lacks paused schedule evidence")
        versions["schema"] = 3
        if result.get("phase") == "paused-maintenance":
            maintenance["migrated_from_versions"] = original_versions
            maintenance["stored_versions"] = copy.deepcopy(dict(versions))
            maintenance["migration_receipt"] = {
                "from_schema": original_versions.get("schema"),
                "to_schema": 3,
                "input_digest": digest_json(document),
                "migrated_at": utc_now(),
            }
        current = 3
    if current == 3 and target_version >= 4:
        activation = result.get("activation")
        preflight = activation.get("capability_preflight", {}) if isinstance(activation, Mapping) else {}
        if preflight.get("connector_read_adapter_receipts") is not True:
            raise MigrationError(
                "schema-3 state lacks service proof for connector adapter receipt enforcement"
            )
        selection = result.get("selection")
        if isinstance(selection, Mapping) and "connector_refresh_receipt" not in selection:
            raise MigrationError(
                "schema-3 selection lacks connector-origin proof and cannot be migrated"
            )
        maintenance = result.setdefault("maintenance", {})
        if result.get("phase") == "paused-maintenance":
            if maintenance.get("stored_versions") != versions:
                raise MigrationError("paused checkpoint versions do not match schema-3 input")
            if maintenance.get("schedule_state") != "paused":
                raise MigrationError("schema-3 checkpoint lacks paused schedule evidence")
        versions.update(
            {
                "schema": 4,
                "protocol": PROTOCOL_VERSION,
                "review_contract": REVIEW_CONTRACT_VERSION,
                "policy": "3",
            }
        )
        if result.get("phase") == "paused-maintenance":
            maintenance["migrated_from_versions"] = original_versions
            maintenance["stored_versions"] = copy.deepcopy(dict(versions))
            maintenance["migration_receipt"] = {
                "from_schema": original_versions.get("schema"),
                "to_schema": 4,
                "input_digest": digest_json(document),
                "migrated_at": utc_now(),
            }
        current = 4
    if current == 4 and target_version >= 5:
        schema4_versions = copy.deepcopy(dict(versions))
        if versions.get("policy") != "3":
            raise MigrationError("schema-4 state does not use the required policy-3 role profile")
        try:
            legacy_snapshot = _validate_role_model_snapshot(config["legacy_profiles"]["policy_3"])
        except (KeyError, RoundletError, TypeError) as exc:
            raise MigrationError("role-model configuration lacks the policy-3 legacy profile") from exc
        if role_model_snapshot_digest(legacy_snapshot) != POLICY3_ROLE_MODEL_SNAPSHOT_DIGEST:
            raise MigrationError("role-model configuration has an unrecognized policy-3 legacy profile")
        activation = result.get("activation")
        if not isinstance(activation, MutableMapping):
            raise MigrationError("schema-4 activation identity is missing")
        repository = activation.get("repository")
        if not isinstance(repository, Mapping):
            raise MigrationError("schema-4 repository identity is missing")
        validate_legacy_policy3_state(result, legacy_snapshot)
        activation["role_model_snapshot"] = legacy_snapshot
        activation["role_model_snapshot_digest"] = digest_json(legacy_snapshot)
        original_installed_digest = require_content_digest(
            result["skill"].get("content_digest"), "schema-4 installed digest"
        )
        if installed_roundlet_digest is not None:
            result["skill"]["content_digest"] = require_content_digest(installed_roundlet_digest)
        versions.update(
            {
                "schema": 5,
                "protocol": PROTOCOL_VERSION,
                "review_contract": REVIEW_CONTRACT_VERSION,
                "policy": POLICY_VERSION,
            }
        )
        result["activation"]["scope_digest"] = compute_scope_digest(
            repository,
            activation.get("base_branch"),
            activation.get("umbrella_issues", []),
            activation.get("allowed_operations", {}),
            result["skill"]["content_digest"],
            owner_actor=activation.get("owner_actor", {}),
            capability_preflight=activation.get("capability_preflight", {}),
            orchestrator_creation_receipt=activation.get("orchestrator_creation_receipt", {}),
            role_model_snapshot=legacy_snapshot,
            role_model_snapshot_digest=activation["role_model_snapshot_digest"],
            protocol_version=PROTOCOL_VERSION,
            policy_version=POLICY_VERSION,
        )
        maintenance = result.get("maintenance", {})
        if result.get("phase") == "paused-maintenance":
            if maintenance.get("stored_versions") != schema4_versions:
                raise MigrationError("paused checkpoint versions do not match schema-4 input")
            # The checkpoint becomes bound to the reviewed target installation;
            # retain its prior binding in the receipt for migration evidence.
            maintenance["installed_digest"] = result["skill"]["content_digest"]
            maintenance["migrated_from_versions"] = original_versions
            maintenance["stored_versions"] = copy.deepcopy(dict(versions))
            maintenance["migration_receipt"] = {
                "from_schema": original_versions.get("schema"),
                "to_schema": 5,
                "input_digest": digest_json(document),
                "original_installed_digest": original_installed_digest,
                "migrated_installed_digest": result["skill"]["content_digest"],
                "migrated_at": utc_now(),
            }
        current = 5
    if current != target_version:
        raise MigrationError(f"no supported migration from schema {current} to {target_version}")
    return result


@dataclass(frozen=True)
class Comment:
    author: str
    author_id: int
    body: str


def _normalize_issue_references(text: str, current_repository: str) -> tuple[str, set[int]]:
    current = normalize_owner_name(current_repository)
    accepted: set[int] = set()

    def url_replace(match: re.Match[str]) -> str:
        parsed = urlparse(match.group(0))
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if parsed.hostname and parsed.hostname.casefold() == "github.com" and len(parts) == 4 and parts[2] == "issues":
            try:
                repo = normalize_owner_name(f"{parts[0]}/{parts[1]}")
                number = int(parts[3])
            except (ValidationError, ValueError):
                return "[external-reference]"
            if repo == current and number > 0:
                accepted.add(number)
                return f"#{number}"
        return "[external-reference]"

    cleaned = re.sub(
        r"https?://[^\s<>()]+",
        url_replace,
        text,
        flags=re.IGNORECASE,
    )

    def qualified_replace(match: re.Match[str]) -> str:
        repo = normalize_owner_name(f"{match.group(1)}/{match.group(2)}")
        number = int(match.group(3))
        if match.group(4):
            return "[external-reference]"
        if repo == current:
            accepted.add(number)
            return f"#{number}"
        return "[external-reference]"

    cleaned = re.sub(
        r"(?<![\w./-])([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)#(\d+)([#?][^\s]*)?",
        qualified_replace,
        cleaned,
    )
    return cleaned, accepted


def extract_same_repository_issue_numbers(text: str, current_repository: str) -> list[int]:
    cleaned, accepted = _normalize_issue_references(text, current_repository)
    cleaned = re.sub(r"https?://\S+", "[url]", cleaned, flags=re.IGNORECASE)
    for match in re.finditer(r"(?<![\w/])#(\d+)\b", cleaned):
        accepted.add(int(match.group(1)))
    return sorted(number for number in accepted if number > 0)


def _section(markdown: str, names: Iterable[str]) -> str:
    wanted = {re.sub(r"\s+", " ", name.casefold()).strip(" :") for name in names}
    lines: list[str] = []
    active = False
    for line in markdown.splitlines():
        heading = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line)
        if heading:
            title = re.sub(r"[*_`]", "", heading.group(1)).casefold()
            title = re.sub(r"\s+", " ", title).strip(" :")
            active = title in wanted
            continue
        if active:
            lines.append(line)
    return "\n".join(lines)


def _scope_line_is_negative(line: str) -> bool:
    return bool(
        re.search(
            r"\b(?:do\s+not|don't|exclude|remove|not\s+in\s+scope|obsolete|archived?|historical)\b",
            line,
            re.IGNORECASE,
        )
    )


def discover_membership(
    *,
    umbrella_issue: int,
    formal_subissues: Iterable[Mapping[str, Any]],
    umbrella_body: str,
    comments: Iterable[Comment | Mapping[str, Any]],
    owner_actor: Mapping[str, Any],
    current_repository: str,
) -> dict[int, list[str]]:
    """Discover only deterministic, owner-authorized same-repository membership."""
    require_positive_issue(umbrella_issue, "umbrella_issue")
    authorized_actor = validate_owner_actor(owner_actor)
    membership: dict[int, list[str]] = {}

    def add(number: int, source: str) -> None:
        number = require_positive_issue(number)
        if number == umbrella_issue:
            return
        membership.setdefault(number, [])
        if source not in membership[number]:
            membership[number].append(source)

    for formal in formal_subissues:
        if not isinstance(formal, Mapping):
            raise ScopeError("formal sub-issue evidence must include repository identity")
        formal_repository = normalize_owner_name(str(formal.get("repository", "")))
        if formal_repository != normalize_owner_name(current_repository):
            raise ScopeError("formal sub-issue evidence points to another repository")
        add(require_positive_issue(formal.get("issue")), "formal-sub-issue")
    body_headings = {
        "sub-issue",
        "sub-issues",
        "sub issue",
        "sub issues",
        "dependency matrix",
        "required implementation order",
        "implementation order",
    }
    body_scope = _section(umbrella_body, body_headings)
    positive_body_scope = "\n".join(
        line for line in body_scope.splitlines() if not _scope_line_is_negative(line)
    )
    for number in extract_same_repository_issue_numbers(positive_body_scope, current_repository):
        add(number, "umbrella-body")
    heading_seen = False
    trusted_list_context = True
    for line in umbrella_body.splitlines():
        heading = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line)
        if heading:
            heading_seen = True
            title = re.sub(r"[*_`]", "", heading.group(1)).casefold()
            title = re.sub(r"\s+", " ", title).strip(" :")
            trusted_list_context = title in body_headings
            continue
        if heading_seen and not trusted_list_context:
            continue
        if _scope_line_is_negative(line):
            continue
        if not re.match(
            r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?(?:#\d+\b|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+\b|https?://github\.com/)",
            line,
            re.IGNORECASE,
        ):
            continue
        for number in extract_same_repository_issue_numbers(line, current_repository):
            add(number, "umbrella-body-list")
    for raw in comments:
        try:
            comment = raw if isinstance(raw, Comment) else Comment(
                str(raw.get("author", "")),
                require_positive_issue(raw.get("author_id"), "comment author ID"),
                str(raw.get("body", "")),
            )
        except (AttributeError, TypeError) as exc:
            raise ScopeError("owner-comment evidence lacks connector actor identity") from exc
        if comment.author_id != authorized_actor["id"]:
            continue
        for line in comment.body.splitlines():
            lowered = line.casefold()
            if _scope_line_is_negative(lowered):
                continue
            explicit = re.search(
                r"\b(?:add|include|link|authorize|sub[- ]?issue|implementation\s+order|dependency\s+matrix|in\s+scope)\b",
                lowered,
            ) or re.match(r"^\s*(?:[-*]|\d+[.)])\s*(?:\[[ xX]\]\s*)?#\d+", line)
            if not explicit:
                continue
            for number in extract_same_repository_issue_numbers(line, current_repository):
                add(number, "owner-comment")
    return membership


def parse_required_order(markdown: str, current_repository: str) -> list[int]:
    content = _section(markdown, {"required implementation order", "implementation order"})
    content = "\n".join(line for line in content.splitlines() if not _scope_line_is_negative(line))
    cleaned, _ = _normalize_issue_references(content, current_repository)
    cleaned = re.sub(r"https?://\S+", "[url]", cleaned, flags=re.IGNORECASE)
    ordered: list[int] = []
    for match in re.finditer(r"(?<![\w/])#(\d+)\b", cleaned):
        number = int(match.group(1))
        if number > 0 and number not in ordered:
            ordered.append(number)
    return ordered


def parse_dependency_edges(text: str, current_repository: str) -> set[tuple[int, int]]:
    """Return (dependent, prerequisite) edges from explicit local statements."""
    cleaned, _ = _normalize_issue_references(text, current_repository)
    cleaned = re.sub(r"https?://\S+", "[url]", cleaned, flags=re.IGNORECASE)
    edges: set[tuple[int, int]] = set()
    relationship = re.compile(
        r"#(\d+)\b[^#\n]{0,120}?\b(?:depends\s+on|blocked\s+by|requires|prerequisite(?:s)?\s*[:=-])\b(?P<dependencies>[^.;\n]{0,240})",
        re.IGNORECASE,
    )
    for match in relationship.finditer(cleaned):
        dependent = int(match.group(1))
        for item in re.finditer(r"(?<![\w/])#(\d+)\b", match.group("dependencies")):
            prerequisite = int(item.group(1))
            if dependent > 0 and prerequisite > 0 and dependent != prerequisite:
                edges.add((dependent, prerequisite))
    matrix = _section(cleaned, {"dependency matrix"})
    for line in matrix.splitlines():
        refs = [int(item) for item in re.findall(r"(?<![\w/])#(\d+)\b", line)]
        if len(refs) >= 2:
            edges.update((refs[0], dependency) for dependency in refs[1:] if dependency != refs[0])
    return edges


@dataclass(frozen=True)
class IssueSnapshot:
    issue: int
    umbrella: int
    repository: str
    open: bool = True
    completion_verified: bool = False
    dependencies: tuple[int, ...] = ()
    external_blockers: tuple[str, ...] = ()
    membership_evidence: tuple[Mapping[str, Any], ...] = ()
    issue_evidence: Mapping[str, Any] | None = None
    completion_evidence: Mapping[str, Any] | None = None
    required_order_index: int | None = None
    ambiguous_active_implementation: bool = False
    owner_priority: int = 0
    unlocks: int = 0
    overlap_risk: int = 0

    def __post_init__(self) -> None:
        require_positive_issue(self.issue)
        require_positive_issue(self.umbrella, "umbrella")
        normalize_owner_name(self.repository)
        if type(self.open) is not bool or type(self.completion_verified) is not bool:
            raise ValidationError("snapshot open and completion_verified fields must be booleans")
        if type(self.ambiguous_active_implementation) is not bool:
            raise ValidationError("snapshot ambiguity field must be a boolean")
        for label, value in (
            ("owner priority", self.owner_priority),
            ("unlocks", self.unlocks),
            ("overlap risk", self.overlap_risk),
        ):
            if type(value) is not int or value < 0:
                raise ValidationError(f"snapshot {label} must be a non-negative integer")
        if self.required_order_index is not None and (
            type(self.required_order_index) is not int or self.required_order_index < 0
        ):
            raise ValidationError("snapshot required order index must be null or a non-negative integer")
        if type(self.dependencies) is not tuple or type(self.external_blockers) is not tuple:
            raise ValidationError("snapshot dependency and blocker collections must be tuples")
        if type(self.membership_evidence) is not tuple:
            raise ValidationError("snapshot membership evidence must be a tuple of connector receipts")
        for dependency in self.dependencies:
            require_positive_issue(dependency, "dependency")
        if len(self.dependencies) != len(set(self.dependencies)) or self.issue in self.dependencies:
            raise ValidationError("snapshot dependencies must be unique and cannot contain the issue itself")
        if any(not isinstance(item, str) or not item.strip() for item in self.external_blockers):
            raise ValidationError("snapshot external blockers must be non-empty strings")
        if not isinstance(self.issue_evidence, Mapping):
            raise ValidationError("snapshot requires canonical connector issue evidence")
        if not self.membership_evidence or any(
            not isinstance(item, Mapping) for item in self.membership_evidence
        ):
            raise ScopeError("snapshot requires canonical connector membership evidence")
        if self.completion_verified is not (self.completion_evidence is not None):
            raise ValidationError("snapshot completion flag must exactly match completion evidence presence")
        if self.completion_verified and self.open:
            raise ScopeError("completed snapshot cannot remain open")


_CONNECTOR_ADAPTER_SEAL = object()
_CONNECTOR_REFRESH_SEAL = object()
CONNECTOR_REFRESH_OPERATION = "complete-scope-refresh"


class _GitHubConnectorReadAdapter:
    """Process-local capability bound to service-returned adapter metadata and one callback."""

    __slots__ = ("_seal", "adapter_id", "activation_id", "read")

    def __init__(
        self,
        *,
        seal: object,
        adapter_id: str,
        activation_id: str,
        read: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    ) -> None:
        if seal is not _CONNECTOR_ADAPTER_SEAL:
            raise ScopeError("GitHub connector adapters require a service-issued capability")
        self._seal = seal
        self.adapter_id = adapter_id
        self.activation_id = activation_id
        self.read = read


def bind_github_connector_read_adapter(
    state: Mapping[str, Any],
    *,
    service_receipt: Mapping[str, Any],
    read_connector: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> _GitHubConnectorReadAdapter:
    """Bind the installed connector callback to exact service-returned capability metadata."""
    required = {
        "verified_by_service",
        "connector",
        "operation",
        "adapter_id",
        "activation_id",
        "repository",
        "repository_id",
        "orchestrator_thread_id",
        "project_identity",
        "created_at",
        "receipt_digest",
    }
    if not isinstance(service_receipt, Mapping) or set(service_receipt) != required:
        raise ValidationError("connector adapter requires exact service capability metadata")
    core = {
        key: copy.deepcopy(value)
        for key, value in service_receipt.items()
        if key != "receipt_digest"
    }
    if require_content_digest(service_receipt.get("receipt_digest"), "connector adapter receipt digest") != digest_json(core):
        raise ScopeError("connector adapter capability receipt digest is invalid")
    if (
        service_receipt.get("verified_by_service") is not True
        or service_receipt.get("connector") != "github"
        or service_receipt.get("operation") != CONNECTOR_REFRESH_OPERATION
    ):
        raise ScopeError("service did not verify the required GitHub connector read adapter")
    activation = state.get("activation", {})
    if activation.get("capability_preflight", {}).get("connector_read_adapter_receipts") is not True:
        raise ScopeError("activation cannot prove connector adapter receipt enforcement")
    if service_receipt.get("activation_id") != activation.get("id"):
        raise ScopeError("connector adapter capability belongs to another activation")
    assert_repository_target(
        activation.get("repository", {}),
        str(service_receipt.get("repository", "")),
        target_repository_id=service_receipt.get("repository_id"),
    )
    orchestrator = activation.get("orchestrator_creation_receipt", {})
    if (
        service_receipt.get("orchestrator_thread_id") != activation.get("orchestrator_thread_id")
        or service_receipt.get("project_identity") != orchestrator.get("project_identity")
    ):
        raise ScopeError("connector adapter capability is not bound to the active Orchestrator project")
    adapter_id = service_receipt.get("adapter_id")
    if not isinstance(adapter_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}", adapter_id
    ):
        raise ValidationError("connector adapter ID is malformed")
    parse_utc_timestamp(service_receipt.get("created_at"), "connector adapter creation time")
    if not callable(read_connector):
        raise ValidationError("connector adapter callback is unavailable")
    return _GitHubConnectorReadAdapter(
        seal=_CONNECTOR_ADAPTER_SEAL,
        adapter_id=adapter_id,
        activation_id=str(activation["id"]),
        read=read_connector,
    )


class _ConnectorRefreshReceipt:
    """Process-local capability issued only after the connector read gateway validates a response."""

    __slots__ = (
        "_seal",
        "request",
        "service_receipt_id",
        "response_digest",
        "manifest",
        "snapshots",
        "snapshot_evidence",
    )

    def __init__(
        self,
        *,
        seal: object,
        request: Mapping[str, Any],
        service_receipt_id: str,
        response_digest: str,
        manifest: Mapping[str, Any],
        snapshots: Sequence[IssueSnapshot],
        snapshot_evidence: Sequence[Mapping[str, Any]],
    ) -> None:
        if seal is not _CONNECTOR_REFRESH_SEAL:
            raise ScopeError("connector refresh receipts can only be issued by the read gateway")
        self._seal = seal
        self.request = copy.deepcopy(dict(request))
        self.service_receipt_id = service_receipt_id
        self.response_digest = response_digest
        self.manifest = copy.deepcopy(dict(manifest))
        self.snapshots = tuple(snapshots)
        self.snapshot_evidence = copy.deepcopy(list(snapshot_evidence))


def _connector_refresh_request(
    state: Mapping[str, Any],
    *,
    refresh_timestamp: str,
    base_sha: str,
    adapter_id: str,
) -> dict[str, Any]:
    activation = state.get("activation", {})
    repository = activation.get("repository", {})
    request = {
        "operation": CONNECTOR_REFRESH_OPERATION,
        "adapter_id": adapter_id,
        "activation_id": activation.get("id"),
        "repository": repository.get("owner_name"),
        "repository_id": repository.get("repository_id"),
        "base_sha": require_full_sha(base_sha, "connector refresh base SHA"),
        "umbrella_issues": list(activation.get("umbrella_issues", [])),
        "refresh_timestamp": refresh_timestamp,
    }
    parse_utc_timestamp(refresh_timestamp, "selection refresh timestamp")
    if not isinstance(adapter_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}", adapter_id
    ):
        raise ValidationError("connector refresh adapter ID is malformed")
    if not isinstance(request["activation_id"], str) or not request["activation_id"]:
        raise ValidationError("connector refresh requires an active activation identity")
    normalize_owner_name(str(request["repository"]))
    require_positive_issue(request["repository_id"], "connector refresh repository ID")
    if not request["umbrella_issues"]:
        raise ValidationError("connector refresh requires an authorized umbrella scope")
    for umbrella in request["umbrella_issues"]:
        require_positive_issue(umbrella, "connector refresh umbrella")
    return request


def _require_connector_timestamp(value: Any, label: str, refresh_timestamp: str) -> str:
    parsed = parse_utc_timestamp(value, label)
    refresh = parse_utc_timestamp(refresh_timestamp, "selection refresh timestamp")
    if parsed != refresh:
        raise ScopeError(f"{label} is not bound to the complete refresh")
    return str(value)


def _validate_issue_evidence(
    state: Mapping[str, Any],
    snapshot: IssueSnapshot,
    *,
    refresh_timestamp: str,
) -> dict[str, Any]:
    evidence = snapshot.issue_evidence
    required = {
        "verified_by_connector",
        "repository",
        "repository_id",
        "issue",
        "revision",
        "state",
        "state_reason",
        "observed_at",
    }
    if not isinstance(evidence, Mapping) or set(evidence) != required:
        raise ValidationError("issue evidence must contain the exact connector receipt fields")
    activation = state["activation"]
    assert_repository_target(
        activation["repository"],
        str(evidence.get("repository", "")),
        target_repository_id=evidence.get("repository_id"),
    )
    if evidence.get("verified_by_connector") is not True:
        raise ScopeError("issue evidence was not verified by the connector")
    if require_positive_issue(evidence.get("issue")) != snapshot.issue:
        raise ScopeError("issue evidence identifies another issue")
    revision = require_content_digest(evidence.get("revision"), "issue evidence revision")
    issue_state = evidence.get("state")
    state_reason = evidence.get("state_reason")
    if issue_state not in {"open", "closed"}:
        raise ValidationError("issue evidence state must be open or closed")
    if issue_state == "open" and state_reason is not None:
        raise ValidationError("open issue evidence cannot have a close reason")
    if issue_state == "closed" and state_reason not in {"completed", "not_planned"}:
        raise ValidationError("closed issue evidence requires an exact close reason")
    if snapshot.open is not (issue_state == "open"):
        raise ScopeError("snapshot open flag differs from live connector issue state")
    observed_at = _require_connector_timestamp(
        evidence.get("observed_at"), "issue evidence timestamp", refresh_timestamp
    )
    normalized = {
        "verified_by_connector": True,
        "repository": normalize_owner_name(str(evidence["repository"])),
        "repository_id": evidence["repository_id"],
        "issue": snapshot.issue,
        "state": issue_state,
        "state_reason": state_reason,
        "observed_at": observed_at,
    }
    if revision != digest_json(normalized):
        raise ScopeError("issue evidence revision was not derived from the canonical connector receipt")
    return {**normalized, "revision": revision}


def _validate_membership_evidence(
    state: Mapping[str, Any],
    snapshot: IssueSnapshot,
    evidence: Mapping[str, Any],
    *,
    umbrella_revision: str,
    issue_revision: str,
    refresh_timestamp: str,
) -> dict[str, Any]:
    common = {
        "verified_by_connector",
        "source_type",
        "repository",
        "repository_id",
        "umbrella_issue",
        "umbrella_revision",
        "issue",
        "issue_revision",
        "observed_at",
    }
    source_type = evidence.get("source_type") if isinstance(evidence, Mapping) else None
    variant = {
        "formal-sub-issue": {"relationship_id"},
        "umbrella-body": {"section", "source_text"},
        "umbrella-body-list": {"source_text"},
        "owner-comment": {"comment_id", "author_id", "source_text"},
    }.get(source_type)
    if variant is None or set(evidence) != common | variant:
        raise ValidationError("membership evidence must be an exact supported connector receipt")
    activation = state["activation"]
    assert_repository_target(
        activation["repository"],
        str(evidence.get("repository", "")),
        target_repository_id=evidence.get("repository_id"),
    )
    if evidence.get("verified_by_connector") is not True:
        raise ScopeError("membership evidence was not verified by the connector")
    if require_positive_issue(evidence.get("umbrella_issue"), "membership umbrella") != snapshot.umbrella:
        raise ScopeError("membership evidence identifies another umbrella")
    if require_positive_issue(evidence.get("issue")) != snapshot.issue:
        raise ScopeError("membership evidence identifies another issue")
    if require_content_digest(evidence.get("umbrella_revision"), "membership umbrella revision") != umbrella_revision:
        raise ScopeError("membership evidence has a stale umbrella revision")
    if require_content_digest(evidence.get("issue_revision"), "membership issue revision") != issue_revision:
        raise ScopeError("membership evidence has a stale issue revision")
    observed_at = _require_connector_timestamp(
        evidence.get("observed_at"), "membership evidence timestamp", refresh_timestamp
    )
    normalized = {key: copy.deepcopy(evidence[key]) for key in common}
    normalized.update({key: copy.deepcopy(evidence[key]) for key in variant})
    normalized["repository"] = normalize_owner_name(str(evidence["repository"]))
    normalized["umbrella_issue"] = snapshot.umbrella
    normalized["issue"] = snapshot.issue
    normalized["observed_at"] = observed_at
    if source_type == "formal-sub-issue":
        relationship_id = evidence.get("relationship_id")
        if not isinstance(relationship_id, str) or not relationship_id.strip() or len(relationship_id) > 256:
            raise ValidationError("formal membership evidence requires a bounded relationship ID")
    else:
        source_text = evidence.get("source_text")
        if not isinstance(source_text, str) or not source_text.strip() or len(source_text) > 512:
            raise ValidationError("text membership evidence requires a bounded source excerpt")
        if snapshot.issue not in extract_same_repository_issue_numbers(source_text, snapshot.repository):
            raise ScopeError("membership source excerpt does not authorize the snapshot issue")
        if source_type == "umbrella-body":
            if evidence.get("section") not in {
                "sub-issues",
                "dependency matrix",
                "required implementation order",
                "implementation order",
            }:
                raise ScopeError("umbrella body evidence is outside an authorized scope section")
        elif source_type == "umbrella-body-list":
            if not re.match(
                r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?(?:#\d+\b|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+\b|https?://github\.com/)",
                source_text,
                re.IGNORECASE,
            ):
                raise ScopeError("umbrella list evidence is not an explicit issue list item")
        elif source_type == "owner-comment":
            require_positive_issue(evidence.get("comment_id"), "membership comment ID")
            if require_positive_issue(evidence.get("author_id"), "membership author ID") != activation["owner_actor"]["id"]:
                raise ScopeError("owner-comment membership evidence is not from the activation-bound actor")
            lowered = source_text.casefold()
            explicit = re.search(
                r"\b(?:add|include|link|authorize|sub[- ]?issue|implementation\s+order|dependency\s+matrix|in\s+scope)\b",
                lowered,
            ) or re.match(r"^\s*(?:[-*]|\d+[.)])\s*(?:\[[ xX]\]\s*)?#\d+", source_text)
            if _scope_line_is_negative(lowered) or not explicit:
                raise ScopeError("owner comment does not explicitly authorize membership")
    return normalized


def _validate_completion_evidence(
    state: Mapping[str, Any],
    snapshot: IssueSnapshot,
    evidence: Mapping[str, Any] | None,
    *,
    issue_revision: str,
    refresh_timestamp: str,
) -> dict[str, Any] | None:
    if evidence is None:
        return None
    required = {
        "verified_by_connector",
        "repository",
        "repository_id",
        "issue",
        "issue_revision",
        "issue_state",
        "issue_state_reason",
        "observed_at",
        "merged_pr",
    }
    if not isinstance(evidence, Mapping) or set(evidence) != required:
        raise ValidationError("completion evidence must contain exact live issue and PR receipts")
    activation = state["activation"]
    assert_repository_target(
        activation["repository"],
        str(evidence.get("repository", "")),
        target_repository_id=evidence.get("repository_id"),
    )
    if evidence.get("verified_by_connector") is not True:
        raise ScopeError("completion evidence was not verified by the connector")
    if require_positive_issue(evidence.get("issue")) != snapshot.issue:
        raise ScopeError("completion evidence identifies another issue")
    if require_content_digest(evidence.get("issue_revision"), "completion issue revision") != issue_revision:
        raise ScopeError("completion evidence has a stale issue revision")
    if evidence.get("issue_state") != "closed" or evidence.get("issue_state_reason") != "completed":
        raise ScopeError("completion requires live closed/completed issue evidence")
    observed_at = _require_connector_timestamp(
        evidence.get("observed_at"), "completion evidence timestamp", refresh_timestamp
    )
    pr = evidence.get("merged_pr")
    pr_required = {
        "number",
        "repository",
        "repository_id",
        "state",
        "merged",
        "head_sha",
        "merge_commit_sha",
        "observed_at",
    }
    if not isinstance(pr, Mapping) or set(pr) != pr_required:
        raise ValidationError("completion requires an exact merged PR connector receipt")
    assert_repository_target(
        activation["repository"],
        str(pr.get("repository", "")),
        target_repository_id=pr.get("repository_id"),
    )
    require_positive_issue(pr.get("number"), "completion PR number")
    if pr.get("state") != "closed" or pr.get("merged") is not True:
        raise ScopeError("completion requires a live closed and merged PR")
    head_sha = require_full_sha(pr.get("head_sha"), "completion PR head SHA")
    merge_sha = require_full_sha(pr.get("merge_commit_sha"), "completion PR merge commit SHA")
    pr_observed_at = _require_connector_timestamp(
        pr.get("observed_at"), "completion PR timestamp", refresh_timestamp
    )
    return {
        "verified_by_connector": True,
        "repository": normalize_owner_name(str(evidence["repository"])),
        "repository_id": evidence["repository_id"],
        "issue": snapshot.issue,
        "issue_revision": issue_revision,
        "issue_state": "closed",
        "issue_state_reason": "completed",
        "observed_at": observed_at,
        "merged_pr": {
            "number": pr["number"],
            "repository": normalize_owner_name(str(pr["repository"])),
            "repository_id": pr["repository_id"],
            "state": "closed",
            "merged": True,
            "head_sha": head_sha,
            "merge_commit_sha": merge_sha,
            "observed_at": pr_observed_at,
        },
    }


def snapshot_document(
    state: Mapping[str, Any],
    snapshot: IssueSnapshot,
    *,
    umbrella_revision: str,
    refresh_timestamp: str,
) -> dict[str, Any]:
    issue_evidence = _validate_issue_evidence(
        state, snapshot, refresh_timestamp=refresh_timestamp
    )
    memberships = [
        _validate_membership_evidence(
            state,
            snapshot,
            item,
            umbrella_revision=umbrella_revision,
            issue_revision=issue_evidence["revision"],
            refresh_timestamp=refresh_timestamp,
        )
        for item in snapshot.membership_evidence
    ]
    memberships.sort(key=canonical_json)
    if len(memberships) != len({canonical_json(item) for item in memberships}):
        raise ValidationError("snapshot membership evidence contains duplicates")
    completion = _validate_completion_evidence(
        state,
        snapshot,
        snapshot.completion_evidence,
        issue_revision=issue_evidence["revision"],
        refresh_timestamp=refresh_timestamp,
    )
    if snapshot.completion_verified and issue_evidence["state_reason"] != "completed":
        raise ScopeError("completion flag differs from live issue completion evidence")
    return {
        "issue": snapshot.issue,
        "umbrella": snapshot.umbrella,
        "repository": normalize_owner_name(snapshot.repository),
        "open": snapshot.open,
        "completion_verified": snapshot.completion_verified,
        "dependencies": list(snapshot.dependencies),
        "external_blockers": list(snapshot.external_blockers),
        "membership_evidence": memberships,
        "issue_evidence": issue_evidence,
        "completion_evidence": completion,
        "required_order_index": snapshot.required_order_index,
        "ambiguous_active_implementation": snapshot.ambiguous_active_implementation,
        "owner_priority": snapshot.owner_priority,
        "unlocks": snapshot.unlocks,
        "overlap_risk": snapshot.overlap_risk,
    }


def _snapshot_from_document(document: Mapping[str, Any]) -> IssueSnapshot:
    required = {
        "issue",
        "umbrella",
        "repository",
        "open",
        "completion_verified",
        "dependencies",
        "external_blockers",
        "membership_evidence",
        "issue_evidence",
        "completion_evidence",
        "required_order_index",
        "ambiguous_active_implementation",
        "owner_priority",
        "unlocks",
        "overlap_risk",
    }
    if not isinstance(document, Mapping) or set(document) != required:
        raise ValidationError("selection snapshot evidence requires exact canonical fields")
    try:
        return IssueSnapshot(
            issue=document["issue"],
            umbrella=document["umbrella"],
            repository=document["repository"],
            open=document["open"],
            completion_verified=document["completion_verified"],
            dependencies=tuple(document["dependencies"]),
            external_blockers=tuple(document["external_blockers"]),
            membership_evidence=tuple(document["membership_evidence"]),
            issue_evidence=document["issue_evidence"],
            completion_evidence=document["completion_evidence"],
            required_order_index=document["required_order_index"],
            ambiguous_active_implementation=document["ambiguous_active_implementation"],
            owner_priority=document["owner_priority"],
            unlocks=document["unlocks"],
            overlap_risk=document["overlap_risk"],
        )
    except (KeyError, TypeError) as exc:
        raise ValidationError("selection snapshot evidence is incomplete") from exc


def normalize_refresh_manifest(
    state: Mapping[str, Any],
    snapshots: Sequence[IssueSnapshot],
    manifest: Mapping[str, Any],
    *,
    refresh_timestamp: str,
) -> dict[str, Any]:
    required = {"repository", "repository_id", "base_sha", "refresh_timestamp", "umbrellas"}
    if not isinstance(manifest, Mapping) or set(manifest) != required:
        raise ValidationError("refresh manifest must contain the exact complete scope fields")
    parse_utc_timestamp(refresh_timestamp, "selection refresh timestamp")
    if manifest.get("refresh_timestamp") != refresh_timestamp:
        raise ScopeError("refresh manifest timestamp differs from the selection receipt")
    activation = state["activation"]
    assert_repository_target(
        activation["repository"],
        str(manifest.get("repository", "")),
        target_repository_id=manifest.get("repository_id"),
    )
    expected_base = activation.get("base_sha")
    task = state.get("task")
    current_selection = state.get("selection")
    if isinstance(task, Mapping) and isinstance(current_selection, Mapping) and current_selection.get("status") == "selected":
        expected_base = task.get("base_sha")
    if require_full_sha(manifest.get("base_sha"), "refresh base_sha") != expected_base:
        raise ScopeError("refresh manifest base differs from the activation")
    umbrella_entries = manifest.get("umbrellas")
    if not isinstance(umbrella_entries, list):
        raise ValidationError("refresh manifest umbrellas must be an ordered list")
    expected_umbrellas = list(activation.get("umbrella_issues", []))
    normalized_entries: list[dict[str, Any]] = []
    seen: list[int] = []
    discovered: dict[int, list[int]] = {}
    for entry in umbrella_entries:
        if not isinstance(entry, Mapping) or set(entry) != {
            "umbrella_issue",
            "umbrella_evidence",
            "umbrella_revision",
            "membership_evidence_digest",
            "discovered_issues",
            "complete",
        }:
            raise ValidationError("each umbrella refresh requires exact completeness evidence")
        umbrella = require_positive_issue(entry.get("umbrella_issue"), "refresh umbrella")
        revision = require_content_digest(
            entry.get("umbrella_revision"), "umbrella refresh revision"
        )
        umbrella_evidence = entry.get("umbrella_evidence")
        umbrella_required = {
            "verified_by_connector",
            "repository",
            "repository_id",
            "issue",
            "body_digest",
            "comments_digest",
            "formal_subissues_digest",
            "observed_at",
        }
        if not isinstance(umbrella_evidence, Mapping) or set(umbrella_evidence) != umbrella_required:
            raise ValidationError("umbrella refresh requires exact canonical connector evidence")
        assert_repository_target(
            activation["repository"],
            str(umbrella_evidence.get("repository", "")),
            target_repository_id=umbrella_evidence.get("repository_id"),
        )
        if umbrella_evidence.get("verified_by_connector") is not True:
            raise ScopeError("umbrella refresh evidence was not verified by the connector")
        if require_positive_issue(umbrella_evidence.get("issue"), "umbrella evidence issue") != umbrella:
            raise ScopeError("umbrella connector evidence identifies another issue")
        for digest_key in ("body_digest", "comments_digest", "formal_subissues_digest"):
            require_content_digest(umbrella_evidence.get(digest_key), f"umbrella {digest_key}")
        _require_connector_timestamp(
            umbrella_evidence.get("observed_at"),
            "umbrella evidence timestamp",
            refresh_timestamp,
        )
        normalized_umbrella_evidence = {
            **copy.deepcopy(dict(umbrella_evidence)),
            "repository": normalize_owner_name(str(umbrella_evidence["repository"])),
        }
        if revision != digest_json(normalized_umbrella_evidence):
            raise ScopeError("umbrella revision was not derived from canonical connector evidence")
        evidence_digest = require_content_digest(
            entry.get("membership_evidence_digest"),
            "membership evidence digest",
        )
        issues = entry.get("discovered_issues")
        if (
            not isinstance(issues, list)
            or any(require_positive_issue(item) == umbrella for item in issues)
            or len(issues) != len(set(issues))
        ):
            raise ScopeError("umbrella refresh contains an invalid or umbrella-as-task issue")
        if entry.get("complete") is not True:
            raise ScopeError("partial umbrella refresh cannot authorize selection or completion")
        seen.append(umbrella)
        discovered[umbrella] = list(issues)
        normalized_entries.append(
            {
                "umbrella_issue": umbrella,
                "umbrella_evidence": normalized_umbrella_evidence,
                "umbrella_revision": revision,
                "membership_evidence_digest": evidence_digest,
                "discovered_issues": list(issues),
                "complete": True,
            }
        )
    if seen != expected_umbrellas:
        raise ScopeError("refresh manifest must cover every authorized umbrella exactly once and in order")
    snapshot_issues: dict[int, list[int]] = {umbrella: [] for umbrella in expected_umbrellas}
    membership_by_umbrella: dict[int, list[dict[str, Any]]] = {
        umbrella: [] for umbrella in expected_umbrellas
    }
    revisions = {
        entry["umbrella_issue"]: entry["umbrella_revision"] for entry in normalized_entries
    }
    for snapshot in snapshots:
        if snapshot.issue == snapshot.umbrella:
            raise ScopeError("an umbrella issue cannot be dispatched as its own sub-issue")
        if snapshot.umbrella not in snapshot_issues:
            raise ScopeError("snapshot belongs to an unauthorized umbrella")
        document = snapshot_document(
            state,
            snapshot,
            umbrella_revision=revisions[snapshot.umbrella],
            refresh_timestamp=refresh_timestamp,
        )
        snapshot_issues[snapshot.umbrella].append(snapshot.issue)
        membership_by_umbrella[snapshot.umbrella].extend(document["membership_evidence"])
    for umbrella in expected_umbrellas:
        if sorted(discovered[umbrella]) != sorted(snapshot_issues[umbrella]):
            raise ScopeError("refresh manifest discovered issues differ from the complete snapshots")
        canonical_memberships = sorted(membership_by_umbrella[umbrella], key=canonical_json)
        expected_digest = digest_json(
            {
                "repository": normalize_owner_name(str(manifest["repository"])),
                "repository_id": manifest["repository_id"],
                "umbrella_issue": umbrella,
                "umbrella_revision": revisions[umbrella],
                "membership_evidence": canonical_memberships,
            }
        )
        supplied_digest = next(
            entry["membership_evidence_digest"]
            for entry in normalized_entries
            if entry["umbrella_issue"] == umbrella
        )
        if supplied_digest != expected_digest:
            raise ScopeError("membership evidence digest was not derived from canonical connector evidence")
    return {
        "repository": normalize_owner_name(str(manifest["repository"])),
        "repository_id": manifest["repository_id"],
        "base_sha": manifest["base_sha"],
        "refresh_timestamp": refresh_timestamp,
        "umbrellas": normalized_entries,
    }


def execute_connector_refresh(
    state: Mapping[str, Any],
    *,
    refresh_timestamp: str,
    adapter: _GitHubConnectorReadAdapter,
) -> _ConnectorRefreshReceipt:
    """Invoke the trusted connector-read adapter once and seal its exact response for selection."""
    if state.get("task") is not None:
        raise TransitionError("do not refresh selection while one task remains active")
    if state.get("phase") not in {"selecting-task", "scope-preflight", "waiting-dependency", "task-done"}:
        raise TransitionError("connector selection refresh is not allowed in the current phase")
    if (
        not isinstance(adapter, _GitHubConnectorReadAdapter)
        or adapter._seal is not _CONNECTOR_ADAPTER_SEAL
    ):
        raise ScopeError("connector refresh requires a service-issued GitHub adapter capability")
    activation = state.get("activation", {})
    if adapter.activation_id != activation.get("id"):
        raise ScopeError("connector read adapter belongs to another activation")
    request = _connector_refresh_request(
        state,
        refresh_timestamp=refresh_timestamp,
        base_sha=activation.get("base_sha"),
        adapter_id=adapter.adapter_id,
    )
    request_digest = digest_json(request)
    response = adapter.read(copy.deepcopy(request))
    required = {
        "verified_by_connector",
        "connector",
        "operation",
        "adapter_id",
        "request_digest",
        "service_receipt_id",
        "refresh_manifest",
        "snapshot_evidence",
        "response_digest",
    }
    if not isinstance(response, Mapping) or set(response) != required:
        raise ValidationError("connector refresh response requires exact service-returned fields")
    if response.get("verified_by_connector") is not True or response.get("connector") != "github":
        raise ScopeError("selection refresh did not originate from the GitHub connector adapter")
    if response.get("operation") != CONNECTOR_REFRESH_OPERATION:
        raise ScopeError("connector refresh response belongs to another operation")
    if response.get("adapter_id") != adapter.adapter_id:
        raise ScopeError("connector refresh response belongs to another service adapter")
    if response.get("request_digest") != request_digest:
        raise ScopeError("connector refresh response is not bound to the activation request")
    service_receipt_id = response.get("service_receipt_id")
    if not isinstance(service_receipt_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}", service_receipt_id
    ):
        raise ValidationError("connector refresh requires a bounded service receipt ID")
    evidence = response.get("snapshot_evidence")
    if not isinstance(evidence, list):
        raise ValidationError("connector refresh snapshot evidence must be an ordered list")
    snapshots = [_snapshot_from_document(item) for item in evidence]
    normalized_manifest = normalize_refresh_manifest(
        state,
        snapshots,
        response.get("refresh_manifest", {}),
        refresh_timestamp=refresh_timestamp,
    )
    umbrella_revisions = {
        entry["umbrella_issue"]: entry["umbrella_revision"]
        for entry in normalized_manifest["umbrellas"]
    }
    canonical_evidence = [
        snapshot_document(
            state,
            snapshot,
            umbrella_revision=umbrella_revisions[snapshot.umbrella],
            refresh_timestamp=refresh_timestamp,
        )
        for snapshot in snapshots
    ]
    if evidence != canonical_evidence:
        raise ScopeError("connector refresh response is not canonical")
    response_core = {
        "verified_by_connector": True,
        "connector": "github",
        "operation": CONNECTOR_REFRESH_OPERATION,
        "adapter_id": adapter.adapter_id,
        "request_digest": request_digest,
        "service_receipt_id": service_receipt_id,
        "refresh_manifest": normalized_manifest,
        "snapshot_evidence": canonical_evidence,
    }
    response_digest = require_content_digest(
        response.get("response_digest"), "connector refresh response digest"
    )
    if response_digest != digest_json(response_core):
        raise ScopeError("connector refresh response digest is invalid")
    return _ConnectorRefreshReceipt(
        seal=_CONNECTOR_REFRESH_SEAL,
        request=request,
        service_receipt_id=service_receipt_id,
        response_digest=response_digest,
        manifest=normalized_manifest,
        snapshots=snapshots,
        snapshot_evidence=canonical_evidence,
    )


def validate_selection_receipt(state: Mapping[str, Any], receipt: Mapping[str, Any]) -> None:
    required = {
        "refresh_timestamp",
        "refresh_manifest",
        "connector_refresh_receipt",
        "snapshot_evidence",
        "source_revisions",
        "eligible_candidates",
        "excluded_candidates",
        "dependency_edges",
        "required_order_positions",
        "selected_umbrella",
        "selected_issue",
        "tie_break",
        "base_sha",
        "activation_id",
        "status",
        "receipt_digest",
    }
    if not isinstance(receipt, Mapping) or set(receipt) != required:
        raise ValidationError("selection receipt is incomplete or hand-built")
    core = {key: copy.deepcopy(value) for key, value in receipt.items() if key != "receipt_digest"}
    if digest_json(core) != receipt.get("receipt_digest"):
        raise ScopeError("selection receipt digest is invalid")
    activation = state.get("activation", {})
    expected_base = activation.get("base_sha")
    task = state.get("task")
    if isinstance(task, Mapping) and receipt.get("status") == "selected":
        expected_base = task.get("base_sha")
    if receipt.get("activation_id") != activation.get("id") or receipt.get("base_sha") != expected_base:
        raise ScopeError("selection receipt activation or base identity is stale")
    evidence = receipt.get("snapshot_evidence")
    if not isinstance(evidence, list):
        raise ValidationError("selection snapshot evidence is malformed")
    snapshots: list[IssueSnapshot] = []
    for item in evidence:
        snapshots.append(_snapshot_from_document(item))
    normalized_manifest = normalize_refresh_manifest(
        state,
        snapshots,
        receipt.get("refresh_manifest", {}),
        refresh_timestamp=str(receipt.get("refresh_timestamp", "")),
    )
    connector_receipt = receipt.get("connector_refresh_receipt")
    connector_required = {
        "verified_by_connector",
        "connector",
        "operation",
        "adapter_id",
        "request_digest",
        "service_receipt_id",
        "response_digest",
    }
    if not isinstance(connector_receipt, Mapping) or set(connector_receipt) != connector_required:
        raise ValidationError("selection receipt lacks exact connector-origin proof")
    if (
        connector_receipt.get("verified_by_connector") is not True
        or connector_receipt.get("connector") != "github"
        or connector_receipt.get("operation") != CONNECTOR_REFRESH_OPERATION
    ):
        raise ScopeError("selection receipt was not produced by the GitHub connector refresh gateway")
    service_receipt_id = connector_receipt.get("service_receipt_id")
    if not isinstance(service_receipt_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}", service_receipt_id
    ):
        raise ValidationError("selection connector service receipt ID is malformed")
    adapter_id = connector_receipt.get("adapter_id")
    if not isinstance(adapter_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}", adapter_id
    ):
        raise ValidationError("selection connector adapter ID is malformed")
    expected_request = _connector_refresh_request(
        state,
        refresh_timestamp=str(receipt.get("refresh_timestamp", "")),
        base_sha=expected_base,
        adapter_id=adapter_id,
    )
    request_digest = digest_json(expected_request)
    if connector_receipt.get("request_digest") != request_digest:
        raise ScopeError("selection connector receipt is not bound to the activation request")
    response_core = {
        "verified_by_connector": True,
        "connector": "github",
        "operation": CONNECTOR_REFRESH_OPERATION,
        "adapter_id": adapter_id,
        "request_digest": request_digest,
        "service_receipt_id": service_receipt_id,
        "refresh_manifest": normalized_manifest,
        "snapshot_evidence": evidence,
    }
    response_digest = require_content_digest(
        connector_receipt.get("response_digest"), "selection connector response digest"
    )
    if response_digest != digest_json(response_core):
        raise ScopeError("selection connector response digest is invalid")
    expected_revisions = {
        str(item.issue): item.issue_evidence["revision"] for item in snapshots
    }
    if receipt.get("source_revisions") != expected_revisions:
        raise ScopeError("selection source revisions differ from the canonical snapshots")
    expected_decision = _recompute_selection_fields(state, snapshots)
    for key, expected in expected_decision.items():
        if receipt.get(key) != expected:
            raise ScopeError(f"selection decision field {key} was not deterministically derived")
    selected_issue = receipt.get("selected_issue")
    selected_umbrella = receipt.get("selected_umbrella")
    status = receipt.get("status")
    if status not in {"selected", "waiting-dependency", "complete"}:
        raise ValidationError("selection receipt status is invalid")
    if status == "selected":
        matches = [item for item in snapshots if item.issue == selected_issue and item.umbrella == selected_umbrella]
        if len(matches) != 1 or selected_issue not in receipt.get("eligible_candidates", []):
            raise ScopeError("selected task is not proven by the complete refresh evidence")
    elif selected_issue is not None or selected_umbrella is not None:
        raise ScopeError("non-selected refresh receipt cannot name a task")
    if status == "complete" and any(not item.completion_verified for item in snapshots):
        raise ScopeError("scope completion receipt contains incomplete discovered work")


def _find_cycle(graph: Mapping[int, set[int]]) -> list[int] | None:
    visiting: set[int] = set()
    visited: set[int] = set()
    stack: list[int] = []

    def visit(node: int) -> list[int] | None:
        if node in visiting:
            index = stack.index(node)
            return stack[index:] + [node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for dependency in sorted(graph.get(node, set())):
            if dependency in graph:
                cycle = visit(dependency)
                if cycle:
                    return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in sorted(graph):
        cycle = visit(node)
        if cycle:
            return cycle
    return None


def _recompute_selection_fields(
    state: Mapping[str, Any],
    snapshots: Sequence[IssueSnapshot],
) -> dict[str, Any]:
    activation = state.get("activation", {})
    current_repo = normalize_owner_name(activation.get("repository", {}).get("owner_name", ""))
    umbrella_order = list(activation.get("umbrella_issues", []))
    by_issue: dict[int, IssueSnapshot] = {}
    for snapshot in snapshots:
        if normalize_owner_name(snapshot.repository) != current_repo:
            raise ScopeError(f"snapshot #{snapshot.issue} belongs to another repository")
        if snapshot.umbrella not in umbrella_order:
            raise ScopeError(f"snapshot #{snapshot.issue} belongs to an unauthorized umbrella")
        if not snapshot.membership_evidence:
            raise ScopeError(f"snapshot #{snapshot.issue} has no authorized membership evidence")
        if snapshot.issue in by_issue:
            raise ValidationError(f"duplicate snapshot for issue #{snapshot.issue}")
        by_issue[snapshot.issue] = snapshot
    graph = {
        issue: set(snapshot.dependencies)
        for issue, snapshot in by_issue.items()
        if not snapshot.completion_verified
    }
    cycle = _find_cycle(graph)
    if cycle:
        raise SelectionBlocked("dependency cycle: " + " -> ".join(f"#{item}" for item in cycle))
    for snapshot in by_issue.values():
        if snapshot.required_order_index is None:
            continue
        for dependency in snapshot.dependencies:
            other = by_issue.get(dependency)
            if (
                other
                and other.umbrella == snapshot.umbrella
                and other.required_order_index is not None
                and other.required_order_index > snapshot.required_order_index
                and not other.completion_verified
            ):
                raise SelectionBlocked(
                    f"required-order contradiction: #{snapshot.issue} depends on later #{dependency}"
                )
    completed = {issue for issue, item in by_issue.items() if item.completion_verified}
    ambiguous = sorted(
        item.issue
        for item in by_issue.values()
        if item.ambiguous_active_implementation and item.issue not in completed
    )
    if ambiguous:
        raise SelectionBlocked(
            "ambiguous active implementation or PR ownership: "
            + ", ".join(f"#{issue}" for issue in ambiguous)
        )
    excluded: dict[str, list[str]] = {}
    eligible_heads: list[IssueSnapshot] = []
    for umbrella in umbrella_order:
        remaining = [
            item
            for item in by_issue.values()
            if item.umbrella == umbrella and item.issue not in completed
        ]
        if not remaining:
            continue
        ordered = [item for item in remaining if item.required_order_index is not None]
        heads = [min(ordered, key=lambda item: (item.required_order_index, item.issue))] if ordered else remaining
        head_ids = {item.issue for item in heads}
        for item in remaining:
            reasons: list[str] = []
            if item.issue not in head_ids:
                reasons.append("not the first incomplete required-order entry")
            if not item.open and not item.completion_verified:
                reasons.append("closed state lacks verified completion evidence")
            missing = [dependency for dependency in item.dependencies if dependency not in completed]
            if missing:
                reasons.append("waiting for dependencies " + ", ".join(f"#{number}" for number in sorted(missing)))
            if item.external_blockers:
                reasons.append("external dependency requires owner-safe evidence")
            if reasons:
                excluded[str(item.issue)] = reasons
            elif item.issue in head_ids:
                eligible_heads.append(item)
    dependency_targets = {
        dependency
        for snapshot in by_issue.values()
        for dependency in snapshot.dependencies
        if by_issue.get(dependency) and by_issue[dependency].umbrella != snapshot.umbrella
    }

    def rank(item: IssueSnapshot) -> tuple[int, int, int, int, int, int]:
        return (
            0 if item.issue in dependency_targets else 1,
            -item.unlocks,
            item.overlap_risk,
            -item.owner_priority,
            umbrella_order.index(item.umbrella),
            item.issue,
        )

    selected = min(eligible_heads, key=rank) if eligible_heads else None
    return {
        "eligible_candidates": [item.issue for item in sorted(eligible_heads, key=rank)],
        "excluded_candidates": excluded,
        "dependency_edges": sorted(
            (
                {"dependent": issue, "prerequisite": dependency}
                for issue, dependencies in graph.items()
                for dependency in dependencies
            ),
            key=lambda edge: (edge["dependent"], edge["prerequisite"]),
        ),
        "required_order_positions": {
            str(item.issue): item.required_order_index
            for item in snapshots
            if item.required_order_index is not None
        },
        "selected_umbrella": selected.umbrella if selected else None,
        "selected_issue": selected.issue if selected else None,
        "tie_break": "cross-dependency, unlocks, overlap-risk, owner-priority, umbrella-order, issue-number",
        "status": "selected" if selected else ("complete" if not graph else "waiting-dependency"),
    }


def select_next_task(
    state: MutableMapping[str, Any],
    refresh_receipt: _ConnectorRefreshReceipt,
) -> dict[str, Any]:
    """Atomically bind one connector-gateway-sealed refresh decision into active state."""
    if state.get("task") is not None:
        raise TransitionError("do not select another task while one task remains active")
    if state.get("phase") not in {"selecting-task", "scope-preflight", "waiting-dependency", "task-done"}:
        raise TransitionError("task selection is not allowed in the current phase")
    activation = state.get("activation", {})
    if (
        not isinstance(refresh_receipt, _ConnectorRefreshReceipt)
        or refresh_receipt._seal is not _CONNECTOR_REFRESH_SEAL
    ):
        raise ScopeError("task selection requires an opaque connector refresh gateway receipt")
    refresh_timestamp = str(refresh_receipt.request.get("refresh_timestamp", ""))
    expected_request = _connector_refresh_request(
        state,
        refresh_timestamp=refresh_timestamp,
        base_sha=activation.get("base_sha"),
        adapter_id=str(refresh_receipt.request.get("adapter_id", "")),
    )
    if refresh_receipt.request != expected_request:
        raise ScopeError("connector refresh receipt is stale for the active selection request")
    snapshots = refresh_receipt.snapshots
    refresh_manifest = refresh_receipt.manifest
    current_repo = normalize_owner_name(activation.get("repository", {}).get("owner_name", ""))
    umbrella_order = list(activation.get("umbrella_issues", []))
    if not umbrella_order:
        raise ValidationError("activation has no umbrella scope")
    normalized_manifest = normalize_refresh_manifest(
        state,
        snapshots,
        refresh_manifest,
        refresh_timestamp=refresh_timestamp,
    )
    if normalized_manifest != refresh_receipt.manifest:
        raise ScopeError("connector refresh manifest changed after gateway validation")
    by_issue: dict[int, IssueSnapshot] = {}
    for snapshot in snapshots:
        if normalize_owner_name(snapshot.repository) != current_repo:
            raise ScopeError(f"snapshot #{snapshot.issue} belongs to another repository")
        if snapshot.umbrella not in umbrella_order:
            raise ScopeError(f"snapshot #{snapshot.issue} belongs to an unauthorized umbrella")
        if not snapshot.membership_evidence:
            raise ScopeError(f"snapshot #{snapshot.issue} has no authorized membership evidence")
        if snapshot.issue in by_issue:
            raise ValidationError(f"duplicate snapshot for issue #{snapshot.issue}")
        by_issue[snapshot.issue] = snapshot

    graph = {
        issue: set(snapshot.dependencies)
        for issue, snapshot in by_issue.items()
        if not snapshot.completion_verified
    }
    cycle = _find_cycle(graph)
    if cycle:
        raise SelectionBlocked("dependency cycle: " + " -> ".join(f"#{item}" for item in cycle))

    for snapshot in by_issue.values():
        if snapshot.required_order_index is None:
            continue
        for dependency in snapshot.dependencies:
            other = by_issue.get(dependency)
            if (
                other
                and other.umbrella == snapshot.umbrella
                and other.required_order_index is not None
                and other.required_order_index > snapshot.required_order_index
                and not other.completion_verified
            ):
                raise SelectionBlocked(
                    f"required-order contradiction: #{snapshot.issue} depends on later #{dependency}"
                )

    completed = {issue for issue, item in by_issue.items() if item.completion_verified}
    ambiguous = sorted(
        item.issue
        for item in by_issue.values()
        if item.ambiguous_active_implementation and item.issue not in completed
    )
    if ambiguous:
        raise SelectionBlocked(
            "ambiguous active implementation or PR ownership: "
            + ", ".join(f"#{issue}" for issue in ambiguous)
        )
    excluded: dict[str, list[str]] = {}
    eligible_heads: list[IssueSnapshot] = []

    for umbrella in umbrella_order:
        remaining = [
            item
            for item in by_issue.values()
            if item.umbrella == umbrella and item.issue not in completed
        ]
        if not remaining:
            continue
        ordered = [item for item in remaining if item.required_order_index is not None]
        heads = [min(ordered, key=lambda item: (item.required_order_index, item.issue))] if ordered else remaining
        head_ids = {item.issue for item in heads}
        for item in remaining:
            reasons: list[str] = []
            if item.issue not in head_ids:
                reasons.append("not the first incomplete required-order entry")
            if not item.open and not item.completion_verified:
                reasons.append("closed state lacks verified completion evidence")
            missing = [dependency for dependency in item.dependencies if dependency not in completed]
            if missing:
                reasons.append("waiting for dependencies " + ", ".join(f"#{number}" for number in sorted(missing)))
            if item.external_blockers:
                reasons.append("external dependency requires owner-safe evidence")
            if reasons:
                excluded[str(item.issue)] = reasons
            elif item.issue in head_ids:
                eligible_heads.append(item)

    active_issue = (state.get("task") or {}).get("issue")
    if active_issue is not None:
        eligible_heads = [item for item in eligible_heads if item.issue != active_issue]
        excluded.setdefault(str(active_issue), []).append("already active")

    dependency_targets = {
        dependency
        for snapshot in by_issue.values()
        for dependency in snapshot.dependencies
        if by_issue.get(dependency) and by_issue[dependency].umbrella != snapshot.umbrella
    }

    def rank(item: IssueSnapshot) -> tuple[int, int, int, int, int, int]:
        return (
            0 if item.issue in dependency_targets else 1,
            -item.unlocks,
            item.overlap_risk,
            -item.owner_priority,
            umbrella_order.index(item.umbrella),
            item.issue,
        )

    selected = min(eligible_heads, key=rank) if eligible_heads else None
    dependency_edges = sorted(
        ({"dependent": issue, "prerequisite": dependency} for issue, deps in graph.items() for dependency in deps),
        key=lambda edge: (edge["dependent"], edge["prerequisite"]),
    )
    umbrella_revisions = {
        entry["umbrella_issue"]: entry["umbrella_revision"]
        for entry in normalized_manifest["umbrellas"]
    }
    snapshot_evidence = [
        snapshot_document(
            state,
            item,
            umbrella_revision=umbrella_revisions[item.umbrella],
            refresh_timestamp=refresh_timestamp,
        )
        for item in snapshots
    ]
    if snapshot_evidence != refresh_receipt.snapshot_evidence:
        raise ScopeError("connector snapshot evidence changed after gateway validation")
    request_digest = digest_json(expected_request)
    connector_response_core = {
        "verified_by_connector": True,
        "connector": "github",
        "operation": CONNECTOR_REFRESH_OPERATION,
        "adapter_id": expected_request["adapter_id"],
        "request_digest": request_digest,
        "service_receipt_id": refresh_receipt.service_receipt_id,
        "refresh_manifest": normalized_manifest,
        "snapshot_evidence": snapshot_evidence,
    }
    if refresh_receipt.response_digest != digest_json(connector_response_core):
        raise ScopeError("connector refresh receipt lost its response binding")
    receipt = {
        "refresh_timestamp": refresh_timestamp,
        "refresh_manifest": normalized_manifest,
        "connector_refresh_receipt": {
            "verified_by_connector": True,
            "connector": "github",
            "operation": CONNECTOR_REFRESH_OPERATION,
            "adapter_id": expected_request["adapter_id"],
            "request_digest": request_digest,
            "service_receipt_id": refresh_receipt.service_receipt_id,
            "response_digest": refresh_receipt.response_digest,
        },
        "snapshot_evidence": snapshot_evidence,
        "source_revisions": {
            str(item.issue): item.issue_evidence["revision"] for item in snapshots
        },
        "eligible_candidates": [item.issue for item in sorted(eligible_heads, key=rank)],
        "excluded_candidates": excluded,
        "dependency_edges": dependency_edges,
        "required_order_positions": {
            str(item.issue): item.required_order_index
            for item in snapshots
            if item.required_order_index is not None
        },
        "selected_umbrella": selected.umbrella if selected else None,
        "selected_issue": selected.issue if selected else None,
        "tie_break": "cross-dependency, unlocks, overlap-risk, owner-priority, umbrella-order, issue-number",
        "base_sha": activation.get("base_sha"),
        "activation_id": activation.get("id"),
        "status": "selected" if selected else ("complete" if not graph else "waiting-dependency"),
    }
    receipt["receipt_digest"] = digest_json(receipt)
    if len(canonical_json(receipt).encode("utf-8")) > 65536:
        raise ValidationError("selection receipt exceeds the bounded state limit")
    state["selection"] = copy.deepcopy(receipt)
    current_phase = state.get("phase")
    if current_phase != "selecting-task":
        transition_state(state, "selecting-task")
    if receipt["status"] == "waiting-dependency":
        transition_state(state, "waiting-dependency")
    elif receipt["status"] == "complete":
        transition_state(state, "scope-complete")
    validate_selection_receipt(state, receipt)
    return receipt


def validate_mailbox_shape(payload: Mapping[str, Any], kind: str) -> None:
    if kind not in MAILBOX_NAMES:
        raise MailboxError("unknown mailbox kind")
    if not isinstance(payload, Mapping):
        raise MailboxError("mailbox payload must be an object")
    required = {
        "protocol_version",
        "review_contract_version",
        "activation_id",
        "repository",
        "repository_id",
        "selected_issue",
        "source_role",
        "source_thread_id",
        "phase",
        "base_sha",
        "candidate_sha",
        "idempotency_key",
        "timestamp",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise MailboxError("mailbox fields missing: " + ", ".join(missing))
    key = payload["idempotency_key"]
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,200}", key):
        raise MailboxError("mailbox idempotency key is malformed")
    mailbox_sequence(key)
    if len(canonical_json(payload).encode("utf-8")) > MAX_MAILBOX_BYTES:
        raise MailboxError("mailbox payload exceeds the bounded artifact limit")


def mailbox_sequence(idempotency_key: str) -> int:
    match = re.search(r"(\d+)$", idempotency_key)
    if not match:
        raise MailboxError("mailbox idempotency key must end with a monotonic decimal sequence")
    sequence = int(match.group(1))
    if sequence <= 0:
        raise MailboxError("mailbox idempotency sequence must be positive")
    return sequence


def validate_mailbox_envelope(payload: Mapping[str, Any], state: Mapping[str, Any], kind: str) -> None:
    validate_mailbox_shape(payload, kind)
    if payload["protocol_version"] != state["versions"]["protocol"]:
        raise MailboxError("mailbox protocol version mismatch")
    if payload["review_contract_version"] != state["versions"]["review_contract"]:
        raise MailboxError("mailbox review contract mismatch")
    if payload["activation_id"] != state["activation"]["id"]:
        raise MailboxError("mailbox activation mismatch")
    try:
        assert_repository_target(
            state["activation"]["repository"],
            str(payload["repository"]),
            target_repository_id=payload["repository_id"],
        )
    except (ScopeError, ValidationError) as exc:
        raise MailboxError(str(exc)) from exc
    if kind == "github-context":
        selection = state.get("selection")
        if state["activation"]["allowed_operations"].get("create_task_branches") is not True:
            raise MailboxError("Worker branch and task creation were not authorized")
        if state.get("phase") != "selecting-task" or not isinstance(selection, Mapping):
            raise MailboxError("GitHub context requires a durable pre-dispatch selection")
        if payload["phase"] != "selecting-task":
            raise MailboxError("GitHub context phase mismatch")
        if payload["selected_issue"] != selection.get("selected_issue"):
            raise MailboxError("GitHub context selected issue mismatch")
        if payload["base_sha"] != state["activation"].get("base_sha"):
            raise MailboxError("GitHub context base SHA mismatch")
        if payload["candidate_sha"] is not None:
            raise MailboxError("pre-dispatch GitHub context cannot claim a candidate")
        if payload["source_role"] != "orchestrator":
            raise MailboxError("github-context must come from the orchestrator")
        if payload["source_thread_id"] != state["activation"].get("orchestrator_thread_id"):
            raise MailboxError("GitHub context source thread mismatch")
        return
    task = state.get("task") or {}
    if payload["selected_issue"] != task.get("issue"):
        raise MailboxError("mailbox selected task mismatch")
    if payload["phase"] != state["phase"]:
        raise MailboxError("mailbox phase mismatch")
    if payload["base_sha"] != task.get("base_sha"):
        raise MailboxError("mailbox base SHA mismatch")
    phase = state.get("phase")
    role = payload["source_role"]
    expected_roles = {
        "github-context": "orchestrator",
        "worker-handoff": "worker",
        "supervisor-review": "supervisor",
    }
    if role != expected_roles[kind]:
        raise MailboxError(f"{kind} must come from the {expected_roles[kind]}")
    if kind == "worker-handoff":
        require_full_sha(payload["candidate_sha"], "Worker handoff candidate_sha")
        if phase not in {
            "worker-running",
            "worker-repair",
            "pass-follow-up",
            "ready",
            "maintenance-requested",
        }:
            raise MailboxError("Worker handoff is not accepted in this phase")
        if task.get("active_role") != "worker":
            raise MailboxError("Worker handoff requires the active Worker role")
        if phase == "worker-running" and state["activation"]["allowed_operations"].get("create_draft_prs") is not True:
            raise MailboxError("draft PR creation was not authorized before Worker handoff consumption")
        if phase == "ready" and payload["candidate_sha"] != task.get("candidate_sha"):
            raise MailboxError("final Worker handoff candidate SHA mismatch")
    elif kind == "supervisor-review":
        if phase not in {"supervisor-running", "final-supervisor"}:
            raise MailboxError("Supervisor review is not accepted in this phase")
        if task.get("active_role") != "supervisor":
            raise MailboxError("Supervisor review requires the active Supervisor role")
        if payload["candidate_sha"] != task.get("candidate_sha"):
            raise MailboxError("mailbox candidate SHA mismatch")
    if role == "worker":
        expected_thread = task.get("worker_thread_id")
    elif role == "supervisor":
        expected_thread = state["review"].get("current_supervisor_thread_id")
    else:
        expected_thread = state["activation"].get("orchestrator_thread_id")
    if payload["source_thread_id"] != expected_thread:
        raise MailboxError("mailbox source thread mismatch")


class MailboxStore:
    def __init__(self, state_directory: str | os.PathLike[str]):
        self.directory = Path(state_directory) / "mailbox"

    def path(self, kind: str) -> Path:
        if kind not in MAILBOX_NAMES:
            raise MailboxError("unknown mailbox kind")
        return self.directory / MAILBOX_NAMES[kind]

    def write(self, kind: str, payload: Mapping[str, Any], state: Mapping[str, Any]) -> None:
        validate_mailbox_shape(payload, kind)
        key = payload["idempotency_key"]
        payload_digest = digest_json(payload)
        existing_receipt = state.get("receipts", {}).get(key)
        if isinstance(existing_receipt, Mapping):
            if existing_receipt.get("kind") != kind or existing_receipt.get("payload_digest") != payload_digest:
                raise MailboxError("idempotency key is bound to another mailbox payload")
            if existing_receipt.get("status") == "complete":
                return
        elif mailbox_sequence(key) <= state["mailbox_high_water"][kind]:
            raise MailboxError("mailbox idempotency key was already consumed and archived")
        elif mailbox_sequence(key) != state["mailbox_high_water"][kind] + 1:
            raise MailboxError("mailbox idempotency sequence must be the next value for its kind")
        validate_mailbox_envelope(payload, state, kind)
        path = self.path(kind)
        if path.exists():
            existing = read_json(path, max_bytes=MAX_MAILBOX_BYTES)
            if canonical_json(existing) == canonical_json(payload):
                return
            raise MailboxError("cannot overwrite an unread mailbox payload")
        atomic_write_json(path, payload, max_bytes=MAX_MAILBOX_BYTES)

    def consume(
        self,
        kind: str,
        state_store: StateStore,
        *,
        mutate: Callable[[Mapping[str, Any]], Mapping[str, Any]],
        reconcile: Callable[[Mapping[str, Any]], Mapping[str, Any] | bool | None] | None = None,
        advance: Callable[[MutableMapping[str, Any], Mapping[str, Any], Mapping[str, Any]], None]
        | None = None,
    ) -> Mapping[str, Any]:
        mailbox_path = self.path(kind)
        with state_store.single_writer():
            payload = read_json(mailbox_path, max_bytes=MAX_MAILBOX_BYTES)
            state = state_store.load()
            validate_mailbox_shape(payload, kind)
            key = payload["idempotency_key"]
            payload_digest = digest_json(payload)
            existing = state.get("receipts", {}).get(key)
            if existing is not None:
                if existing.get("kind") != kind or existing.get("payload_digest") != payload_digest:
                    raise MailboxError("idempotency key is bound to another mailbox payload")
                if existing.get("status") == "complete":
                    try:
                        mailbox_path.unlink()
                    except FileNotFoundError:
                        pass
                    return existing["receipt"]
            elif mailbox_sequence(key) <= state["mailbox_high_water"][kind]:
                raise MailboxError("mailbox idempotency key was already consumed and archived")
            elif mailbox_sequence(key) != state["mailbox_high_water"][kind] + 1:
                raise MailboxError("mailbox idempotency sequence must be the next value for its kind")
            validate_mailbox_envelope(payload, state, kind)
            if existing is not None:
                if existing.get("status") != "pending" or reconcile is None:
                    raise MailboxError("pending mailbox mutation requires deterministic reconciliation")
                reconciled = reconcile(payload)
                if reconciled is None:
                    raise MailboxError("mailbox mutation identity is ambiguous after interruption")
                if reconciled is False:
                    receipt = mutate(payload)
                elif isinstance(reconciled, Mapping):
                    receipt = reconciled
                else:
                    raise MailboxError("mailbox reconciliation result is invalid")
            else:
                state_store.begin_mailbox_intent(key, kind, payload_digest)
                receipt = mutate(payload)
            if not isinstance(receipt, Mapping) or not receipt:
                raise MailboxError("mutation receipt is missing or ambiguous")
            state_store.complete_mailbox_intent(
                key,
                kind,
                payload_digest,
                receipt,
                update=(lambda current: advance(current, payload, receipt)) if advance is not None else None,
            )
            try:
                mailbox_path.unlink()
            except FileNotFoundError:
                pass
            return receipt

    def discard_github_context_after_dispatch(self) -> None:
        path = self.path("github-context")
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def compact_completed_task(
    state: MutableMapping[str, Any],
    *,
    issue_url: str,
    pr_url: str,
    merge_sha: str,
    completed_at: str | None = None,
) -> None:
    if state.get("phase") != "task-done":
        raise TransitionError("compact a task only after task-done")
    task = state.get("task")
    if not isinstance(task, Mapping):
        raise ValidationError("completed task is missing")
    merge = require_full_sha(merge_sha, "merge_sha")
    state.setdefault("completed_tasks", []).append(
        {
            "umbrella_issue": task["umbrella_issue"],
            "issue": task["issue"],
            "issue_url": issue_url,
            "pr_url": pr_url,
            "merge_sha": merge,
            "review_rounds": state["review"]["round"],
            "completed_at": completed_at or utc_now(),
            "final_status": "merged",
        }
    )
    state["task"] = None
    state["selection"] = None
    state["review"] = {
        "round": 0,
        "last_result": None,
        "pass_identity": None,
        "current_supervisor_thread_id": None,
        "supervisor_thread_ids": [],
        "supervisor_creation_receipts": [],
        "unarchived_supervisor_thread_ids": [],
        "archived_supervisor_count": 0,
        "archived_supervisor_digest": "0" * 64,
        "last_supervisor_created_at": None,
    }
    receipts = state.get("receipts", {})
    if any(receipt.get("status") != "complete" for receipt in receipts.values()):
        raise MailboxError("complete or reconcile every mailbox intent before task compaction")
    if receipts:
        entries = [
            {"idempotency_key": key, **copy.deepcopy(dict(receipt))}
            for key, receipt in sorted(receipts.items())
        ]
        state["receipt_archive"]["digest"] = fold_archive_digest(
            state["receipt_archive"]["digest"],
            entries,
        )
        state["receipt_archive"]["count"] += len(entries)
    state["receipts"] = {}
    if state.get("github_mutations", {}).get("pending") is not None:
        raise MailboxError("reconcile the pending GitHub mutation before task compaction")
    state["github_mutations"] = {"pending": None, "receipts": {}}
    state["maintenance"]["pending_action"] = None


def compact_scope(
    state: MutableMapping[str, Any],
    state_directory: str | os.PathLike[str],
    *,
    completed_at: str | None = None,
) -> dict[str, Any]:
    if state.get("phase") != "scope-complete" or state.get("task") is not None:
        raise TransitionError("scope compaction requires scope-complete with no active task")
    timestamp = completed_at or utc_now()
    summary = {
        "activation_id": state["activation"]["id"],
        "scope_started_at": state["activation"]["started_at"],
        "scope_completed_at": timestamp,
        "umbrella_issues": state["activation"]["umbrella_issues"],
        "completed_tasks": copy.deepcopy(state.get("completed_tasks", [])),
        "final_result": "scope-complete",
    }
    directory = Path(state_directory)
    atomic_write_json(directory / SUMMARY_FILENAME, summary, max_bytes=MAX_STATE_BYTES)
    mailbox = directory / "mailbox"
    if mailbox.exists():
        for name in MAILBOX_NAMES.values():
            try:
                (mailbox / name).unlink()
            except FileNotFoundError:
                pass
    compacted = {
        "skill": copy.deepcopy(state["skill"]),
        "versions": copy.deepcopy(state["versions"]),
        "activation": copy.deepcopy(state["activation"]),
        "phase": "scope-complete",
        "selection": copy.deepcopy(state["selection"]),
        "task": None,
        "review": {
            "round": 0,
            "last_result": None,
            "pass_identity": None,
            "current_supervisor_thread_id": None,
            "supervisor_thread_ids": [],
            "supervisor_creation_receipts": [],
            "unarchived_supervisor_thread_ids": [],
            "archived_supervisor_count": 0,
            "archived_supervisor_digest": "0" * 64,
            "last_supervisor_created_at": None,
        },
        "receipts": {},
        "github_mutations": {"pending": None, "receipts": {}},
        "receipt_archive": {"count": 0, "digest": "0" * 64},
        "mailbox_high_water": {kind: 0 for kind in sorted(MAILBOX_NAMES)},
        "maintenance": {
            "requested": False,
            "reason": None,
            "checkpoint_id": None,
            "previous_phase": None,
            "schedule_id": state.get("maintenance", {}).get("schedule_id"),
            "schedule_state": "paused",
            "stored_versions": None,
            "pending_action": None,
            "resume_worker": False,
            "migrated_from_versions": None,
            "migration_receipt": None,
        },
        "retry": None,
        "blocker": None,
        "completed_tasks": [],
        "summary_pointer": SUMMARY_FILENAME,
        "timestamps": {
            "created_at": state["timestamps"]["created_at"],
            "updated_at": timestamp,
        },
    }
    atomic_write_json(directory / STATE_FILENAME, compacted, max_bytes=MAX_STATE_BYTES)
    return summary


def skill_content_digest(skill_root: str | os.PathLike[str]) -> str:
    root = Path(skill_root).resolve()
    if not (root / "SKILL.md").is_file():
        raise ValidationError("skill root does not contain SKILL.md")
    hasher = hashlib.sha256()
    included_roots = {"SKILL.md", "agents", "scripts", "references", "assets"}
    files = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.relative_to(root).parts[0] in included_roots
        and "__pycache__" not in path.parts
        and not path.name.endswith((".pyc", ".pyo"))
    ]
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        hasher.update(len(relative).to_bytes(8, "big"))
        hasher.update(relative)
        data = path.read_bytes()
        hasher.update(len(data).to_bytes(8, "big"))
        hasher.update(data)
    return hasher.hexdigest()


def exact_worktree_branch_from_porcelain(porcelain: str, worktree: Path) -> str | None:
    """Return one exact branch ref for a listed worktree, rejecting ambiguous records."""
    expected = f"worktree {worktree.resolve()}"
    matches: list[list[str]] = []
    for record in re.split(r"\n\s*\n", porcelain.strip()):
        lines = [line for line in record.splitlines() if line]
        if lines and lines[0] == expected:
            matches.append(lines)
    if len(matches) > 1:
        raise GuardError("recorded worktree appears more than once in porcelain identity")
    if not matches:
        return None
    branches = [line.removeprefix("branch ") for line in matches[0] if line.startswith("branch ")]
    if len(branches) != 1:
        return None
    return branches[0]


class GuardedGit:
    def __init__(
        self,
        state_store: StateStore,
        *,
        activation_id: str,
        installed_digest: str,
        skill_root: str | os.PathLike[str],
        runner: CommandRunner | None = None,
    ):
        self.store = state_store
        self.state = state_store.load()
        self.runner = runner or CommandRunner()
        if activation_id != self.state["activation"]["id"]:
            raise GuardError("activation ID does not match guarded state")
        digest = require_content_digest(installed_digest)
        if digest != self.state["skill"]["content_digest"]:
            raise GuardError("installed digest does not match guarded state")
        if skill_content_digest(skill_root) != digest:
            raise GuardError("installed skill content does not match the declared digest")
        repo = self.state["activation"]["repository"]
        identity = resolve_repository_identity(
            repo["git_root"],
            self.state["activation"]["base_branch"],
            repository_id=repo.get("repository_id"),
            require_synchronized=False,
            runner=self.runner,
        )
        assert_repository_target(repo, identity.owner_name, target_repository_id=identity.repository_id)
        if identity.git_common_dir_fingerprint != repo["git_common_dir_fingerprint"]:
            raise GuardError("Git common directory identity changed")
        if identity.origin_fingerprint != repo["origin_fingerprint"]:
            raise GuardError("origin identity changed")
        if identity.origin_push_fingerprint != repo["origin_push_fingerprint"]:
            raise GuardError("origin push identity changed")
        if identity.current_branch not in {"", self.state["activation"]["base_branch"]}:
            raise GuardError("orchestration checkout is on an unrelated branch")
        self.identity = identity

    def _assert_effective_base_identity(self, identity: RepositoryIdentity, root: Path) -> None:
        if Path(identity.git_root).resolve() != root.resolve() or not repository_identity_has_effective_base(identity):
            raise GuardError("orchestration checkout is not the exact effective remote base")

    def refresh_base(self) -> None:
        if self.state.get("phase") not in {
            "scope-preflight",
            "selecting-task",
            "waiting-dependency",
            "task-done",
        }:
            raise GuardError("base refresh is not allowed in the current phase")
        if self.state.get("task") is not None and self.state.get("phase") != "task-done":
            raise GuardError("do not refresh for selection while an active task exists")
        root = Path(self.identity.git_root)
        base = self.state["activation"]["base_branch"]
        self.runner.run(["git", "fetch", "origin", base], root)
        current = self.runner.run(["git", "branch", "--show-current"], root)
        if current not in {"", base}:
            raise GuardError("orchestration checkout is on an unrelated branch")
        self.runner.run(["git", "merge", "--ff-only", f"origin/{base}"], root)
        refreshed = resolve_repository_identity(
            root,
            base,
            repository_id=self.state["activation"]["repository"].get("repository_id"),
            require_synchronized=False,
            runner=self.runner,
        )
        if (
            refreshed.git_common_dir_fingerprint != self.identity.git_common_dir_fingerprint
            or refreshed.origin_fingerprint != self.identity.origin_fingerprint
            or refreshed.origin_push_fingerprint != self.identity.origin_push_fingerprint
        ):
            raise GuardError("repository identity changed during base refresh")
        self._assert_effective_base_identity(refreshed, root)
        self.state["activation"]["base_sha"] = refreshed.remote_base_sha
        self.store.save(self.state)

    def push_task_branch(self) -> None:
        if self.state["activation"]["allowed_operations"].get("create_task_branches") is not True:
            raise GuardError("task branch operation is not authorized")
        task = self.state.get("task")
        if not isinstance(task, Mapping):
            raise GuardError("no active task owns a branch")
        if self.state.get("phase") not in {"worker-running", "worker-repair", "pass-follow-up"}:
            raise GuardError("task push is not allowed in the current phase")
        if self.state.get("maintenance", {}).get("requested"):
            raise GuardError("task push is forbidden while maintenance is pending")
        if task.get("active_role") is not None:
            raise GuardError("task push requires a completed immutable Worker handoff")
        branch = validate_branch_name(task.get("branch"))
        if not branch.startswith("codex/"):
            raise GuardError("recorded task branch is outside codex/")
        worktree = Path(task.get("worktree", "")).resolve()
        repo = self.state["activation"]["repository"]
        worktree_identity = resolve_repository_identity(
            worktree,
            self.state["activation"]["base_branch"],
            repository_id=repo.get("repository_id"),
            require_synchronized=False,
            runner=self.runner,
        )
        assert_repository_target(
            repo,
            worktree_identity.owner_name,
            target_repository_id=worktree_identity.repository_id,
        )
        if Path(worktree_identity.git_root).resolve() != worktree:
            raise GuardError("recorded task worktree path is not its resolved Git root")
        if worktree_identity.git_common_dir_fingerprint != repo["git_common_dir_fingerprint"]:
            raise GuardError("task worktree belongs to another Git common directory")
        if (
            worktree_identity.origin_fingerprint != repo["origin_fingerprint"]
            or worktree_identity.origin_push_fingerprint != repo["origin_push_fingerprint"]
        ):
            raise GuardError("task worktree origin differs from the activation")
        current = self.runner.run(["git", "branch", "--show-current"], worktree)
        if current != branch:
            raise GuardError("task worktree is not on the recorded branch")
        head = require_full_sha(self.runner.run(["git", "rev-parse", "HEAD"], worktree), "task HEAD")
        if head != task.get("candidate_sha"):
            raise GuardError("task HEAD differs from the recorded candidate")
        base = require_full_sha(task.get("base_sha"), "task base_sha")
        self.runner.run(["git", "merge-base", "--is-ancestor", base, head], worktree)
        self.runner.run(["git", "push", "origin", branch], worktree)

    def sync_base(self) -> None:
        if self.state.get("phase") != "sync-base":
            raise GuardError("base sync is allowed only in sync-base")
        root = Path(self.identity.git_root)
        base = self.state["activation"]["base_branch"]
        self.runner.run(["git", "fetch", "origin", base], root)
        current = self.runner.run(["git", "branch", "--show-current"], root)
        if current not in {"", base}:
            raise GuardError("orchestration checkout is on an unrelated branch")
        self.runner.run(["git", "merge", "--ff-only", f"origin/{base}"], root)
        head = require_full_sha(self.runner.run(["git", "rev-parse", "HEAD"], root), "HEAD")
        local = require_full_sha(self.runner.run(["git", "rev-parse", f"refs/heads/{base}"], root), "local base")
        remote = require_full_sha(
            self.runner.run(["git", "rev-parse", f"refs/remotes/origin/{base}"], root),
            "remote base",
        )
        effective = RepositoryIdentity(
            **{
                **self.identity.__dict__,
                "head_sha": head,
                "local_base_sha": local,
                "remote_base_sha": remote,
            }
        )
        self._assert_effective_base_identity(effective, root)
        if self.runner.run(["git", "status", "--porcelain=v1"], root):
            raise GuardError("orchestration checkout became dirty")
        self.state["activation"]["base_sha"] = remote
        transition_state(self.state, "task-done")
        self.store.save(self.state)

    def _cleanup_metadata_proof(self) -> tuple[Mapping[str, Any], Path, str, str]:
        if self.state.get("phase") != "cleanup":
            raise GuardError("cleanup is allowed only in cleanup")
        if self.state["activation"]["allowed_operations"].get("delete_proven_task_owned_resources") is not True:
            raise GuardError("task-owned cleanup is not authorized")
        if self.state.get("maintenance", {}).get("requested"):
            raise GuardError("cleanup is forbidden while maintenance is pending")
        task = self.state.get("task")
        if not isinstance(task, Mapping):
            raise GuardError("no active task owns cleanup resources")
        if task.get("active_role") is not None:
            raise GuardError("a child thread still owns the task resources")
        cleanup = task.get("cleanup", {})
        if cleanup.get("worker_archived") is not True or cleanup.get("supervisors_archived") is not True:
            raise GuardError("archive the exact Worker and Supervisors before local cleanup")
        merge_receipt = task.get("merge_receipt")
        close_receipt = task.get("issue_close_receipt")
        if not isinstance(merge_receipt, Mapping):
            raise GuardError("confirmed merge receipt is missing")
        if not isinstance(close_receipt, Mapping):
            raise GuardError("confirmed selected-issue close receipt is missing")
        assert_repository_target(
            self.state["activation"]["repository"],
            str(merge_receipt.get("repository", "")),
            target_repository_id=merge_receipt.get("repository_id"),
        )
        assert_repository_target(
            self.state["activation"]["repository"],
            str(close_receipt.get("repository", "")),
            target_repository_id=close_receipt.get("repository_id"),
        )
        if merge_receipt.get("pr_number") != task.get("pr_number"):
            raise GuardError("merge receipt PR differs from the selected task")
        if close_receipt.get("issue") != task.get("issue") or close_receipt.get("state_reason") != "completed":
            raise GuardError("issue-close receipt differs from the selected task")
        branch = validate_branch_name(task.get("branch"))
        if not branch.startswith("codex/") or branch == self.state["activation"]["base_branch"]:
            raise GuardError("recorded cleanup branch is unsafe")
        worktree = Path(task.get("worktree", "")).resolve()
        if worktree == Path(self.identity.git_root).resolve():
            raise GuardError("cannot remove the orchestration checkout")
        head = require_full_sha(task.get("candidate_sha"), "task candidate_sha")
        if head != task.get("merged_head_sha") or head != task.get("candidate_sha"):
            raise GuardError("cleanup head does not match the merged candidate")
        merge_sha = require_full_sha(task.get("merge_sha"), "merge_sha")
        if merge_receipt.get("merge_sha") != merge_sha or merge_receipt.get("expected_head_sha") != head:
            raise GuardError("merge receipt identity differs from cleanup state")
        root = Path(self.identity.git_root)
        current = self.runner.run(["git", "branch", "--show-current"], root)
        base = self.state["activation"]["base_branch"]
        if current not in {"", base}:
            raise GuardError("orchestration checkout is on an unrelated branch during cleanup")
        self.runner.run(["git", "fetch", "origin", base], root)
        remote_ref = f"refs/remotes/origin/{base}"
        remote = require_full_sha(self.runner.run(["git", "rev-parse", remote_ref], root), "remote base")
        root_head = require_full_sha(self.runner.run(["git", "rev-parse", "HEAD"], root), "orchestrator HEAD")
        task_base = require_full_sha(task.get("base_sha"), "task base_sha")
        self.runner.run(["git", "merge-base", "--is-ancestor", root_head, remote], root)
        self.runner.run(["git", "merge-base", "--is-ancestor", task_base, remote], root)
        self.runner.run(["git", "merge-base", "--is-ancestor", merge_sha, remote], root)
        self.runner.run(["git", "merge-base", "--is-ancestor", head, remote], root)
        if self.runner.run(["git", "status", "--porcelain=v1"], root):
            raise GuardError("orchestration checkout is dirty during cleanup")
        return task, worktree, branch, head

    def remove_task_worktree(self) -> None:
        task, worktree, branch, head = self._cleanup_metadata_proof()
        root = Path(self.identity.git_root)
        listed = self.runner.run(["git", "worktree", "list", "--porcelain"], root)
        if f"worktree {worktree}" not in listed.splitlines():
            if not worktree.exists():
                self.state["task"]["cleanup"]["worktree_removed"] = True
                self.store.save(self.state)
                return
            raise GuardError("recorded worktree ownership is ambiguous")
        if exact_worktree_branch_from_porcelain(listed, worktree) != f"refs/heads/{branch}":
            raise GuardError("cleanup worktree porcelain branch differs from the recorded task branch")
        repo = self.state["activation"]["repository"]
        worktree_identity = resolve_repository_identity(
            worktree,
            self.state["activation"]["base_branch"],
            repository_id=repo.get("repository_id"),
            require_synchronized=False,
            runner=self.runner,
        )
        if worktree_identity.git_common_dir_fingerprint != repo["git_common_dir_fingerprint"]:
            raise GuardError("cleanup worktree belongs to another Git common directory")
        if worktree_identity.current_branch != branch:
            raise GuardError("cleanup worktree is not on the recorded task branch")
        if worktree_identity.head_sha != head:
            raise GuardError("cleanup worktree HEAD differs from the merged candidate")
        self.runner.run(["git", "worktree", "remove", str(worktree)], root)
        self.state["task"]["cleanup"]["worktree_removed"] = True
        self.store.save(self.state)

    def delete_local_task_branch(self) -> None:
        _, worktree, branch, head = self._cleanup_metadata_proof()
        if self.state["task"]["cleanup"].get("worktree_removed") is not True:
            raise GuardError("remove and durably record the task worktree before deleting its branch")
        root = Path(self.identity.git_root)
        listed = self.runner.run(["git", "worktree", "list", "--porcelain"], root)
        if f"worktree {worktree}" in listed.splitlines() or worktree.exists():
            raise GuardError("remove the task worktree before deleting its branch")
        branches = self.runner.run(["git", "branch", "--list", branch], root)
        if not branches.strip():
            self.state["task"]["cleanup"]["local_branch_deleted"] = True
            self.store.save(self.state)
            return
        branch_head = require_full_sha(
            self.runner.run(["git", "rev-parse", f"refs/heads/{branch}"], root),
            "task branch head",
        )
        if branch_head != head:
            raise GuardError("local task branch differs from the merged candidate")
        base = self.state["activation"]["base_branch"]
        self.runner.run(["git", "merge", "--ff-only", f"origin/{base}"], root)
        self.runner.run(["git", "branch", "-d", branch], root)
        self.state["task"]["cleanup"]["local_branch_deleted"] = True
        self.store.save(self.state)


def _guard_from_args(args: argparse.Namespace) -> GuardedGit:
    return GuardedGit(
        StateStore(args.state_dir),
        activation_id=args.activation_id,
        installed_digest=args.installed_digest,
        skill_root=args.skill_root,
    )


GUARDED_CLI_COMMANDS = (
    "guarded-refresh",
    "guarded-push",
    "guarded-sync",
    "guarded-remove-worktree",
    "guarded-delete-branch",
)
GUARDED_CLI_OPTIONS = (
    "--state-dir",
    "--activation-id",
    "--installed-digest",
    "--skill-root",
)


def validate_guarded_cli_shape(argv: Sequence[str]) -> None:
    if not argv or argv[0] not in GUARDED_CLI_COMMANDS:
        return
    if len(argv) != 1 + 2 * len(GUARDED_CLI_OPTIONS) or tuple(argv[1::2]) != GUARDED_CLI_OPTIONS:
        raise ValidationError(
            "guarded command must use the exact immutable argument order with no duplicate or trailing tokens"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Roundlet deterministic state and guarded Git helper")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-state", help="Validate one Roundlet state directory")
    validate.add_argument("--state-dir", required=True)

    migrate = sub.add_parser("migrate-state", help="Atomically apply a supported state migration")
    migrate.add_argument("--state-dir", required=True)
    migrate.add_argument("--activation-id", required=True)
    migrate.add_argument("--checkpoint-id", required=True)
    migrate.add_argument("--schedule-id", required=True)
    migrate.add_argument("--expected-installed-digest", required=True)
    migrate.add_argument("--expected-from-schema", required=True, type=int)
    migrate.add_argument("--target-schema", required=True, type=int)
    migrate.add_argument("--skill-root", required=True)

    digest = sub.add_parser("skill-digest", help="Print the deterministic installed skill content digest")
    digest.add_argument("--skill-root", required=True)

    role_config = sub.add_parser("role-config", help="Print validated Roundlet role-model configuration")
    role_config.add_argument("--skill-root", required=True)

    for name in GUARDED_CLI_COMMANDS:
        guarded = sub.add_parser(name)
        guarded.add_argument("--state-dir", required=True)
        guarded.add_argument("--activation-id", required=True)
        guarded.add_argument("--installed-digest", required=True)
        guarded.add_argument("--skill-root", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    try:
        validate_guarded_cli_shape(raw_argv)
    except RoundletError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    args = build_parser().parse_args(raw_argv)
    try:
        if args.command == "validate-state":
            StateStore(args.state_dir).load()
        elif args.command == "migrate-state":
            StateStore(args.state_dir).migrate(
                activation_id=args.activation_id,
                checkpoint_id=args.checkpoint_id,
                schedule_id=args.schedule_id,
                expected_installed_digest=args.expected_installed_digest,
                expected_from_schema=args.expected_from_schema,
                target_version=args.target_schema,
                skill_root=args.skill_root,
            )
        elif args.command == "role-config":
            config = load_role_model_config(args.skill_root)
            print(canonical_json(config))
            return 0
        elif args.command == "skill-digest":
            print(skill_content_digest(args.skill_root))
            return 0
        elif args.command == "guarded-refresh":
            _guard_from_args(args).refresh_base()
        elif args.command == "guarded-push":
            _guard_from_args(args).push_task_branch()
        elif args.command == "guarded-sync":
            _guard_from_args(args).sync_base()
        elif args.command == "guarded-remove-worktree":
            _guard_from_args(args).remove_task_worktree()
        elif args.command == "guarded-delete-branch":
            _guard_from_args(args).delete_local_task_branch()
        else:
            raise ValidationError("unknown command")
    except RoundletError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
