from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "roundlet"
import sys

sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import orchestration_state as rs


def repository_path_is_outside_skill_tree(path):
    relative = path.relative_to(REPO_ROOT)
    return relative.parts[0] != "skills"


def resolve_skill_link_target(target):
    resolved_skill_root = SKILL_ROOT.resolve()
    resolved_target = (resolved_skill_root / target).resolve()
    try:
        resolved_target.relative_to(resolved_skill_root)
    except ValueError as error:
        raise ValueError(f"skill link escapes publishable root: {target}") from error
    if not resolved_target.is_file():
        raise ValueError(f"skill link does not target a file: {target}")
    return resolved_target


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40
DIGEST = rs.skill_content_digest(SKILL_ROOT)
REFRESH_TIME = "2026-07-14T01:00:00Z"
OWNER_ACTOR = {
    "id": 7,
    "login": "owner",
    "account_type": "User",
    "verified_by_connector": True,
}
CAPABILITY_PREFLIGHT = {
    "verified_by_service": True,
    "per_thread_receipts": True,
    "worker_profile_enforceable": True,
    "supervisor_profile_enforceable": True,
    "connector_read_adapter_receipts": True,
}


def identity(*, base: str = "main", digest_root: str = "/repo/.git") -> rs.RepositoryIdentity:
    return rs.RepositoryIdentity(
        owner_name="owner/project",
        repository_id=123,
        git_root="/repo",
        git_common_dir=digest_root,
        git_common_dir_fingerprint=rs.hashlib.sha256(digest_root.encode()).hexdigest(),
        origin_fingerprint=rs.origin_fingerprint("https://github.com/owner/project.git"),
        origin_push_fingerprint=rs.origin_fingerprint("https://github.com/owner/project.git"),
        origin_host="github.com",
        base_branch=base,
        head_sha=SHA_A,
        local_base_sha=SHA_A,
        remote_base_sha=SHA_A,
        current_branch=base,
    )


def role_receipt(role, thread_id, *, created_at="2026-07-14T00:00:00Z", parent="orchestrator-1"):
    model_profile = rs.load_role_model_config(SKILL_ROOT)["defaults"]["roles"][role]
    profiles = {
        "orchestrator": (True, True, "workspace-write"),
        "worker": (True, False, "worktree-write"),
        "supervisor": (False, False, "read-only"),
    }
    filesystem_write, github_connector, permission = profiles[role]
    return {
        "verified_by_service": True,
        "role": role,
        "thread_id": thread_id,
        "model": model_profile["model"],
        "reasoning_effort": model_profile["reasoning_effort"],
        "environment_type": "worktree" if role == "worker" else "local",
        "project_identity": identity().git_common_dir_fingerprint,
        "parent_thread_id": None if role == "orchestrator" else parent,
        "forked": False,
        "permission_profile": permission,
        "filesystem_write": filesystem_write,
        "github_connector": github_connector,
        "shell_network": role == "orchestrator",
        "web_access": role == "orchestrator",
        "gh_access": role == "orchestrator",
        "created_at": created_at,
    }


def policy3_role_receipt(role, thread_id, *, created_at="2026-07-14T00:00:00Z", parent="orchestrator-1"):
    receipt = role_receipt(role, thread_id, created_at=created_at, parent=parent)
    receipt.update(rs.load_role_model_config(SKILL_ROOT)["legacy_profiles"]["policy_3"][role])
    return receipt


def downgrade_to_policy3(value):
    activation = value["activation"]
    activation["orchestrator_creation_receipt"].update(
        rs.load_role_model_config(SKILL_ROOT)["legacy_profiles"]["policy_3"]["orchestrator"]
    )
    if value.get("task"):
        value["task"]["worker_creation_receipt"].update(
            rs.load_role_model_config(SKILL_ROOT)["legacy_profiles"]["policy_3"]["worker"]
        )
    for receipt in value["review"]["supervisor_creation_receipts"]:
        receipt.update(rs.load_role_model_config(SKILL_ROOT)["legacy_profiles"]["policy_3"]["supervisor"])
    activation.pop("role_model_snapshot", None)
    activation.pop("role_model_snapshot_digest", None)
    for key in (
        "review_policy_snapshot",
        "review_policy_snapshot_digest",
        "legacy_unbounded_review",
        "legacy_review_migration",
    ):
        activation.pop(key, None)
    value["review"].pop("exhaustion", None)
    value["review"].pop("supervisor_creation_intent", None)
    value["review"].pop("completed_supervisor_count", None)
    value["review"].pop("completed_supervisor_results", None)
    value["review"].pop("completed_supervisor_digest", None)
    value["versions"].update({"schema": 4, "review_contract": "3", "policy": "3"})
    refresh_policy3_scope(value)


def refresh_policy3_scope(value):
    activation = value["activation"]
    legacy_snapshot = rs.load_role_model_config(SKILL_ROOT)["legacy_profiles"]["policy_3"]
    activation["scope_digest"] = rs.compute_policy3_scope_digest(
        activation["repository"],
        activation["base_branch"],
        activation["umbrella_issues"],
        activation["allowed_operations"],
        value["skill"]["content_digest"],
        owner_actor=activation["owner_actor"],
        capability_preflight=activation["capability_preflight"],
        orchestrator_creation_receipt=activation["orchestrator_creation_receipt"],
    )


def activation_request(*, umbrellas=None, base="main", operations=None):
    return {
        "mode": "start",
        "base_branch": base,
        "umbrella_issues": umbrellas or [10],
        "authorize": operations
        or {
            "create_task_branches": True,
            "create_draft_prs": True,
            "mark_ready_for_review": True,
            "merge_commit_after_all_gates": True,
            "close_completed_sub_issues": True,
            "delete_proven_task_owned_resources": True,
        },
    }


def state(*, umbrellas=None, digest=DIGEST, operations=None):
    return rs.new_state(
        activation_request(umbrellas=umbrellas, operations=operations),
        identity(),
        activation_id="activation-0001",
        orchestrator_thread_id="orchestrator-1",
        installed_roundlet_digest=digest,
        owner_actor=OWNER_ACTOR,
        capability_preflight=CAPABILITY_PREFLIGHT,
        orchestrator_creation_receipt=role_receipt("orchestrator", "orchestrator-1"),
        skill_root=SKILL_ROOT,
        now="2026-07-14T00:00:00Z",
    )


def issue_connector_evidence(issue, *, open=True, completed=False):
    core = {
        "verified_by_connector": True,
        "repository": "owner/project",
        "repository_id": 123,
        "issue": issue,
        "state": "open" if open else "closed",
        "state_reason": None if open else ("completed" if completed else "not_planned"),
        "observed_at": REFRESH_TIME,
    }
    return {**core, "revision": rs.digest_json(core)}


def umbrella_connector_evidence(umbrella):
    return {
        "verified_by_connector": True,
        "repository": "owner/project",
        "repository_id": 123,
        "issue": umbrella,
        "body_digest": rs.digest_json({"umbrella": umbrella, "kind": "body"}),
        "comments_digest": rs.digest_json({"umbrella": umbrella, "kind": "comments"}),
        "formal_subissues_digest": rs.digest_json({"umbrella": umbrella, "kind": "formal"}),
        "observed_at": REFRESH_TIME,
    }


def formal_membership_evidence(issue, umbrella, issue_revision):
    umbrella_evidence = umbrella_connector_evidence(umbrella)
    return {
        "verified_by_connector": True,
        "source_type": "formal-sub-issue",
        "repository": "owner/project",
        "repository_id": 123,
        "umbrella_issue": umbrella,
        "umbrella_revision": rs.digest_json(umbrella_evidence),
        "issue": issue,
        "issue_revision": issue_revision,
        "observed_at": REFRESH_TIME,
        "relationship_id": f"formal:{umbrella}:{issue}",
    }


def merged_completion_evidence(issue, issue_revision):
    return {
        "verified_by_connector": True,
        "repository": "owner/project",
        "repository_id": 123,
        "issue": issue,
        "issue_revision": issue_revision,
        "issue_state": "closed",
        "issue_state_reason": "completed",
        "observed_at": REFRESH_TIME,
        "merged_pr": {
            "number": 1000 + issue,
            "repository": "owner/project",
            "repository_id": 123,
            "state": "closed",
            "merged": True,
            "head_sha": SHA_B,
            "merge_commit_sha": SHA_C,
            "observed_at": REFRESH_TIME,
        },
    }


def set_selection(value, *, umbrella=10, issue=11, base=SHA_A):
    source_umbrella = value["activation"]["umbrella_issues"][0]
    issue_evidence = issue_connector_evidence(issue)
    snapshot = rs.IssueSnapshot(
        issue=issue,
        umbrella=source_umbrella,
        repository="owner/project",
        membership_evidence=(
            formal_membership_evidence(issue, source_umbrella, issue_evidence["revision"]),
        ),
        issue_evidence=issue_evidence,
    )
    receipt = select_from_connector(
        value,
        [snapshot],
        refresh_manifest(value, {source_umbrella: [issue]}, [snapshot]),
    )
    receipt["selected_umbrella"] = umbrella
    receipt["base_sha"] = base
    receipt["receipt_digest"] = rs.digest_json(
        {key: item for key, item in receipt.items() if key != "receipt_digest"}
    )
    value["selection"] = receipt


def refresh_manifest(value, discovered, snapshots=None):
    snapshots = list(snapshots or [])
    memberships_by_umbrella = {
        umbrella: [] for umbrella in value["activation"]["umbrella_issues"]
    }
    for snapshot in snapshots:
        memberships_by_umbrella.setdefault(snapshot.umbrella, []).extend(
            copy.deepcopy(list(snapshot.membership_evidence))
        )
    for umbrella, issues in discovered.items():
        known = {
            item["issue"] for item in memberships_by_umbrella.get(umbrella, [])
        }
        for issue in issues:
            if issue not in known:
                issue_evidence = issue_connector_evidence(issue)
                memberships_by_umbrella.setdefault(umbrella, []).append(
                    formal_membership_evidence(issue, umbrella, issue_evidence["revision"])
                )
    return {
        "repository": "owner/project",
        "repository_id": 123,
        "base_sha": value["activation"]["base_sha"],
        "refresh_timestamp": REFRESH_TIME,
        "umbrellas": [
            {
                "umbrella_issue": umbrella,
                "umbrella_evidence": umbrella_connector_evidence(umbrella),
                "umbrella_revision": rs.digest_json(umbrella_connector_evidence(umbrella)),
                "membership_evidence_digest": rs.digest_json(
                    {
                        "repository": "owner/project",
                        "repository_id": 123,
                        "umbrella_issue": umbrella,
                        "umbrella_revision": rs.digest_json(umbrella_connector_evidence(umbrella)),
                        "membership_evidence": sorted(
                            memberships_by_umbrella.get(umbrella, []), key=rs.canonical_json
                        ),
                    }
                ),
                "discovered_issues": discovered.get(umbrella, []),
                "complete": True,
            }
            for umbrella in value["activation"]["umbrella_issues"]
        ],
    }


def raw_snapshot_document(snapshot):
    return {
        "issue": snapshot.issue,
        "umbrella": snapshot.umbrella,
        "repository": snapshot.repository,
        "open": snapshot.open,
        "completion_verified": snapshot.completion_verified,
        "dependencies": list(snapshot.dependencies),
        "external_blockers": list(snapshot.external_blockers),
        "membership_evidence": copy.deepcopy(list(snapshot.membership_evidence)),
        "issue_evidence": copy.deepcopy(snapshot.issue_evidence),
        "completion_evidence": copy.deepcopy(snapshot.completion_evidence),
        "required_order_index": snapshot.required_order_index,
        "ambiguous_active_implementation": snapshot.ambiguous_active_implementation,
        "owner_priority": snapshot.owner_priority,
        "unlocks": snapshot.unlocks,
        "overlap_risk": snapshot.overlap_risk,
    }


def select_from_connector(value, snapshots, manifest):
    snapshot_evidence = [raw_snapshot_document(snapshot) for snapshot in snapshots]
    adapter_core = {
        "verified_by_service": True,
        "connector": "github",
        "operation": rs.CONNECTOR_REFRESH_OPERATION,
        "adapter_id": "github-adapter:roundlet-test",
        "activation_id": value["activation"]["id"],
        "repository": "owner/project",
        "repository_id": 123,
        "orchestrator_thread_id": value["activation"]["orchestrator_thread_id"],
        "project_identity": value["activation"]["orchestrator_creation_receipt"][
            "project_identity"
        ],
        "created_at": "2026-07-14T00:00:00Z",
    }

    def read_connector(request):
        core = {
            "verified_by_connector": True,
            "connector": "github",
            "operation": rs.CONNECTOR_REFRESH_OPERATION,
            "adapter_id": request["adapter_id"],
            "request_digest": rs.digest_json(request),
            "service_receipt_id": f"github-read:{rs.digest_json(request)[:16]}",
            "refresh_manifest": copy.deepcopy(manifest),
            "snapshot_evidence": copy.deepcopy(snapshot_evidence),
        }
        return {**core, "response_digest": rs.digest_json(core)}

    adapter = rs.bind_github_connector_read_adapter(
        value,
        service_receipt={**adapter_core, "receipt_digest": rs.digest_json(adapter_core)},
        read_connector=read_connector,
    )
    sealed = rs.execute_connector_refresh(
        value,
        refresh_timestamp=REFRESH_TIME,
        adapter=adapter,
    )
    return rs.select_next_task(value, sealed)


def assigned_state(*, umbrellas=None, digest=DIGEST):
    value = state(umbrellas=umbrellas, digest=digest)
    set_selection(value, umbrella=(umbrellas or [10])[0])
    rs.assign_task(
        value,
        umbrella_issue=(umbrellas or [10])[0],
        issue=11,
        branch="codex/issue-11",
        worktree="/repo-worktrees/issue-11",
        worker_thread_id="worker-11",
        worker_creation_receipt=role_receipt("worker", "worker-11"),
        base_sha=SHA_A,
    )
    return value


def pass_identity_for(value, candidate=SHA_B):
    if not value["review"]["supervisor_thread_ids"]:
        value["review"]["round"] = 1
        value["review"]["supervisor_thread_ids"] = ["supervisor-pass"]
        value["review"]["unarchived_supervisor_thread_ids"] = ["supervisor-pass"]
        value["review"]["last_supervisor_created_at"] = "2026-07-14T00:00:00Z"
        value["review"]["supervisor_creation_receipts"] = [
            role_receipt("supervisor", "supervisor-pass", created_at="2026-07-14T00:00:00Z")
        ]
        value["review"]["completed_supervisor_count"] = 1
        value["review"]["completed_supervisor_results"] = [
            {"thread_id": "supervisor-pass", "generation": 1, "result": "PASS"}
        ]
        value["review"]["completed_supervisor_digest"] = rs.fold_archive_digest(
            "0" * 64, value["review"]["completed_supervisor_results"]
        )
    return {
        "activation_id": value["activation"]["id"],
        "repository": value["activation"]["repository"]["owner_name"],
        "issue": value["task"]["issue"],
        "base_sha": value["task"]["base_sha"],
        "candidate_sha": candidate,
        "review_contract": value["versions"]["review_contract"],
        "supervisor_thread_id": value["review"]["supervisor_thread_ids"][-1],
        "review_round": value["review"]["round"],
    }


def begin_review(value, thread_id, *, final=False):
    generation = value["review"]["round"] + 1
    rs.begin_supervisor(
        value,
        thread_id,
        final=final,
        creation_receipt={
            "activation_id": value["activation"]["id"],
            "issue": value["task"]["issue"],
            "generation": generation,
            "installed_roundlet_digest": value["skill"]["content_digest"],
            "review_contract": value["versions"]["review_contract"],
            "created": True,
            "service_receipt": role_receipt(
                "supervisor",
                thread_id,
                created_at=f"2026-07-14T00:00:00.{generation:06d}Z",
            ),
        },
    )


def pr_identity(value):
    return {
        "repository": "owner/project",
        "repository_id": 123,
        "base_repository": "owner/project",
        "base_repository_id": 123,
        "base_branch": "main",
        "base_sha": value["task"]["base_sha"],
        "head_repository": "owner/project",
        "head_repository_id": 123,
        "head_ref": value["task"]["branch"],
        "head_sha": value["task"]["candidate_sha"],
    }


def apply_github(value, operation, target, receipt, *, key=None):
    intent_key = key or f"{operation}-0001"
    rs.begin_github_mutation_intent(
        value,
        operation=operation,
        idempotency_key=intent_key,
        target=target,
    )
    rs.complete_github_mutation_intent(value, idempotency_key=intent_key, receipt=receipt)


def record_draft(value, *, overrides=None):
    live = {
        **pr_identity(value),
        "issue": value["task"]["issue"],
        "pr_number": 22,
        "pr_url": "https://github.com/owner/project/pull/22",
        "pr_state": "open",
        "draft": True,
    }
    live.update(overrides or {})
    apply_github(value, "create-draft-pr", pr_identity(value), live)


def record_ready(value, *, overrides=None):
    live = {
        **pr_identity(value),
        "pr_number": 22,
        "pr_url": "https://github.com/owner/project/pull/22",
        "pr_state": "open",
        "draft": False,
    }
    live.update(overrides or {})
    apply_github(value, "mark-ready", live, live)


def premerge_live(value):
    return {
        **pr_identity(value),
        "scope_valid": True,
        "membership_valid": True,
        "worktree_clean": True,
        "tests_passed": True,
        "checks_passed": True,
        "pr_ready": True,
        "mergeable": True,
        "no_conflict": True,
        "no_new_blocker": True,
        "no_maintenance_request": True,
        "issue": value["task"]["issue"],
        "pr_number": value["task"]["pr_number"],
        "pr_url": value["task"]["pr_url"],
        "pr_state": "open",
        "draft": False,
        "merge_method": "merge",
    }


def record_merge(value, *, overrides=None):
    receipt = {
        **pr_identity(value),
        "pr_number": value["task"]["pr_number"],
        "pr_url": value["task"]["pr_url"],
        "pr_state": "closed",
        "merged": True,
        "expected_head_sha": value["task"]["candidate_sha"],
        "merge_sha": SHA_C,
        "merge_method": "merge",
    }
    receipt.update(overrides or {})
    apply_github(value, "merge-pr", premerge_live(value), receipt)


def record_close(value, *, issue=11, issue_state="closed"):
    target = {"repository": "owner/project", "repository_id": 123, "issue": issue}
    receipt = {**target, "issue_state": issue_state, "state_reason": "completed"}
    apply_github(value, "close-issue", target, receipt)


def complete_scope(value):
    issue_evidence = issue_connector_evidence(11, open=False, completed=True)
    snapshot = rs.IssueSnapshot(
        issue=11,
        umbrella=value["activation"]["umbrella_issues"][0],
        repository="owner/project",
        open=False,
        completion_verified=True,
        membership_evidence=(
            formal_membership_evidence(
                11,
                value["activation"]["umbrella_issues"][0],
                issue_evidence["revision"],
            ),
        ),
        issue_evidence=issue_evidence,
        completion_evidence=merged_completion_evidence(11, issue_evidence["revision"]),
    )
    select_from_connector(
        value,
        [snapshot],
        refresh_manifest(
            value,
            {value["activation"]["umbrella_issues"][0]: [11]},
            [snapshot],
        ),
    )


def set_operation(value, operation, enabled):
    value["activation"]["allowed_operations"][operation] = enabled
    value["activation"]["scope_digest"] = rs.compute_scope_digest(
        value["activation"]["repository"],
        value["activation"]["base_branch"],
        value["activation"]["umbrella_issues"],
        value["activation"]["allowed_operations"],
        value["skill"]["content_digest"],
        owner_actor=value["activation"]["owner_actor"],
        capability_preflight=value["activation"]["capability_preflight"],
        orchestrator_creation_receipt=value["activation"]["orchestrator_creation_receipt"],
        role_model_snapshot=value["activation"]["role_model_snapshot"],
        role_model_snapshot_digest=value["activation"]["role_model_snapshot_digest"],
        review_policy_snapshot=value["activation"]["review_policy_snapshot"],
        review_policy_snapshot_digest=value["activation"]["review_policy_snapshot_digest"],
        legacy_unbounded_review=value["activation"]["legacy_unbounded_review"],
    )


def set_review_budget(value, maximum, *, converge_after=None, legacy_unbounded=False):
    activation = value["activation"]
    activation["review_policy_snapshot"] = {
        "max_supervisor_cycles": maximum,
        "converge_after_supervisor_cycles": maximum if converge_after is None else converge_after,
    }
    activation["review_policy_snapshot_digest"] = rs.digest_json(
        activation["review_policy_snapshot"]
    )
    activation["legacy_unbounded_review"] = legacy_unbounded
    activation["scope_digest"] = rs.compute_scope_digest(
        activation["repository"],
        activation["base_branch"],
        activation["umbrella_issues"],
        activation["allowed_operations"],
        value["skill"]["content_digest"],
        owner_actor=activation["owner_actor"],
        capability_preflight=activation["capability_preflight"],
        orchestrator_creation_receipt=activation["orchestrator_creation_receipt"],
        role_model_snapshot=activation["role_model_snapshot"],
        role_model_snapshot_digest=activation["role_model_snapshot_digest"],
        review_policy_snapshot=activation["review_policy_snapshot"],
        review_policy_snapshot_digest=activation["review_policy_snapshot_digest"],
        legacy_unbounded_review=activation["legacy_unbounded_review"],
    )


def downgrade_to_schema6(value):
    activation = value["activation"]
    maximum = activation["review_policy_snapshot"]["max_supervisor_cycles"]
    value["review"].pop("completed_supervisor_count", None)
    value["review"].pop("completed_supervisor_results", None)
    value["review"].pop("completed_supervisor_digest", None)
    activation["review_policy_snapshot"] = {"max_supervisor_cycles": maximum}
    activation["review_policy_snapshot_digest"] = rs.digest_json(
        activation["review_policy_snapshot"]
    )
    value["versions"].update({"schema": 6, "protocol": "3", "review_contract": "4", "policy": "5"})
    if isinstance(value["review"].get("pass_identity"), dict):
        value["review"]["pass_identity"]["review_contract"] = "4"
    activation["scope_digest"] = rs.compute_schema6_scope_digest(
        activation["repository"],
        activation["base_branch"],
        activation["umbrella_issues"],
        activation["allowed_operations"],
        value["skill"]["content_digest"],
        owner_actor=activation["owner_actor"],
        capability_preflight=activation["capability_preflight"],
        orchestrator_creation_receipt=activation["orchestrator_creation_receipt"],
        role_model_snapshot=activation["role_model_snapshot"],
        role_model_snapshot_digest=activation["role_model_snapshot_digest"],
        review_policy_snapshot=activation["review_policy_snapshot"],
        review_policy_snapshot_digest=activation["review_policy_snapshot_digest"],
        legacy_unbounded_review=activation["legacy_unbounded_review"],
    )


def downgrade_to_schema5_unbounded(value):
    value["versions"].update({"schema": 5, "protocol": "3", "review_contract": "3", "policy": "4"})
    activation = value["activation"]
    for key in (
        "review_policy_snapshot",
        "review_policy_snapshot_digest",
        "legacy_unbounded_review",
        "legacy_review_migration",
    ):
        activation.pop(key, None)
    value["review"].pop("exhaustion", None)
    value["review"].pop("supervisor_creation_intent", None)
    value["review"].pop("completed_supervisor_count", None)
    value["review"].pop("completed_supervisor_results", None)
    value["review"].pop("completed_supervisor_digest", None)
    activation["scope_digest"] = rs.compute_scope_digest(
        activation["repository"],
        activation["base_branch"],
        activation["umbrella_issues"],
        activation["allowed_operations"],
        value["skill"]["content_digest"],
        owner_actor=activation["owner_actor"],
        capability_preflight=activation["capability_preflight"],
        orchestrator_creation_receipt=activation["orchestrator_creation_receipt"],
        role_model_snapshot=activation["role_model_snapshot"],
        role_model_snapshot_digest=activation["role_model_snapshot_digest"],
        protocol_version="3",
        policy_version="4",
    )


def premerge_state():
    value = assigned_state()
    rs.set_candidate(value, SHA_B, clean=True)
    record_draft(value)
    begin_review(value, "supervisor-initial")
    rs.accept_supervisor_result(
        value,
        thread_id="supervisor-initial",
        candidate_sha=SHA_B,
        result="PASS",
    )
    rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-initial")
    rs.set_candidate(value, SHA_B, clean=True)
    record_ready(value)
    begin_review(value, "supervisor-final", final=True)
    rs.accept_supervisor_result(
        value,
        thread_id="supervisor-final",
        candidate_sha=SHA_B,
        result="PASS",
    )
    rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-final")
    rs.record_worker_ready_to_merge(
        value,
        worker_thread_id="worker-11",
        head_sha=SHA_B,
        clean=True,
    )
    return value


class ActivationTests(unittest.TestCase):
    def test_normalizes_activation(self):
        value = rs.normalize_activation_request(activation_request(umbrellas=[10, 20]))
        self.assertEqual(value["umbrella_issues"], [10, 20])

    def test_rejects_repository_selector(self):
        request = activation_request()
        request["repository"] = "other/repo"
        with self.assertRaises(rs.ScopeError):
            rs.normalize_activation_request(request)

    def test_rejects_repository_list(self):
        request = activation_request()
        request["repositories"] = ["owner/project"]
        with self.assertRaises(rs.ScopeError):
            rs.normalize_activation_request(request)

    def test_rejects_duplicate_umbrellas(self):
        with self.assertRaises(rs.ValidationError):
            rs.normalize_activation_request(activation_request(umbrellas=[10, 10]))

    def test_rejects_invalid_issue_ids(self):
        with self.assertRaises(rs.ValidationError):
            rs.normalize_activation_request(activation_request(umbrellas=[0]))

    def test_rejects_missing_operation(self):
        operations = activation_request()["authorize"]
        del operations["create_draft_prs"]
        with self.assertRaises(rs.ValidationError):
            rs.normalize_activation_request(activation_request(operations=operations))

    def test_rejects_non_boolean_operation(self):
        operations = activation_request()["authorize"]
        operations["create_draft_prs"] = "yes"
        with self.assertRaises(rs.ValidationError):
            rs.normalize_activation_request(activation_request(operations=operations))

    def test_owner_name_origin_formats(self):
        expected = "owner/project"
        self.assertEqual(rs.owner_name_from_origin("https://github.com/Owner/Project.git"), expected)
        self.assertEqual(rs.owner_name_from_origin("git@github.com:Owner/Project.git"), expected)
        self.assertEqual(rs.owner_name_from_origin("ssh://git@github.com/Owner/Project.git"), expected)

    def test_rejects_ambiguous_origin(self):
        with self.assertRaises(rs.ValidationError):
            rs.owner_name_from_origin("https://github.com/owner/group/project.git")

    def test_rejects_non_github_origin_host(self):
        with self.assertRaises(rs.ValidationError):
            rs.owner_name_from_origin("https://evil.example/owner/project.git")
        with self.assertRaises(rs.ValidationError):
            rs.owner_name_from_origin("git@evil.example:owner/project.git")

    def test_scope_digest_is_normalized_and_stable(self):
        first = state(umbrellas=[10, 20])["activation"]["scope_digest"]
        second = state(umbrellas=[10, 20])["activation"]["scope_digest"]
        self.assertEqual(first, second)

    def test_issue_text_is_not_in_scope_digest(self):
        value = state()
        before = value["activation"]["scope_digest"]
        value["retry"] = {"mutable_issue_body_digest": "changed"}
        rs.validate_state(value)
        self.assertEqual(value["activation"]["scope_digest"], before)

    def test_umbrella_order_changes_scope_digest(self):
        first = state(umbrellas=[10, 20])["activation"]["scope_digest"]
        second = state(umbrellas=[20, 10])["activation"]["scope_digest"]
        self.assertNotEqual(first, second)

    def test_base_mismatch_blocks(self):
        with self.assertRaises(rs.ScopeError):
            rs.new_state(
                activation_request(base="develop"),
                identity(base="main"),
                activation_id="activation-0001",
                orchestrator_thread_id="orchestrator-1",
                installed_roundlet_digest=DIGEST,
                owner_actor=OWNER_ACTOR,
                capability_preflight=CAPABILITY_PREFLIGHT,
                orchestrator_creation_receipt=role_receipt("orchestrator", "orchestrator-1"),
                skill_root=SKILL_ROOT,
            )

    def test_unsynchronized_identity_blocks(self):
        unsynced = rs.RepositoryIdentity(**{**identity().__dict__, "remote_base_sha": SHA_B})
        with self.assertRaises(rs.GuardError):
            rs.new_state(
                activation_request(),
                unsynced,
                activation_id="activation-0001",
                orchestrator_thread_id="orchestrator-1",
                installed_roundlet_digest=DIGEST,
                owner_actor=OWNER_ACTOR,
                capability_preflight=CAPABILITY_PREFLIGHT,
                orchestrator_creation_receipt=role_receipt("orchestrator", "orchestrator-1"),
                skill_root=SKILL_ROOT,
            )

    def test_repository_target_validation(self):
        repo = state()["activation"]["repository"]
        rs.assert_repository_target(repo, "OWNER/PROJECT", target_repository_id=123)
        with self.assertRaises(rs.ScopeError):
            rs.assert_repository_target(repo, "owner/other")
        with self.assertRaises(rs.ScopeError):
            rs.assert_repository_target(repo, "owner/project", target_repository_id=999)
        with self.assertRaises(rs.ScopeError):
            rs.assert_repository_target(repo, "owner/project")

    def test_activation_blocks_when_service_cannot_prove_child_isolation(self):
        for key in ("supervisor_profile_enforceable", "connector_read_adapter_receipts"):
            with self.subTest(key=key):
                unverifiable = {**CAPABILITY_PREFLIGHT, key: False}
                with self.assertRaises(rs.ScopeError):
                    rs.new_state(
                        activation_request(),
                        identity(),
                        activation_id="activation-0001",
                        orchestrator_thread_id="orchestrator-1",
                        installed_roundlet_digest=DIGEST,
                        owner_actor=OWNER_ACTOR,
                        capability_preflight=unverifiable,
                        orchestrator_creation_receipt=role_receipt("orchestrator", "orchestrator-1"),
                        skill_root=SKILL_ROOT,
                    )

    def test_activation_binds_verified_numeric_owner_actor(self):
        spoofed = {**OWNER_ACTOR, "verified_by_connector": False}
        with self.assertRaises(rs.ScopeError):
            rs.new_state(
                activation_request(),
                identity(),
                activation_id="activation-0001",
                orchestrator_thread_id="orchestrator-1",
                installed_roundlet_digest=DIGEST,
                owner_actor=spoofed,
                capability_preflight=CAPABILITY_PREFLIGHT,
                orchestrator_creation_receipt=role_receipt("orchestrator", "orchestrator-1"),
                skill_root=SKILL_ROOT,
            )


class StateMachineTests(unittest.TestCase):
    def test_normal_transition(self):
        value = state()
        rs.transition_state(value, "selecting-task")
        self.assertEqual(value["phase"], "selecting-task")

    def test_illegal_transition(self):
        with self.assertRaises(rs.TransitionError):
            rs.transition_state(state(), "merging")

    def test_expected_phase_is_enforced(self):
        with self.assertRaises(rs.TransitionError):
            rs.transition_state(state(), "selecting-task", expected_phase="idle")

    def test_assign_one_task(self):
        value = assigned_state()
        self.assertEqual(value["task"]["issue"], 11)
        with self.assertRaises(rs.TransitionError):
            rs.assign_task(
                value,
                umbrella_issue=10,
                issue=12,
                branch="codex/issue-12",
                worktree="/tmp/12",
                worker_thread_id="worker-12",
                worker_creation_receipt=role_receipt("worker", "worker-12"),
                base_sha=SHA_A,
            )

    def test_assign_rejects_unauthorized_umbrella(self):
        value = state()
        rs.transition_state(value, "selecting-task")
        set_selection(value, umbrella=99)
        with self.assertRaises(rs.ScopeError):
            rs.assign_task(
                value,
                umbrella_issue=99,
                issue=11,
                branch="codex/issue-11",
                worktree="/tmp/11",
                worker_thread_id="worker-11",
                worker_creation_receipt=role_receipt("worker", "worker-11"),
                base_sha=SHA_A,
            )

    def test_assign_rejects_non_codex_branch(self):
        value = state()
        rs.transition_state(value, "selecting-task")
        set_selection(value)
        with self.assertRaises(rs.ScopeError):
            rs.assign_task(
                value,
                umbrella_issue=10,
                issue=11,
                branch="feat/issue-11",
                worktree="/tmp/11",
                worker_thread_id="worker-11",
                worker_creation_receipt=role_receipt("worker", "worker-11"),
                base_sha=SHA_A,
            )

    def test_assign_rejects_unauthorized_worker_resource_creation(self):
        operations = activation_request()["authorize"]
        operations["create_task_branches"] = False
        value = state(operations=operations)
        rs.transition_state(value, "selecting-task")
        set_selection(value)
        with self.assertRaises(rs.ScopeError):
            rs.assign_task(
                value,
                umbrella_issue=10,
                issue=11,
                branch="codex/issue-11",
                worktree="/tmp/11",
                worker_thread_id="worker-11",
                worker_creation_receipt=role_receipt("worker", "worker-11"),
                base_sha=SHA_A,
            )
        self.assertIsNone(value["task"])

    def test_assign_binds_exact_selection_issue_and_base(self):
        value = state()
        rs.transition_state(value, "selecting-task")
        set_selection(value)
        with self.assertRaises(rs.ScopeError):
            rs.assign_task(
                value,
                umbrella_issue=10,
                issue=12,
                branch="codex/issue-12",
                worktree="/tmp/12",
                worker_thread_id="worker-12",
                worker_creation_receipt=role_receipt("worker", "worker-12"),
                base_sha=SHA_A,
            )
        stale = state()
        rs.transition_state(stale, "selecting-task")
        set_selection(stale, base=SHA_B)
        with self.assertRaises(rs.ScopeError):
            rs.assign_task(
                stale,
                umbrella_issue=10,
                issue=11,
                branch="codex/issue-11",
                worktree="/tmp/11",
                worker_thread_id="worker-11",
                worker_creation_receipt=role_receipt("worker", "worker-11"),
                base_sha=SHA_B,
            )

    def test_candidate_requires_clean_worktree(self):
        with self.assertRaises(rs.GuardError):
            rs.set_candidate(assigned_state(), SHA_B, clean=False)

    def test_draft_pr_receipt_binds_exact_task(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        self.assertEqual(value["phase"], "draft-pr")
        self.assertEqual(value["task"]["pr_number"], 22)

    def test_draft_pr_receipt_requires_live_open_draft_readback(self):
        for pr_state, draft in (("closed", True), ("open", False)):
            with self.subTest(pr_state=pr_state, draft=draft):
                value = assigned_state()
                rs.set_candidate(value, SHA_B, clean=True)
                with self.assertRaises(rs.GuardError):
                    record_draft(value, overrides={"pr_state": pr_state, "draft": draft})
                self.assertEqual(value["phase"], "worker-running")
                self.assertIsNone(value["task"]["draft_pr_receipt"])

    def test_draft_pr_rejects_wrong_repository(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        with self.assertRaises(rs.ScopeError):
            record_draft(value, overrides={"repository": "other/project"})

    def test_draft_and_premerge_reject_fork_head_or_wrong_base(self):
        for overrides in (
            {"base_branch": "release"},
            {"head_repository": "attacker/fork", "head_repository_id": 999},
        ):
            with self.subTest(overrides=overrides):
                value = assigned_state()
                rs.set_candidate(value, SHA_B, clean=True)
                with self.assertRaises(rs.ScopeError):
                    record_draft(value, overrides=overrides)
        value = premerge_state()
        live = premerge_live(value)
        live.update({"head_repository": "attacker/fork", "head_repository_id": 999})
        self.assertTrue(any("cross-repository" in error for error in rs.verify_premerge_gates(value, live)))

    def test_ready_merge_and_close_require_live_state_readback(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        begin_review(value, "supervisor-initial")
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-initial",
            candidate_sha=SHA_B,
            result="PASS",
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-initial")
        rs.set_candidate(value, SHA_B, clean=True)
        with self.assertRaises(rs.GuardError):
            record_ready(value, overrides={"draft": True})

        value = premerge_state()
        with self.assertRaises(rs.GuardError):
            record_merge(value, overrides={"merged": False})

        value = premerge_state()
        record_merge(value)
        with self.assertRaises(rs.GuardError):
            record_close(value, issue_state="open")

    def test_mark_ready_preflight_blocks_connector_before_side_effect(self):
        draft = assigned_state()
        rs.set_candidate(draft, SHA_B, clean=True)
        record_draft(draft)
        active_repair = copy.deepcopy(draft)
        active_repair["phase"] = "worker-repair"
        active_repair["task"]["active_role"] = "worker"
        for label, value in (("premature-draft", draft), ("active-worker", active_repair)):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                store = rs.StateStore(temporary)
                store.initialize(value)
                target = {
                    **pr_identity(value),
                    "pr_number": 22,
                    "pr_url": "https://github.com/owner/project/pull/22",
                    "pr_state": "open",
                    "draft": False,
                }
                calls = []
                with self.assertRaises((rs.GuardError, rs.TransitionError)):
                    rs.execute_github_mutation(
                        store,
                        operation="mark-ready",
                        idempotency_key=f"mark-ready-{label}",
                        target=target,
                        mutate=lambda item: calls.append(item) or target,
                    )
                self.assertEqual(calls, [])
                self.assertIsNone(store.load()["github_mutations"]["pending"])

    def test_premerge_cannot_enter_merging_without_gateway_intent(self):
        value = premerge_state()
        with self.assertRaises(rs.TransitionError):
            rs.transition_state(value, "merging")

    def test_false_operation_flags_block_before_every_connector_callback(self):
        states = []

        draft_state = assigned_state()
        rs.set_candidate(draft_state, SHA_B, clean=True)
        states.append(
            (
                draft_state,
                "create_draft_prs",
                "create-draft-pr",
                pr_identity(draft_state),
            )
        )

        ready_state = assigned_state()
        rs.set_candidate(ready_state, SHA_B, clean=True)
        record_draft(ready_state)
        begin_review(ready_state, "supervisor-initial")
        rs.accept_supervisor_result(
            ready_state,
            thread_id="supervisor-initial",
            candidate_sha=SHA_B,
            result="PASS",
        )
        rs.record_supervisor_archived(ready_state, supervisor_thread_id="supervisor-initial")
        rs.set_candidate(ready_state, SHA_B, clean=True)
        states.append(
            (
                ready_state,
                "mark_ready_for_review",
                "mark-ready",
                {
                    **pr_identity(ready_state),
                    "pr_number": 22,
                    "pr_url": "https://github.com/owner/project/pull/22",
                    "pr_state": "open",
                    "draft": False,
                },
            )
        )

        merge_state = premerge_state()
        states.append(
            (
                merge_state,
                "merge_commit_after_all_gates",
                "merge-pr",
                premerge_live(merge_state),
            )
        )

        close_state = premerge_state()
        record_merge(close_state)
        states.append(
            (
                close_state,
                "close_completed_sub_issues",
                "close-issue",
                {"repository": "owner/project", "repository_id": 123, "issue": 11},
            )
        )

        delete_state = premerge_state()
        record_merge(delete_state)
        record_close(delete_state)
        states.append(
            (
                delete_state,
                "delete_proven_task_owned_resources",
                "delete-remote-branch",
                {
                    "repository": "owner/project",
                    "repository_id": 123,
                    "branch": "codex/issue-11",
                },
            )
        )

        for value, flag, operation, target in states:
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as temporary:
                set_operation(value, flag, False)
                store = rs.StateStore(temporary)
                store.initialize(value)
                calls = []
                with self.assertRaises(rs.ScopeError):
                    rs.execute_github_mutation(
                        store,
                        operation=operation,
                        idempotency_key=f"blocked-{operation}-0001",
                        target=target,
                        mutate=lambda item: calls.append(item) or {"unexpected": True},
                    )
                self.assertEqual(calls, [])

    def test_github_gateway_records_before_mutation_and_reconciles_interruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = assigned_state()
            rs.set_candidate(value, SHA_B, clean=True)
            target = pr_identity(value)
            receipt = {
                **target,
                "issue": 11,
                "pr_number": 22,
                "pr_url": "https://github.com/owner/project/pull/22",
                "pr_state": "open",
                "draft": True,
            }
            store = rs.StateStore(temporary)
            store.initialize(value)
            pending = store.load()
            rs.begin_github_mutation_intent(
                pending,
                operation="create-draft-pr",
                idempotency_key="create-draft-pr-0001",
                target=target,
            )
            store.save(pending)
            calls = []
            result = rs.execute_github_mutation(
                store,
                operation="create-draft-pr",
                idempotency_key="create-draft-pr-0001",
                target=target,
                mutate=lambda item: self.fail("pending connector mutation must not retry blindly"),
                reconcile=lambda item: calls.append(item) or receipt,
            )
            self.assertEqual(result["pr_number"], 22)
            self.assertEqual(len(calls), 1)
            current = store.load()
            self.assertEqual(current["phase"], "draft-pr")
            self.assertIsNone(current["github_mutations"]["pending"])
            self.assertEqual(
                current["github_mutations"]["receipts"]["create-draft-pr-0001"]["status"],
                "complete",
            )

    def test_worker_and_supervisor_capability_receipts_fail_closed(self):
        value = state()
        set_selection(value)
        github_worker = {**role_receipt("worker", "worker-11"), "github_connector": True}
        with self.assertRaises(rs.ScopeError):
            rs.assign_task(
                value,
                umbrella_issue=10,
                issue=11,
                branch="codex/issue-11",
                worktree="/tmp/11",
                worker_thread_id="worker-11",
                worker_creation_receipt=github_worker,
                base_sha=SHA_A,
            )

        bad_fields = {
            "model": "gpt-5.5",
            "forked": True,
            "permission_profile": "workspace-write",
            "github_connector": True,
        }
        for field, bad_value in bad_fields.items():
            with self.subTest(field=field):
                candidate = assigned_state()
                rs.set_candidate(candidate, SHA_B, clean=True)
                record_draft(candidate)
                service = {**role_receipt("supervisor", "supervisor-bad"), field: bad_value}
                with self.assertRaises(rs.ScopeError):
                    rs.begin_supervisor(
                        candidate,
                        "supervisor-bad",
                        creation_receipt={
                            "activation_id": candidate["activation"]["id"],
                            "issue": 11,
                            "generation": 1,
                            "installed_roundlet_digest": value["skill"]["content_digest"],
                            "review_contract": value["versions"]["review_contract"],
                            "created": True,
                            "service_receipt": service,
                        },
                    )

    def test_merge_then_exact_issue_close_receipts(self):
        value = premerge_state()
        record_merge(value)
        self.assertEqual(value["phase"], "closing-issue")
        record_close(value)
        self.assertEqual(value["phase"], "cleanup")
        self.assertEqual(value["task"]["issue_close_receipt"]["issue"], 11)

    def test_issue_close_rejects_unselected_issue(self):
        value = premerge_state()
        record_merge(value)
        with self.assertRaises(rs.ScopeError):
            record_close(value, issue=12)

    def test_candidate_change_invalidates_pass(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        rs.transition_state(value, "draft-pr")
        value["task"]["active_role"] = None
        begin_review(value, "supervisor-1")
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-1",
            candidate_sha=SHA_B,
            result="PASS",
        )
        self.assertIsNotNone(value["review"]["pass_identity"])
        rs.set_candidate(value, SHA_C, clean=True)
        self.assertIsNone(value["review"]["pass_identity"])

    def test_fresh_supervisor_is_enforced(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        rs.transition_state(value, "draft-pr")
        value["task"]["active_role"] = None
        begin_review(value, "supervisor-1")
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-1",
            candidate_sha=SHA_B,
            result="FINDINGS",
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-1")
        value["task"]["active_role"] = None
        with self.assertRaises(rs.ValidationError):
            begin_review(value, "supervisor-1")

    def test_review_budget_exhaustion_requires_worker_finalization(self):
        value = assigned_state()
        set_review_budget(value, 1)
        rs.set_candidate(value, SHA_B, clean=True)
        value["task"].update({"pr_number": 22, "pr_url": "https://github.com/owner/project/pull/22"})
        value["task"]["pr_ready"] = True
        value["phase"] = "ready"
        begin_review(value, "supervisor-budget", final=True)
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-budget",
            candidate_sha=SHA_B,
            result="FINDINGS",
            non_blocking_items=["fix this"],
        )
        self.assertEqual(value["phase"], "final-worker-repair")
        rs.validate_mailbox_envelope(
            {
                "protocol_version": value["versions"]["protocol"],
                "review_contract_version": value["versions"]["review_contract"],
                "activation_id": value["activation"]["id"],
                "repository": "owner/project",
                "repository_id": 123,
                "selected_issue": 11,
                "source_role": "worker",
                "source_thread_id": "worker-11",
                "phase": "final-worker-repair",
                "base_sha": SHA_A,
                "candidate_sha": SHA_C,
                "idempotency_key": "final-worker-0001",
                "timestamp": "2026-07-14T00:00:01Z",
            },
            value,
            "worker-handoff",
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-budget")
        value["task"]["active_role"] = None
        value["phase"] = "draft-pr"
        with self.assertRaises((rs.GuardError, rs.TransitionError)):
            begin_review(value, "supervisor-too-many")
        value["phase"] = "final-worker-repair"
        value["task"]["active_role"] = "worker"
        rs.record_worker_final_dispositions(
            value,
            worker_thread_id="worker-11",
            head_sha=SHA_C,
            clean=True,
            tests_passed=True,
            dispositions=[{"finding": "fix this", "disposition": "FIXED", "evidence": "test"}],
        )
        self.assertEqual(value["review"]["exhaustion"]["reviewed_candidate_sha"], SHA_B)
        self.assertEqual(value["review"]["exhaustion"]["final_candidate_sha"], SHA_C)
        self.assertEqual(value["task"]["candidate_sha"], SHA_C)
        self.assertEqual(value["phase"], "ready")
        rs.begin_worker_merge_readiness(value)
        rs.record_worker_ready_to_merge(value, worker_thread_id="worker-11", head_sha=SHA_C, clean=True)
        self.assertEqual(value["phase"], "pre-merge")
        self.assertEqual(rs.verify_premerge_gates(value, premerge_live(value)), [])

    def test_supervisor_budget_preflight_blocks_creation_callback(self):
        value = assigned_state()
        set_review_budget(value, 1)
        rs.set_candidate(value, SHA_B, clean=True)
        value["phase"] = "draft-pr"
        value["review"].update(
            {
                "round": 1,
                "archived_supervisor_count": 1,
                "last_supervisor_created_at": "2026-07-14T00:00:00.000001Z",
            }
        )
        calls = []
        with self.assertRaises(rs.GuardError):
            rs.create_supervisor_after_preflight(
                value,
                final=False,
                create_task=lambda preflight: calls.append(preflight) or {},
            )
        self.assertEqual(calls, [])

    def test_supervisor_guidance_is_round_aware_and_reaches_creation_callback(self):
        fresh = assigned_state()
        rs.set_candidate(fresh, SHA_B, clean=True)
        record_draft(fresh)
        for generation in range(1, 4):
            thread_id = f"supervisor-complete-{generation}"
            begin_review(fresh, thread_id)
            rs.accept_supervisor_result(
                fresh,
                thread_id=thread_id,
                candidate_sha=SHA_B,
                result="FINDINGS",
                non_blocking_items=[f"finding-{generation}"],
            )
            rs.record_supervisor_archived(fresh, supervisor_thread_id=thread_id)
            rs.set_candidate(fresh, SHA_B, clean=True)
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(fresh)
            seen = []

            def create(intent):
                seen.append(intent)
                generation = intent["generation"]
                thread_id = f"supervisor-guidance-{generation}"
                return {
                    "thread_id": thread_id,
                    "creation_receipt": {
                        "activation_id": intent["activation_id"],
                        "issue": intent["issue"],
                        "generation": generation,
                        "installed_roundlet_digest": intent["installed_roundlet_digest"],
                        "review_contract": intent["review_contract"],
                        "created": True,
                        "service_receipt": role_receipt(
                            "supervisor", thread_id, created_at=f"2026-07-14T00:00:00.{generation:06d}Z"
                        ),
                    },
                }

            rs.create_supervisor_after_preflight(
                fresh,
                final=False,
                state_store=store,
                create_task=create,
            )
            fresh = store.load()
            rs.accept_supervisor_result(
                fresh,
                thread_id="supervisor-guidance-4",
                candidate_sha=SHA_B,
                result="FINDINGS",
                non_blocking_items=["finding-4"],
            )
            store.save(fresh)
            fresh = store.load()
            rs.record_supervisor_archived(fresh, supervisor_thread_id="supervisor-guidance-4")
            rs.set_candidate(fresh, SHA_B, clean=True)
            record_ready(fresh)
            store.save(fresh)
            rs.create_supervisor_after_preflight(
                fresh,
                final=True,
                state_store=store,
                create_task=create,
            )
        for generation, final in ((4, False), (5, True)):
            intent = seen[generation - 4]
            self.assertEqual(intent["generation"], generation)
            self.assertIs(intent["final"], final)
            self.assertEqual(
                intent["guidance"],
                {
                    "current_cycle": generation,
                    "completed_cycles": generation - 1,
                    "max_cycles": 5,
                    "converge_after_cycles": 3,
                    "mode": "CONVERGING",
                    "directive": (
                        "After 3 complete Supervisor reviews, begin progressively converging the review. "
                        "Prioritize regressions against earlier findings and independently reproducible blocking "
                        "correctness, safety, authority, or contract failures. Do not expand into speculative or "
                        "non-blocking cleanup. Do not suppress a newly discovered blocking finding."
                    ),
                },
            )
            self.assertEqual(intent["guidance_digest"], rs.digest_json(intent["guidance"]))
        equality = assigned_state()
        set_review_budget(equality, 3, converge_after=3)
        rs.set_candidate(equality, SHA_B, clean=True)
        equality["phase"] = "draft-pr"
        equality["review"].update(
            {"round": 2, "archived_supervisor_count": 2, "last_supervisor_created_at": "2026-07-14T00:00:00.000002Z"}
        )
        self.assertEqual(rs.supervisor_review_guidance(equality)["mode"], "COMPLETE")

    def test_maintenance_discard_does_not_advance_convergence(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        for generation in (1, 2):
            thread_id = f"supervisor-completed-{generation}"
            begin_review(value, thread_id)
            rs.accept_supervisor_result(
                value,
                thread_id=thread_id,
                candidate_sha=SHA_B,
                result="FINDINGS",
                non_blocking_items=[f"finding-{generation}"],
            )
            rs.record_supervisor_archived(value, supervisor_thread_id=thread_id)
            rs.set_candidate(value, SHA_B, clean=True)
        begin_review(value, "supervisor-discarded")
        rs.request_maintenance(value, "interrupt incomplete review")
        rs.discard_supervisor_for_maintenance(value, supervisor_thread_id="supervisor-discarded")
        rs.create_maintenance_checkpoint(
            value, checkpoint_id="checkpoint-001", schedule_id="schedule-1", schedule_state="paused"
        )
        rs.resume_maintenance(
            value,
            checkpoint_id="checkpoint-001",
            installed_roundlet_digest=DIGEST,
            current_versions=value["versions"],
            repository_identity=identity(),
            schedule_id="schedule-1",
        )
        self.assertEqual(value["review"]["round"], 3)
        self.assertEqual(value["review"]["completed_supervisor_count"], 2)
        self.assertEqual(
            rs.preflight_supervisor_creation(value)["guidance"],
            {
                "current_cycle": 4,
                "completed_cycles": 2,
                "max_cycles": 5,
                "converge_after_cycles": 3,
                "mode": "COMPLETE",
                "directive": (
                    "Perform a complete independent review of the supplied contract. Report every newly "
                    "discovered actionable P0/P1/P2 correctness, safety, authority, or contract failure."
                ),
            },
        )
        begin_review(value, "supervisor-completed-3")
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-completed-3",
            candidate_sha=SHA_B,
            result="FINDINGS",
            non_blocking_items=["finding-3"],
        )
        rs.validate_state(value)
        self.assertEqual(
            value["review"]["completed_supervisor_results"][-1],
            {"thread_id": "supervisor-completed-3", "generation": 4, "result": "FINDINGS"},
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-completed-3")
        rs.set_candidate(value, SHA_B, clean=True)
        self.assertEqual(rs.preflight_supervisor_creation(value)["guidance"]["mode"], "CONVERGING")

    def test_inflated_completed_counter_fails_before_preflight(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        for generation in range(1, 4):
            thread_id = f"supervisor-discarded-{generation}"
            begin_review(value, thread_id)
            rs.request_maintenance(value, "interrupt incomplete review")
            rs.discard_supervisor_for_maintenance(value, supervisor_thread_id=thread_id)
            rs.create_maintenance_checkpoint(
                value,
                checkpoint_id=f"checkpoint-{generation:03d}",
                schedule_id="schedule-1",
                schedule_state="paused",
            )
            rs.resume_maintenance(
                value,
                checkpoint_id=f"checkpoint-{generation:03d}",
                installed_roundlet_digest=DIGEST,
                current_versions=value["versions"],
                repository_identity=identity(),
                schedule_id="schedule-1",
            )
        self.assertEqual(value["review"]["completed_supervisor_count"], 0)
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(value)
            tampered = store.load()
            tampered["review"]["completed_supervisor_count"] = 3
            rs.atomic_write_json(store.path, tampered)
            with self.assertRaisesRegex(rs.ValidationError, "durable result evidence"):
                store.load()

    def test_unarchived_supervisor_must_be_the_exact_latest_completion(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        for generation in (1, 2):
            thread_id = f"supervisor-boundary-{generation}"
            begin_review(value, thread_id)
            rs.accept_supervisor_result(
                value,
                thread_id=thread_id,
                candidate_sha=SHA_B,
                result="FINDINGS",
                non_blocking_items=[f"finding-{generation}"],
            )
            rs.record_supervisor_archived(value, supervisor_thread_id=thread_id)
            rs.set_candidate(value, SHA_B, clean=True)
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(value)
            value = store.load()
            begin_review(value, "supervisor-boundary-3")
            store.save(value)
            value = store.load()
            rs.accept_supervisor_result(
                value,
                thread_id="supervisor-boundary-3",
                candidate_sha=SHA_B,
                result="FINDINGS",
                non_blocking_items=["finding-3"],
            )
            store.save(value)
            tampered = store.load()
            tampered["review"]["unarchived_supervisor_thread_ids"] = ["supervisor-boundary-1"]
            rs.atomic_write_json(store.path, tampered)
            with self.assertRaisesRegex(rs.ValidationError, "unarchived Supervisor is not the latest"):
                store.load()
            with self.assertRaisesRegex(rs.ScopeError, "accepted result commitment"):
                rs.record_supervisor_archived(tampered, supervisor_thread_id="supervisor-boundary-1")
            with self.assertRaisesRegex(rs.ValidationError, "unarchived Supervisor is not the latest"):
                rs.preflight_supervisor_creation(tampered)

    def test_active_supervisor_cannot_have_completion_evidence(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        for generation in (1, 2):
            thread_id = f"supervisor-active-boundary-{generation}"
            begin_review(value, thread_id)
            rs.accept_supervisor_result(
                value,
                thread_id=thread_id,
                candidate_sha=SHA_B,
                result="FINDINGS",
                non_blocking_items=[f"finding-{generation}"],
            )
            rs.record_supervisor_archived(value, supervisor_thread_id=thread_id)
            rs.set_candidate(value, SHA_B, clean=True)
        begin_review(value, "supervisor-active-boundary-3")
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(value)
            tampered = store.load()
            review = tampered["review"]
            review["completed_supervisor_count"] = 3
            review["completed_supervisor_results"].append(
                {"thread_id": "supervisor-active-boundary-3", "generation": 3, "result": "FINDINGS"}
            )
            review["completed_supervisor_digest"] = rs.fold_archive_digest(
                "0" * 64, review["completed_supervisor_results"]
            )
            rs.atomic_write_json(store.path, tampered)
            with self.assertRaisesRegex(rs.ValidationError, "active Supervisor has durable completion evidence"):
                store.load()
            with self.assertRaisesRegex(rs.ValidationError, "active Supervisor has durable completion evidence"):
                rs.preflight_supervisor_creation(tampered)
            rs.request_maintenance(tampered, "interrupt forged active completion")
            with self.assertRaisesRegex(rs.ValidationError, "active Supervisor has durable completion evidence"):
                rs.discard_supervisor_for_maintenance(
                    tampered, supervisor_thread_id="supervisor-active-boundary-3"
                )

    def test_active_supervisor_cannot_be_archived_before_result_acceptance(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        begin_review(value, "supervisor-active-archived")
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(value)
            tampered = store.load()
            review = tampered["review"]
            review["unarchived_supervisor_thread_ids"] = []
            review["archived_supervisor_count"] = 1
            review["archived_supervisor_digest"] = rs.fold_archive_digest(
                "0" * 64, "supervisor-active-archived"
            )
            rs.atomic_write_json(store.path, tampered)
            with self.assertRaisesRegex(rs.ValidationError, "sole latest unarchived"):
                store.load()
            with self.assertRaisesRegex(rs.ValidationError, "sole latest unarchived"):
                rs.accept_supervisor_result(
                    tampered,
                    thread_id="supervisor-active-archived",
                    candidate_sha=SHA_B,
                    result="FINDINGS",
                    non_blocking_items=["forged archival boundary"],
                )
            rs.request_maintenance(tampered, "interrupt forged active archive")
            with self.assertRaisesRegex(rs.ValidationError, "sole latest unarchived"):
                rs.discard_supervisor_for_maintenance(
                    tampered, supervisor_thread_id="supervisor-active-archived"
                )

    def test_discarded_supervisors_cannot_be_forged_into_completed_reviews(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        for generation in range(1, 4):
            thread_id = f"supervisor-discard-outcome-{generation}"
            begin_review(value, thread_id)
            rs.request_maintenance(value, "interrupt incomplete review")
            rs.discard_supervisor_for_maintenance(value, supervisor_thread_id=thread_id)
            rs.create_maintenance_checkpoint(
                value,
                checkpoint_id=f"checkpoint-{generation:03d}",
                schedule_id="schedule-1",
                schedule_state="paused",
            )
            rs.resume_maintenance(
                value,
                checkpoint_id=f"checkpoint-{generation:03d}",
                installed_roundlet_digest=DIGEST,
                current_versions=value["versions"],
                repository_identity=identity(),
                schedule_id="schedule-1",
            )
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(value)
            tampered = store.load()
            review = tampered["review"]
            review["completed_supervisor_count"] = 3
            review["completed_supervisor_results"] = [
                {
                    "thread_id": f"supervisor-discard-outcome-{generation}",
                    "generation": generation,
                    "result": "FINDINGS",
                }
                for generation in range(1, 4)
            ]
            review["completed_supervisor_digest"] = rs.fold_archive_digest(
                "0" * 64, review["completed_supervisor_results"]
            )
            rs.atomic_write_json(store.path, tampered)
            with self.assertRaisesRegex(rs.ValidationError, "completed archive outcome"):
                store.load()
            with self.assertRaisesRegex(rs.ValidationError, "completed archive outcome"):
                rs.preflight_supervisor_creation(tampered)

    def test_discarded_outcomes_cannot_be_rewritten_with_completion_evidence(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        for generation in range(1, 4):
            thread_id = f"supervisor-discard-commitment-{generation}"
            begin_review(value, thread_id)
            rs.request_maintenance(value, "interrupt incomplete review")
            rs.discard_supervisor_for_maintenance(value, supervisor_thread_id=thread_id)
            rs.create_maintenance_checkpoint(
                value,
                checkpoint_id=f"checkpoint-{generation:03d}",
                schedule_id="schedule-1",
                schedule_state="paused",
            )
            rs.resume_maintenance(
                value,
                checkpoint_id=f"checkpoint-{generation:03d}",
                installed_roundlet_digest=DIGEST,
                current_versions=value["versions"],
                repository_identity=identity(),
                schedule_id="schedule-1",
            )
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(value)
            tampered = store.load()
            original_state = copy.deepcopy(dict(tampered))
            original_authority = rs.read_json(store.supervisor_archive_authority_path)
            review = tampered["review"]
            predecessor = "0" * 64
            forged_outcomes = []
            for generation in range(1, 4):
                payload = {
                    "thread_id": f"supervisor-discard-commitment-{generation}",
                    "generation": generation,
                    "outcome": "COMPLETED",
                }
                archive_digest = rs.fold_archive_digest(predecessor, [payload])
                forged_outcomes.append(
                    {**payload, "predecessor_digest": predecessor, "archive_digest": archive_digest}
                )
                predecessor = archive_digest
            review["completed_supervisor_count"] = 3
            review["completed_supervisor_results"] = [
                {
                    "thread_id": f"supervisor-discard-commitment-{generation}",
                    "generation": generation,
                    "result": "FINDINGS",
                }
                for generation in range(1, 4)
            ]
            review["completed_supervisor_digest"] = rs.fold_archive_digest(
                "0" * 64, review["completed_supervisor_results"]
            )
            review["archived_supervisor_outcomes"] = forged_outcomes
            review["archived_supervisor_outcome_digest"] = rs.fold_archive_digest(
                "0" * 64, forged_outcomes
            )
            review["archived_supervisor_digest"] = predecessor
            rs.atomic_write_json(store.path, tampered)
            rs.atomic_write_json(
                store.supervisor_archive_transaction_path,
                rs._archive_transaction(
                    original_state,
                    tampered,
                    original_authority,
                    rs._archive_authority_from_state(tampered),
                ),
            )
            with self.assertRaisesRegex(rs.ScopeError, "impossible state-ahead"):
                store.load()
            with self.assertRaisesRegex(rs.ScopeError, "archive authority"):
                rs.preflight_supervisor_creation(tampered)

    def test_uncommitted_supervisor_result_cannot_be_archived_or_saved(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(value)
            durable = store.load()
            begin_review(durable, "supervisor-pending-commitment")
            store.save(durable)

            forged = store.load()
            review = forged["review"]
            review["current_supervisor_thread_id"] = None
            review["last_result"] = "FINDINGS"
            review["completed_supervisor_count"] = 1
            review["completed_supervisor_results"] = [
                {
                    "thread_id": "supervisor-pending-commitment",
                    "generation": 1,
                    "result": "FINDINGS",
                }
            ]
            review["completed_supervisor_digest"] = rs.fold_archive_digest(
                "0" * 64, review["completed_supervisor_results"]
            )
            forged["task"]["active_role"] = None
            rs.transition_state(forged, "worker-repair")
            with self.assertRaisesRegex(rs.ScopeError, "accepted result commitment"):
                rs.record_supervisor_archived(
                    forged, supervisor_thread_id="supervisor-pending-commitment"
                )
            with self.assertRaisesRegex(rs.ScopeError, "accepted result commitment"):
                store.save(forged)
            with self.assertRaisesRegex(rs.ScopeError, "accepted result commitment"):
                rs.preflight_supervisor_creation(forged)

            accepted = store.load()
            rs.accept_supervisor_result(
                accepted,
                thread_id="supervisor-pending-commitment",
                candidate_sha=SHA_B,
                result="FINDINGS",
                non_blocking_items=["normal accepted result"],
            )
            store.save(accepted)
            committed = store.load()
            self.assertIsNotNone(
                committed.supervisor_archive_authority["pending_completion"]
            )
            rs.record_supervisor_archived(
                committed, supervisor_thread_id="supervisor-pending-commitment"
            )
            store.save(committed)
            archived = store.load()
            self.assertEqual(
                archived["review"]["archived_supervisor_outcomes"][-1]["outcome"], "COMPLETED"
            )
            self.assertIsNone(archived.supervisor_archive_authority["pending_completion"])

    def test_multi_outcome_append_cannot_batch_forged_completions(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        for generation in range(1, 5):
            thread_id = f"supervisor-batch-discard-{generation}"
            begin_review(value, thread_id)
            rs.request_maintenance(value, "interrupt incomplete review")
            rs.discard_supervisor_for_maintenance(value, supervisor_thread_id=thread_id)
            rs.create_maintenance_checkpoint(
                value,
                checkpoint_id=f"batch-checkpoint-{generation:03d}",
                schedule_id="schedule-1",
                schedule_state="paused",
            )
            rs.resume_maintenance(
                value,
                checkpoint_id=f"batch-checkpoint-{generation:03d}",
                installed_roundlet_digest=DIGEST,
                current_versions=value["versions"],
                repository_identity=identity(),
                schedule_id="schedule-1",
            )
        forged = copy.deepcopy(value)
        review = forged["review"]
        predecessor = "0" * 64
        outcomes = []
        for generation in range(1, 5):
            outcome = "COMPLETED" if generation < 4 else "DISCARDED"
            payload = {
                "thread_id": f"supervisor-batch-discard-{generation}",
                "generation": generation,
                "outcome": outcome,
            }
            archive_digest = rs.fold_archive_digest(predecessor, [payload])
            outcomes.append(
                {**payload, "predecessor_digest": predecessor, "archive_digest": archive_digest}
            )
            predecessor = archive_digest
        review["completed_supervisor_count"] = 3
        review["completed_supervisor_results"] = [
            {
                "thread_id": f"supervisor-batch-discard-{generation}",
                "generation": generation,
                "result": "FINDINGS",
            }
            for generation in range(1, 4)
        ]
        review["completed_supervisor_digest"] = rs.fold_archive_digest(
            "0" * 64, review["completed_supervisor_results"]
        )
        review["archived_supervisor_outcomes"] = outcomes
        review["archived_supervisor_outcome_digest"] = rs.fold_archive_digest(
            "0" * 64, outcomes
        )
        review["archived_supervisor_digest"] = predecessor
        rs.validate_state(forged)

        initial = assigned_state()
        rs.set_candidate(initial, SHA_B, clean=True)
        record_draft(initial)
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(initial)
            with self.assertRaisesRegex(rs.ScopeError, "append only one outcome"):
                store.save(forged)
            self.assertEqual(store.load()["review"]["round"], 0)
            forged_with_authority = rs._MigrationAuthorizedState(
                forged,
                supervisor_archive_authority=rs.read_json(
                    store.supervisor_archive_authority_path
                ),
            )
            with self.assertRaisesRegex(rs.ScopeError, "differs from durable outcome history"):
                rs.preflight_supervisor_creation(forged_with_authority)

    def test_supervisor_creation_reconciles_a_durable_intent_after_interruption(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        value["phase"] = "draft-pr"
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(value)
            creations = []
            with self.assertRaises(rs.ValidationError):
                rs.create_supervisor_after_preflight(
                    value,
                    final=False,
                    state_store=store,
                    create_task=lambda intent: creations.append(intent) or {},
                )
            durable = store.load()
            self.assertIsNotNone(durable["review"]["supervisor_creation_intent"])
            self.assertEqual(len(creations), 1)
            rs.create_supervisor_after_preflight(
                value,
                final=False,
                state_store=store,
                create_task=lambda intent: self.fail("must reconcile instead of creating twice"),
                reconcile_task=lambda intent: {
                    "thread_id": "supervisor-reconciled",
                    "creation_receipt": {
                        "activation_id": intent["activation_id"],
                        "issue": intent["issue"],
                        "generation": intent["generation"],
                        "installed_roundlet_digest": intent["installed_roundlet_digest"],
                        "review_contract": intent["review_contract"],
                        "created": True,
                        "service_receipt": role_receipt(
                            "supervisor", "supervisor-reconciled", created_at="2026-07-14T00:00:00.000001Z"
                        ),
                    },
                },
            )
            self.assertEqual(len(creations), 1)
            self.assertEqual(store.load()["review"]["round"], 1)

    def test_exhausted_findings_require_exact_identity_and_archival(self):
        value = assigned_state()
        set_review_budget(value, 1)
        rs.set_candidate(value, SHA_B, clean=True)
        value["task"].update({"pr_number": 22, "pr_url": "https://github.com/owner/project/pull/22"})
        value["task"]["pr_ready"] = True
        value["phase"] = "ready"
        begin_review(value, "supervisor-budget", final=True)
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-budget",
            candidate_sha=SHA_B,
            result="FINDINGS",
            non_blocking_items=["real finding"],
        )
        with self.assertRaisesRegex(rs.GuardError, "archived"):
            rs.record_worker_final_dispositions(
                value,
                worker_thread_id="worker-11",
                head_sha=SHA_C,
                clean=True,
                tests_passed=True,
                dispositions=[{"finding": "real finding", "disposition": "FIXED", "evidence": "test"}],
            )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-budget")
        with self.assertRaisesRegex(rs.GuardError, "tests"):
            rs.record_worker_final_dispositions(
                value,
                worker_thread_id="worker-11",
                head_sha=SHA_C,
                clean=True,
                tests_passed=False,
                dispositions=[{"finding": "real finding", "disposition": "FIXED", "evidence": "test"}],
            )
        with self.assertRaisesRegex(rs.GuardError, "bind each exhausted finding"):
            rs.record_worker_final_dispositions(
                value,
                worker_thread_id="worker-11",
                head_sha=SHA_C,
                clean=True,
                tests_passed=True,
                dispositions=[{"finding": "different arbitrary finding", "disposition": "FIXED", "evidence": "test"}],
            )
        rs.record_worker_final_dispositions(
            value,
            worker_thread_id="worker-11",
            head_sha=SHA_C,
            clean=True,
            tests_passed=True,
            dispositions=[{"finding": "real finding", "disposition": "FIXED", "evidence": "test"}],
        )
        tampered = copy.deepcopy(value)
        tampered["review"]["exhaustion"]["worker_findings_digest"] = "0" * 64
        with self.assertRaisesRegex(rs.ValidationError, "finding identities"):
            rs.validate_state(tampered)

    def test_ready_stage_exhaustion_accepts_repaired_head(self):
        value = assigned_state()
        set_review_budget(value, 2)
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        begin_review(value, "supervisor-initial")
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-initial",
            candidate_sha=SHA_B,
            result="PASS",
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-initial")
        rs.set_candidate(value, SHA_B, clean=True)
        record_ready(value)
        begin_review(value, "supervisor-final", final=True)
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-final",
            candidate_sha=SHA_B,
            result="FINDINGS",
            non_blocking_items=["ready-stage finding"],
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-final")
        rs.record_worker_final_dispositions(
            value,
            worker_thread_id="worker-11",
            head_sha=SHA_C,
            clean=True,
            tests_passed=True,
            dispositions=[{"finding": "ready-stage finding", "disposition": "FIXED", "evidence": "test"}],
        )
        self.assertEqual(value["phase"], "ready")
        self.assertIsNone(value["task"]["active_role"])
        rs.begin_worker_merge_readiness(value)
        rs.record_worker_ready_to_merge(value, worker_thread_id="worker-11", head_sha=SHA_C, clean=True)
        self.assertEqual(value["phase"], "pre-merge")

    def test_max_one_reserves_a_real_final_supervisor_after_ready_readback(self):
        value = assigned_state()
        set_review_budget(value, 1)
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        record_ready(value)
        begin_review(value, "supervisor-only", final=True)
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-only",
            candidate_sha=SHA_B,
            result="PASS",
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-only")
        self.assertEqual(value["review"]["pass_identity"]["stage"], "final")
        self.assertEqual(value["task"]["active_role"], "worker")
        rs.record_worker_ready_to_merge(value, worker_thread_id="worker-11", head_sha=SHA_B, clean=True)
        self.assertEqual(value["phase"], "pre-merge")

    def test_default_budget_reserves_round_five_for_a_real_final_review(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        for review_round in range(1, 5):
            thread_id = f"supervisor-{review_round}"
            begin_review(value, thread_id)
            rs.accept_supervisor_result(
                value,
                thread_id=thread_id,
                candidate_sha=SHA_B,
                result="FINDINGS",
                non_blocking_items=[f"finding-{review_round}"],
            )
            rs.record_supervisor_archived(value, supervisor_thread_id=thread_id)
            rs.set_candidate(value, SHA_B, clean=True)
        record_ready(value)
        begin_review(value, "supervisor-5", final=True)
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-5",
            candidate_sha=SHA_B,
            result="PASS",
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-5")
        self.assertEqual(value["review"]["pass_identity"]["stage"], "final")
        rs.record_worker_ready_to_merge(value, worker_thread_id="worker-11", head_sha=SHA_B, clean=True)
        self.assertEqual(value["phase"], "pre-merge")

    def test_default_budget_allows_round_five_ready_findings(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        for review_round in range(1, 5):
            thread_id = f"supervisor-{review_round}"
            begin_review(value, thread_id)
            rs.accept_supervisor_result(
                value,
                thread_id=thread_id,
                candidate_sha=SHA_B,
                result="FINDINGS",
                non_blocking_items=[f"finding-{review_round}"],
            )
            rs.record_supervisor_archived(value, supervisor_thread_id=thread_id)
            rs.set_candidate(value, SHA_B, clean=True)
        record_ready(value)
        begin_review(value, "supervisor-5", final=True)
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-5",
            candidate_sha=SHA_B,
            result="FINDINGS",
            non_blocking_items=["fifth ready finding"],
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-5")
        rs.record_worker_final_dispositions(
            value,
            worker_thread_id="worker-11",
            head_sha=SHA_C,
            clean=True,
            tests_passed=True,
            dispositions=[
                {
                    "finding": "fifth ready finding",
                    "disposition": "FIXED",
                    "evidence": "regression test",
                }
            ],
        )
        self.assertEqual(value["phase"], "ready")
        self.assertEqual(value["review"]["exhaustion"]["round"], 5)

    def test_default_budget_allows_round_five_draft_findings_and_then_stops(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        for review_round in range(1, 5):
            thread_id = f"supervisor-{review_round}"
            begin_review(value, thread_id)
            rs.accept_supervisor_result(
                value,
                thread_id=thread_id,
                candidate_sha=SHA_B,
                result="FINDINGS",
                non_blocking_items=[f"finding-{review_round}"],
            )
            rs.record_supervisor_archived(value, supervisor_thread_id=thread_id)
            rs.set_candidate(value, SHA_B, clean=True)

        begin_review(value, "supervisor-5")
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-5",
            candidate_sha=SHA_B,
            result="FINDINGS",
            non_blocking_items=["fifth draft finding"],
        )
        self.assertEqual(value["phase"], "final-worker-repair")
        self.assertEqual(value["review"]["exhaustion"]["round"], 5)
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-5")
        denied = copy.deepcopy(value)
        denied["task"]["active_role"] = None
        denied["phase"] = "draft-pr"
        with self.assertRaisesRegex(rs.GuardError, "budget is exhausted"):
            rs.preflight_supervisor_creation(denied)

    def test_last_slot_draft_pass_cannot_be_promoted_to_final_pass(self):
        value = assigned_state()
        set_review_budget(value, 1)
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        begin_review(value, "supervisor-draft-only")
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-draft-only",
            candidate_sha=SHA_B,
            result="PASS",
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-draft-only")
        rs.set_candidate(value, SHA_B, clean=True)
        with self.assertRaisesRegex(rs.GuardError, "cannot be promoted"):
            rs.preflight_mark_ready(value, head_sha=SHA_B)

    def test_legacy_review_history_stays_bounded_across_two_hundred_rounds(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        value["task"]["pr_number"] = 22
        value["phase"] = "draft-pr"
        downgrade_to_schema5_unbounded(value)
        rs.request_maintenance(value, "schema-6 migration")
        rs.create_maintenance_checkpoint(
            value,
            checkpoint_id="checkpoint-001",
            schedule_id="schedule-1",
            schedule_state="paused",
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            rs.atomic_write_json(store.path, value)
            value = store.migrate(
                activation_id="activation-0001",
                checkpoint_id="checkpoint-001",
                schedule_id="schedule-1",
                expected_installed_digest=DIGEST,
                expected_from_schema=5,
                skill_root=SKILL_ROOT,
            )
            value = store.load()
            rs.resume_maintenance(
                value,
                checkpoint_id="checkpoint-001",
                installed_roundlet_digest=DIGEST,
                current_versions=value["versions"],
                repository_identity=identity(),
                schedule_id="schedule-1",
            )
            for review_round in range(1, 201):
                thread_id = f"supervisor-{review_round}"
                begin_review(value, thread_id)
                rs.accept_supervisor_result(
                    value,
                    thread_id=thread_id,
                    candidate_sha=SHA_B,
                    result="FINDINGS",
                    non_blocking_items=[f"finding-{review_round}"],
                )
                store.save(value)
                value = store.load()
                rs.record_supervisor_archived(value, supervisor_thread_id=thread_id)
                rs.set_candidate(value, SHA_B, clean=True)
                store.save(value)
                value = store.load()
            store.save(value)
            value = store.load()
            rs.validate_state(value)
            self.assertEqual(value["review"]["round"], 200)
            self.assertEqual(value["review"]["archived_supervisor_count"], 200)
            self.assertLessEqual(len(value["review"]["supervisor_thread_ids"]), 64)
            self.assertEqual(value["review"]["unarchived_supervisor_thread_ids"], [])
            self.assertLess(len(rs.canonical_json(value).encode("utf-8")), rs.MAX_STATE_BYTES)

    def test_fresh_activation_cannot_select_legacy_unbounded_review(self):
        value = assigned_state()
        set_review_budget(value, 64, legacy_unbounded=True)
        value["activation"]["legacy_review_migration"] = {
            "from_schema": 5,
            "input_digest": "0" * 64,
        }
        with self.assertRaisesRegex(rs.ScopeError, "durable StateStore migration gateway"):
            rs.validate_state(value)

    def test_fresh_activation_cannot_forge_a_complete_schema_five_predecessor(self):
        value = assigned_state()
        set_review_budget(value, 1)
        predecessor_state = copy.deepcopy(value)
        downgrade_to_schema5_unbounded(predecessor_state)
        predecessor = {
            "versions": copy.deepcopy(predecessor_state["versions"]),
            "skill": copy.deepcopy(predecessor_state["skill"]),
            "activation": copy.deepcopy(predecessor_state["activation"]),
            "review_summary": {
                "round": predecessor_state["review"]["round"],
                "archived_supervisor_count": predecessor_state["review"]["archived_supervisor_count"],
                "archived_supervisor_digest": predecessor_state["review"]["archived_supervisor_digest"],
                "last_supervisor_created_at": predecessor_state["review"]["last_supervisor_created_at"],
            },
        }
        activation = value["activation"]
        activation["legacy_unbounded_review"] = True
        activation["legacy_review_migration"] = {
            "from_schema": 5,
            "input_digest": rs.digest_json(predecessor),
            "predecessor": predecessor,
        }
        activation["scope_digest"] = rs.compute_scope_digest(
            activation["repository"],
            activation["base_branch"],
            activation["umbrella_issues"],
            activation["allowed_operations"],
            value["skill"]["content_digest"],
            owner_actor=activation["owner_actor"],
            capability_preflight=activation["capability_preflight"],
            orchestrator_creation_receipt=activation["orchestrator_creation_receipt"],
            role_model_snapshot=activation["role_model_snapshot"],
            role_model_snapshot_digest=activation["role_model_snapshot_digest"],
            review_policy_snapshot=activation["review_policy_snapshot"],
            review_policy_snapshot_digest=activation["review_policy_snapshot_digest"],
            legacy_unbounded_review=True,
        )
        with self.assertRaisesRegex(rs.ScopeError, "durable StateStore migration gateway"):
            rs.validate_state(value)

    def test_supervisor_creation_time_orders_whole_then_fractional_second(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        value["task"]["pr_number"] = 22
        value["phase"] = "draft-pr"
        rs.begin_supervisor(
            value,
            "supervisor-whole",
            creation_receipt={
                "activation_id": value["activation"]["id"],
                "issue": 11,
                "generation": 1,
                "installed_roundlet_digest": value["skill"]["content_digest"],
                "review_contract": value["versions"]["review_contract"],
                "created": True,
                "service_receipt": role_receipt(
                    "supervisor", "supervisor-whole", created_at="2026-07-14T00:00:00Z"
                ),
            },
        )
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-whole",
            candidate_sha=SHA_B,
            result="FINDINGS",
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-whole")
        rs.set_candidate(value, SHA_B, clean=True)
        rs.begin_supervisor(
            value,
            "supervisor-fractional",
            creation_receipt={
                "activation_id": value["activation"]["id"],
                "issue": 11,
                "generation": 2,
                "installed_roundlet_digest": value["skill"]["content_digest"],
                "review_contract": value["versions"]["review_contract"],
                "created": True,
                "service_receipt": role_receipt(
                    "supervisor", "supervisor-fractional", created_at="2026-07-14T00:00:00.1Z"
                ),
            },
        )
        self.assertEqual(value["review"]["round"], 2)

    def test_stale_supervisor_candidate_is_rejected(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        rs.transition_state(value, "draft-pr")
        value["task"]["active_role"] = None
        begin_review(value, "supervisor-1")
        with self.assertRaises(rs.MailboxError):
            rs.accept_supervisor_result(
                value,
                thread_id="supervisor-1",
                candidate_sha=SHA_C,
                result="PASS",
            )

    def test_first_pass_enters_follow_up(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        rs.transition_state(value, "draft-pr")
        value["task"]["active_role"] = None
        begin_review(value, "supervisor-1")
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-1",
            candidate_sha=SHA_B,
            result="PASS",
            non_blocking_items=["consider naming"],
        )
        self.assertEqual(value["phase"], "pass-follow-up")
        self.assertEqual(value["task"]["active_role"], "worker")

    def test_final_pass_enters_premerge(self):
        value = premerge_state()
        self.assertEqual(value["phase"], "pre-merge")
        self.assertTrue(value["task"]["worker_ready_to_merge"])

    def test_premerge_gates(self):
        value = premerge_state()
        live = premerge_live(value)
        self.assertEqual(rs.verify_premerge_gates(value, live), [])
        live["checks_passed"] = False
        self.assertIn("required GitHub checks are not passing", rs.verify_premerge_gates(value, live))

    def test_premerge_rejects_durable_maintenance_and_missing_repository_id(self):
        value = premerge_state()
        live = premerge_live(value)
        live["repository_id"] = None
        value["maintenance"]["requested"] = True
        errors = rs.verify_premerge_gates(value, live)
        self.assertIn("maintenance is pending", errors)
        self.assertTrue(any("repository ID is required" in item for item in errors))

    def test_validate_rejects_stale_pass(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        value["review"]["pass_identity"] = {"candidate_sha": SHA_C}
        with self.assertRaises(rs.ValidationError):
            rs.validate_state(value)


class MaintenanceTests(unittest.TestCase):
    def test_request_records_previous_phase(self):
        value = assigned_state()
        value["task"]["active_role"] = None
        rs.request_maintenance(value, "upgrade reviewed skill")
        self.assertEqual(value["phase"], "maintenance-requested")
        self.assertEqual(value["maintenance"]["previous_phase"], "worker-running")

    def test_checkpoint_requires_no_active_child(self):
        value = assigned_state()
        rs.request_maintenance(value, "upgrade")
        with self.assertRaises(rs.TransitionError):
            rs.create_maintenance_checkpoint(
                value,
                checkpoint_id="checkpoint-001",
                schedule_id="schedule-1",
                schedule_state="paused",
            )

    def test_worker_drain_resumes_the_same_worker_turn(self):
        value = assigned_state()
        rs.request_maintenance(value, "upgrade")
        rs.drain_worker_for_maintenance(
            value,
            worker_thread_id="worker-11",
            candidate_sha=None,
            clean=True,
        )
        rs.create_maintenance_checkpoint(
            value,
            checkpoint_id="checkpoint-001",
            schedule_id="schedule-1",
            schedule_state="paused",
        )
        rs.resume_maintenance(
            value,
            checkpoint_id="checkpoint-001",
            installed_roundlet_digest=value["skill"]["content_digest"],
            current_versions=value["versions"],
            repository_identity=identity(),
            schedule_id="schedule-1",
        )
        self.assertEqual(value["phase"], "worker-running")
        self.assertEqual(value["task"]["active_role"], "worker")

    def test_final_worker_repair_maintenance_round_trip_preserves_policy_scope(self):
        value = assigned_state()
        set_review_budget(value, 1)
        rs.set_candidate(value, SHA_B, clean=True)
        value["task"].update({"pr_number": 22, "pr_url": "https://github.com/owner/project/pull/22"})
        value["task"]["pr_ready"] = True
        value["phase"] = "ready"
        begin_review(value, "supervisor-budget", final=True)
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-budget",
            candidate_sha=SHA_B,
            result="FINDINGS",
            non_blocking_items=["fix this"],
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-budget")
        rs.request_maintenance(value, "upgrade")
        rs.drain_worker_for_maintenance(
            value,
            worker_thread_id="worker-11",
            candidate_sha=SHA_C,
            clean=True,
        )
        rs.create_maintenance_checkpoint(
            value,
            checkpoint_id="checkpoint-001",
            schedule_id="schedule-1",
            schedule_state="paused",
        )
        rs.resume_maintenance(
            value,
            checkpoint_id="checkpoint-001",
            installed_roundlet_digest=value["skill"]["content_digest"],
            current_versions=value["versions"],
            repository_identity=identity(),
            schedule_id="schedule-1",
        )
        self.assertEqual(value["phase"], "final-worker-repair")
        self.assertEqual(value["task"]["active_role"], "worker")
        self.assertEqual(value["task"]["candidate_sha"], SHA_B)
        self.assertEqual(value["review"]["exhaustion"]["provisional_candidate_sha"], SHA_C)
        rs.record_worker_final_dispositions(
            value,
            worker_thread_id="worker-11",
            head_sha=SHA_C,
            clean=True,
            tests_passed=True,
            dispositions=[{"finding": "fix this", "disposition": "FIXED", "evidence": "test"}],
        )
        self.assertEqual(value["review"]["exhaustion"]["final_candidate_sha"], SHA_C)
        rs.validate_state(value)

    def test_material_maintenance_cannot_preserve_exhausted_terminal_authority(self):
        value = assigned_state()
        set_review_budget(value, 1)
        rs.set_candidate(value, SHA_B, clean=True)
        value["task"].update({"pr_number": 22, "pr_url": "https://github.com/owner/project/pull/22", "pr_ready": True})
        value["phase"] = "ready"
        begin_review(value, "supervisor-budget", final=True)
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-budget",
            candidate_sha=SHA_B,
            result="FINDINGS",
            non_blocking_items=["fix this"],
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-budget")
        rs.request_maintenance(value, "upgrade")
        rs.drain_worker_for_maintenance(value, worker_thread_id="worker-11", candidate_sha=None, clean=True)
        rs.create_maintenance_checkpoint(
            value, checkpoint_id="checkpoint-001", schedule_id="schedule-1", schedule_state="paused"
        )
        for digest, versions in (
            ("e" * 64, value["versions"]),
            (value["skill"]["content_digest"], {**value["versions"], "review_contract": "999"}),
        ):
            paused = copy.deepcopy(value)
            with self.subTest(digest=digest, versions=versions):
                with self.assertRaisesRegex(rs.GuardError, "invalidates review-budget exhaustion"):
                    rs.resume_maintenance(
                        paused,
                        checkpoint_id="checkpoint-001",
                        installed_roundlet_digest=digest,
                        current_versions=versions,
                        repository_identity=identity(),
                        schedule_id="schedule-1",
                    )
                self.assertEqual(paused["phase"], "paused-maintenance")
                self.assertIsNotNone(paused["review"]["exhaustion"])

    def test_current_state_rejects_legacy_unbound_scope_digest(self):
        value = state()
        activation = value["activation"]
        activation["scope_digest"] = rs.compute_scope_digest(
            activation["repository"],
            activation["base_branch"],
            activation["umbrella_issues"],
            activation["allowed_operations"],
            value["skill"]["content_digest"],
            owner_actor=activation["owner_actor"],
            capability_preflight=activation["capability_preflight"],
            orchestrator_creation_receipt=activation["orchestrator_creation_receipt"],
            role_model_snapshot=activation["role_model_snapshot"],
            role_model_snapshot_digest=activation["role_model_snapshot_digest"],
        )
        with self.assertRaisesRegex(rs.ScopeError, "scope digest"):
            rs.validate_state(value)

    def test_invalidated_follow_up_resumes_at_fresh_review_boundary(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        value["task"]["pr_number"] = 22
        value["phase"] = "draft-pr"
        begin_review(value, "supervisor-before-maintenance")
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-before-maintenance",
            candidate_sha=SHA_B,
            result="PASS",
        )
        rs.record_supervisor_archived(
            value,
            supervisor_thread_id="supervisor-before-maintenance",
        )
        rs.request_maintenance(value, "upgrade review contract")
        rs.drain_worker_for_maintenance(
            value,
            worker_thread_id="worker-11",
            candidate_sha=SHA_B,
            clean=True,
        )
        rs.create_maintenance_checkpoint(
            value,
            checkpoint_id="checkpoint-001",
            schedule_id="schedule-1",
            schedule_state="paused",
        )
        versions = {**value["versions"], "review_contract": "2"}
        rs.resume_maintenance(
            value,
            checkpoint_id="checkpoint-001",
            installed_roundlet_digest="e" * 64,
            current_versions=versions,
            repository_identity=identity(),
            schedule_id="schedule-1",
        )
        self.assertEqual(value["phase"], "draft-pr")
        self.assertIsNone(value["task"]["active_role"])
        self.assertIsNone(value["review"]["pass_identity"])
        begin_review(value, "supervisor-after-maintenance")

    def test_supervisor_discard_restores_pre_review_phase(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        value["task"]["pr_number"] = 22
        value["phase"] = "draft-pr"
        begin_review(value, "supervisor-maintenance")
        rs.request_maintenance(value, "upgrade")
        rs.discard_supervisor_for_maintenance(
            value,
            supervisor_thread_id="supervisor-maintenance",
        )
        rs.create_maintenance_checkpoint(
            value,
            checkpoint_id="checkpoint-001",
            schedule_id="schedule-1",
            schedule_state="paused",
        )
        rs.resume_maintenance(
            value,
            checkpoint_id="checkpoint-001",
            installed_roundlet_digest=value["skill"]["content_digest"],
            current_versions=value["versions"],
            repository_identity=identity(),
            schedule_id="schedule-1",
        )
        self.assertEqual(value["phase"], "draft-pr")
        self.assertIsNone(value["task"]["active_role"])
        self.assertEqual(value["review"]["archived_supervisor_count"], 1)

    def test_checkpoint_rejects_pending_mutation_receipt(self):
        value = assigned_state()
        value["task"]["active_role"] = None
        value["receipts"]["receipt-key-0001"] = {
            "status": "pending",
            "kind": "worker-handoff",
            "payload_digest": "a" * 64,
            "started_at": "2026-07-14T00:00:00Z",
        }
        rs.request_maintenance(value, "upgrade")
        with self.assertRaises(rs.MailboxError):
            rs.create_maintenance_checkpoint(
                value,
                checkpoint_id="checkpoint-001",
                schedule_id="schedule-1",
                schedule_state="paused",
            )

    def test_pending_supervisor_creation_cannot_cross_maintenance_or_upgrade(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        value["phase"] = "draft-pr"
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(value)
            with self.assertRaises(rs.ValidationError):
                rs.create_supervisor_after_preflight(
                    value,
                    final=False,
                    state_store=store,
                    create_task=lambda intent: {},
                )
            pending = store.load()

        with self.assertRaisesRegex(rs.MailboxError, "pending Supervisor creation"):
            rs.request_maintenance(pending, "upgrade")

        checkpoint = copy.deepcopy(pending)
        checkpoint["phase"] = "maintenance-requested"
        checkpoint["maintenance"].update(
            {"requested": True, "previous_phase": "draft-pr", "reason": "upgrade"}
        )
        with self.assertRaisesRegex(rs.MailboxError, "pending Supervisor creation"):
            rs.create_maintenance_checkpoint(
                checkpoint,
                checkpoint_id="checkpoint-001",
                schedule_id="schedule-1",
                schedule_state="paused",
            )

        paused = self._paused()
        paused["review"]["supervisor_creation_intent"] = pending["review"]["supervisor_creation_intent"]
        with self.assertRaisesRegex(rs.MailboxError, "pending Supervisor creation"):
            rs.resume_maintenance(
                paused,
                checkpoint_id="checkpoint-001",
                installed_roundlet_digest="e" * 64,
                current_versions=paused["versions"],
                repository_identity=identity(),
                schedule_id="schedule-1",
            )

        upgraded = copy.deepcopy(pending)
        upgraded["skill"]["content_digest"] = "e" * 64
        activation = upgraded["activation"]
        activation["scope_digest"] = rs.compute_scope_digest(
            activation["repository"],
            activation["base_branch"],
            activation["umbrella_issues"],
            activation["allowed_operations"],
            upgraded["skill"]["content_digest"],
            owner_actor=activation["owner_actor"],
            capability_preflight=activation["capability_preflight"],
            orchestrator_creation_receipt=activation["orchestrator_creation_receipt"],
            role_model_snapshot=activation["role_model_snapshot"],
            role_model_snapshot_digest=activation["role_model_snapshot_digest"],
            review_policy_snapshot=activation["review_policy_snapshot"],
            review_policy_snapshot_digest=activation["review_policy_snapshot_digest"],
            legacy_unbounded_review=activation["legacy_unbounded_review"],
        )
        with self.assertRaisesRegex(rs.ValidationError, "creation intent identity is stale"):
            rs.validate_state(upgraded)

    def _paused(self):
        value = assigned_state()
        value["task"]["active_role"] = None
        rs.request_maintenance(value, "upgrade")
        rs.create_maintenance_checkpoint(
            value,
            checkpoint_id="checkpoint-001",
            schedule_id="schedule-1",
            schedule_state="paused",
        )
        return value

    def test_resume_requires_explicit_checkpoint(self):
        value = self._paused()
        original = copy.deepcopy(value)
        with self.assertRaises(rs.ValidationError):
            rs.resume_maintenance(
                value,
                checkpoint_id="wrong-checkpoint",
                installed_roundlet_digest="e" * 64,
                current_versions=value["versions"],
                repository_identity=identity(),
                schedule_id="schedule-1",
            )
        self.assertEqual(value, original)

    def test_resume_preserves_original_on_failure(self):
        value = self._paused()
        original = copy.deepcopy(value)
        other = rs.RepositoryIdentity(**{**identity().__dict__, "owner_name": "other/repo"})
        with self.assertRaises(rs.ScopeError):
            rs.resume_maintenance(
                value,
                checkpoint_id="checkpoint-001",
                installed_roundlet_digest="e" * 64,
                current_versions=value["versions"],
                repository_identity=other,
                schedule_id="schedule-1",
            )
        self.assertEqual(value, original)

    def test_review_contract_change_invalidates_pass(self):
        value = self._paused()
        value["task"]["candidate_sha"] = SHA_B
        value["review"]["last_result"] = "PASS"
        value["review"]["pass_identity"] = pass_identity_for(value)
        versions = {**value["versions"], "review_contract": "2"}
        rs.resume_maintenance(
            value,
            checkpoint_id="checkpoint-001",
            installed_roundlet_digest="e" * 64,
            current_versions=versions,
            repository_identity=identity(),
            schedule_id="schedule-1",
        )
        self.assertIsNone(value["review"]["pass_identity"])
        self.assertEqual(value["phase"], "worker-running")

    def test_documentation_only_resume_preserves_pass(self):
        value = self._paused()
        value["task"]["candidate_sha"] = SHA_B
        value["review"]["last_result"] = "PASS"
        value["review"]["pass_identity"] = pass_identity_for(value)
        evidence = rs.documentation_only_resume_evidence(
            value,
            installed_roundlet_digest="e" * 64,
            current_versions=value["versions"],
            schedule_id="schedule-1",
            reviewed_source_repository="ythdelmar68/roundlet",
            reviewed_source_repository_id=999,
            reviewed_source_commit=SHA_C,
            reviewed_source_pr_url="https://github.com/ythdelmar68/roundlet/pull/99",
            changed_paths=[rs.DOCUMENTATION_ONLY_OPERATOR_GUIDE_PATH],
        )
        rs.resume_maintenance(
            value,
            checkpoint_id="checkpoint-001",
            installed_roundlet_digest="e" * 64,
            current_versions=value["versions"],
            repository_identity=identity(),
            schedule_id="schedule-1",
            documentation_evidence=evidence,
        )
        self.assertIsNotNone(value["review"]["pass_identity"])

    def test_documentation_only_resume_rejects_legacy_source_path(self):
        value = self._paused()
        with self.assertRaisesRegex(rs.ValidationError, "operator-guide documentation path"):
            rs.documentation_only_resume_evidence(
                value,
                installed_roundlet_digest="e" * 64,
                current_versions=value["versions"],
                schedule_id="schedule-1",
                reviewed_source_repository="ythdelmar68/roundlet",
                reviewed_source_repository_id=999,
                reviewed_source_commit=SHA_C,
                reviewed_source_pr_url="https://github.com/ythdelmar68/roundlet/pull/99",
                changed_paths=["references/operator-guide.md"],
            )

    def test_code_digest_change_invalidates_pass_by_default(self):
        value = self._paused()
        value["task"]["candidate_sha"] = SHA_B
        value["review"]["last_result"] = "PASS"
        value["review"]["pass_identity"] = pass_identity_for(value)
        rs.resume_maintenance(
            value,
            checkpoint_id="checkpoint-001",
            installed_roundlet_digest="e" * 64,
            current_versions=value["versions"],
            repository_identity=identity(),
            schedule_id="schedule-1",
        )
        self.assertIsNone(value["review"]["pass_identity"])

    def test_schedule_mismatch_preserves_paused_state(self):
        value = self._paused()
        original = copy.deepcopy(value)
        with self.assertRaises(rs.ValidationError):
            rs.resume_maintenance(
                value,
                checkpoint_id="checkpoint-001",
                installed_roundlet_digest="e" * 64,
                current_versions=value["versions"],
                repository_identity=identity(),
                schedule_id="another-schedule",
            )
        self.assertEqual(value, original)

    def test_detached_effective_base_can_resume_maintenance(self):
        value = self._paused()
        detached = rs.RepositoryIdentity(
            **{
                **identity().__dict__,
                "head_sha": SHA_B,
                "local_base_sha": SHA_A,
                "remote_base_sha": SHA_B,
                "current_branch": "",
                "base_branch_owner_worktree": "/owner-checkout",
            }
        )
        rs.resume_maintenance(
            value,
            checkpoint_id="checkpoint-001",
            installed_roundlet_digest=value["skill"]["content_digest"],
            current_versions=value["versions"],
            repository_identity=detached,
            schedule_id="schedule-1",
        )
        self.assertEqual(value["phase"], "worker-running")

    def test_schema_migration(self):
        old = state()
        downgrade_to_policy3(old)
        old["versions"]["schema"] = 1
        old.pop("completed_tasks")
        old.pop("retry")
        old["skill"].pop("source_repository")
        old.pop("receipt_archive")
        old.pop("mailbox_high_water")
        for key in (
            "unarchived_supervisor_thread_ids",
            "archived_supervisor_count",
            "archived_supervisor_digest",
            "last_supervisor_created_at",
        ):
            old["review"].pop(key)
        migrated = rs._migrate_state_document(old)
        self.assertEqual(migrated["versions"]["schema"], rs.SCHEMA_VERSION)
        self.assertEqual(migrated["completed_tasks"], [])
        self.assertEqual(migrated["skill"]["source_repository"], "ythdelmar68/roundlet")

    def test_schema_six_migration_preserves_non_converging_review_behavior(self):
        old = assigned_state()
        rs.set_candidate(old, SHA_B, clean=True)
        record_draft(old)
        for generation in range(1, 5):
            thread_id = f"supervisor-schema-six-{generation}"
            begin_review(old, thread_id)
            rs.accept_supervisor_result(
                old,
                thread_id=thread_id,
                candidate_sha=SHA_B,
                result="FINDINGS",
                non_blocking_items=[f"finding-{generation}"],
            )
            rs.record_supervisor_archived(old, supervisor_thread_id=thread_id)
            if generation < 4:
                rs.set_candidate(old, SHA_B, clean=True)
        downgrade_to_schema6(old)
        rs.request_maintenance(old, "schema-8 migration")
        rs.drain_worker_for_maintenance(old, worker_thread_id="worker-11", candidate_sha=SHA_B, clean=True)
        rs.create_maintenance_checkpoint(
            old, checkpoint_id="checkpoint-001", schedule_id="schedule-1", schedule_state="paused"
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            rs.atomic_write_json(store.path, old)
            migrated = store.migrate(
                activation_id="activation-0001",
                checkpoint_id="checkpoint-001",
                schedule_id="schedule-1",
                expected_installed_digest=DIGEST,
                expected_from_schema=6,
                skill_root=SKILL_ROOT,
            )
        rs.validate_state(migrated)
        rs.resume_maintenance(
            migrated,
            checkpoint_id="checkpoint-001",
            installed_roundlet_digest=DIGEST,
            current_versions=migrated["versions"],
            repository_identity=identity(),
            schedule_id="schedule-1",
        )
        rs.set_candidate(migrated, SHA_B, clean=True)
        preflight = rs.preflight_supervisor_creation(migrated)
        self.assertEqual(preflight["generation"], 5)
        self.assertEqual(preflight["guidance"]["mode"], "COMPLETE")
        begin_review(migrated, "supervisor-schema-six-5")
        rs.accept_supervisor_result(
            migrated,
            thread_id="supervisor-schema-six-5",
            candidate_sha=SHA_B,
            result="FINDINGS",
            non_blocking_items=["fifth finding"],
        )
        rs.record_supervisor_archived(migrated, supervisor_thread_id="supervisor-schema-six-5")
        denied = copy.deepcopy(migrated)
        denied["task"]["active_role"] = None
        denied["phase"] = "draft-pr"
        with self.assertRaisesRegex(rs.GuardError, "budget is exhausted"):
            rs.preflight_supervisor_creation(denied)

    def test_schema_six_durable_migration_rebinds_the_reviewed_installation(self):
        old = assigned_state()
        old["task"]["active_role"] = None
        downgrade_to_schema6(old)
        rs.request_maintenance(old, "schema-9 installation migration")
        rs.create_maintenance_checkpoint(
            old, checkpoint_id="checkpoint-001", schedule_id="schedule-1", schedule_state="paused"
        )
        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary) / "roundlet"
            shutil.copytree(SKILL_ROOT, target_root)
            operator_guide = target_root / "references" / "operator-guide.md"
            operator_guide.write_text(
                operator_guide.read_text(encoding="utf-8") + "\n\nTarget installation binding regression.\n",
                encoding="utf-8",
            )
            target_digest = rs.skill_content_digest(target_root)
            self.assertNotEqual(target_digest, DIGEST)
            store = rs.StateStore(Path(temporary) / "state")
            rs.atomic_write_json(store.path, old)
            original_bytes = store.path.read_bytes()
            with self.assertRaisesRegex(rs.MigrationError, "skill root does not match"):
                store.migrate(
                    activation_id="activation-0001",
                    checkpoint_id="checkpoint-001",
                    schedule_id="schedule-1",
                    expected_installed_digest=target_digest,
                    expected_from_schema=6,
                    skill_root=SKILL_ROOT,
                )
            self.assertEqual(store.path.read_bytes(), original_bytes)
            migrated = store.migrate(
                activation_id="activation-0001",
                checkpoint_id="checkpoint-001",
                schedule_id="schedule-1",
                expected_installed_digest=target_digest,
                expected_from_schema=6,
                skill_root=target_root,
            )
            self.assertEqual(migrated["skill"]["content_digest"], target_digest)
            self.assertEqual(migrated["maintenance"]["installed_digest"], target_digest)
            self.assertEqual(
                migrated["maintenance"]["migration_receipt"]["original_installed_digest"], DIGEST
            )
            self.assertEqual(
                migrated["maintenance"]["migration_receipt"]["migrated_installed_digest"], target_digest
            )
            with self.assertRaisesRegex(rs.ValidationError, "maintenance resume digest"):
                rs.resume_maintenance(
                    migrated,
                    checkpoint_id="checkpoint-001",
                    installed_roundlet_digest=DIGEST,
                    current_versions=migrated["versions"],
                    repository_identity=identity(),
                    schedule_id="schedule-1",
                )
            rs.resume_maintenance(
                migrated,
                checkpoint_id="checkpoint-001",
                installed_roundlet_digest=target_digest,
                current_versions=migrated["versions"],
                repository_identity=identity(),
                schedule_id="schedule-1",
            )

    def test_schema_nine_durable_migration_resets_unbound_archive_outcomes(self):
        old = assigned_state()
        old["task"]["active_role"] = None
        rs.request_maintenance(old, "schema-10 outcome migration")
        rs.create_maintenance_checkpoint(
            old, checkpoint_id="checkpoint-001", schedule_id="schedule-1", schedule_state="paused"
        )
        old["versions"].update({"schema": 9, "protocol": "3", "review_contract": "7", "policy": "8"})
        old["maintenance"]["stored_versions"] = copy.deepcopy(old["versions"])
        old["review"].pop("archived_supervisor_outcomes")
        old["review"].pop("archived_supervisor_outcome_digest")
        activation = old["activation"]
        activation["scope_digest"] = rs.compute_scope_digest(
            activation["repository"],
            activation["base_branch"],
            activation["umbrella_issues"],
            activation["allowed_operations"],
            old["skill"]["content_digest"],
            owner_actor=activation["owner_actor"],
            capability_preflight=activation["capability_preflight"],
            orchestrator_creation_receipt=activation["orchestrator_creation_receipt"],
            role_model_snapshot=activation["role_model_snapshot"],
            role_model_snapshot_digest=activation["role_model_snapshot_digest"],
            review_policy_snapshot=activation["review_policy_snapshot"],
            review_policy_snapshot_digest=activation["review_policy_snapshot_digest"],
            legacy_unbounded_review=activation["legacy_unbounded_review"],
            protocol_version="3",
            policy_version="8",
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            rs.atomic_write_json(store.path, old)
            migrated = store.migrate(
                activation_id="activation-0001",
                checkpoint_id="checkpoint-001",
                schedule_id="schedule-1",
                expected_installed_digest=DIGEST,
                expected_from_schema=9,
                skill_root=SKILL_ROOT,
            )
        self.assertEqual(migrated["versions"]["schema"], rs.SCHEMA_VERSION)
        self.assertEqual(migrated["review"]["completed_supervisor_count"], 0)
        self.assertEqual(migrated["review"]["archived_supervisor_outcomes"], [])
        rs.validate_state(migrated)

    def test_schema_six_durable_migration_rejects_stale_policy_or_scope_atomically(self):
        for tamper in ("policy", "scope"):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as temporary:
                old = assigned_state()
                old["task"]["active_role"] = None
                downgrade_to_schema6(old)
                rs.request_maintenance(old, "schema-7 migration")
                rs.create_maintenance_checkpoint(
                    old, checkpoint_id="checkpoint-001", schedule_id="schedule-1", schedule_state="paused"
                )
                if tamper == "policy":
                    old["activation"]["review_policy_snapshot"]["max_supervisor_cycles"] = 64
                else:
                    old["activation"]["scope_digest"] = "0" * 64
                store = rs.StateStore(temporary)
                rs.atomic_write_json(store.path, old)
                original_bytes = store.path.read_bytes()
                with self.assertRaisesRegex(rs.MigrationError, "schema-6 .*stale"):
                    store.migrate(
                        activation_id="activation-0001",
                        checkpoint_id="checkpoint-001",
                        schedule_id="schedule-1",
                        expected_installed_digest=DIGEST,
                        expected_from_schema=6,
                        skill_root=SKILL_ROOT,
                    )
                self.assertEqual(store.path.read_bytes(), original_bytes)

    def test_schema_six_pass_migration_clears_stale_authority_and_resumes_safely(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        begin_review(value, "supervisor-schema-six-pass")
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-schema-six-pass",
            candidate_sha=SHA_B,
            result="PASS",
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-schema-six-pass")
        downgrade_to_schema6(value)
        rs.request_maintenance(value, "schema-7 migration")
        rs.drain_worker_for_maintenance(
            value, worker_thread_id="worker-11", candidate_sha=SHA_B, clean=True
        )
        rs.create_maintenance_checkpoint(
            value, checkpoint_id="checkpoint-001", schedule_id="schedule-1", schedule_state="paused"
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            rs.atomic_write_json(store.path, value)
            migrated = store.migrate(
                activation_id="activation-0001",
                checkpoint_id="checkpoint-001",
                schedule_id="schedule-1",
                expected_installed_digest=DIGEST,
                expected_from_schema=6,
                skill_root=SKILL_ROOT,
            )
            self.assertIsNone(migrated["review"]["pass_identity"])
            self.assertIsNone(migrated["review"]["last_result"])
            rs.resume_maintenance(
                migrated,
                checkpoint_id="checkpoint-001",
                installed_roundlet_digest=DIGEST,
                current_versions=migrated["versions"],
                repository_identity=identity(),
                schedule_id="schedule-1",
            )
            self.assertEqual(migrated["phase"], "draft-pr")

    def test_schema_six_accepted_unarchived_boundary_migrates_safely(self):
        for result in ("PASS", "FINDINGS"):
            with self.subTest(result=result), tempfile.TemporaryDirectory() as temporary:
                value = assigned_state()
                rs.set_candidate(value, SHA_B, clean=True)
                record_draft(value)
                begin_review(value, f"supervisor-schema-six-unarchived-{result.lower()}")
                rs.accept_supervisor_result(
                    value,
                    thread_id=f"supervisor-schema-six-unarchived-{result.lower()}",
                    candidate_sha=SHA_B,
                    result=result,
                    non_blocking_items=[] if result == "PASS" else ["repair required"],
                )
                downgrade_to_schema6(value)
                rs.request_maintenance(value, "schema-11 unarchived result migration")
                rs.drain_worker_for_maintenance(
                    value, worker_thread_id="worker-11", candidate_sha=SHA_B, clean=True
                )
                rs.create_maintenance_checkpoint(
                    value, checkpoint_id="checkpoint-001", schedule_id="schedule-1", schedule_state="paused"
                )
                store = rs.StateStore(temporary)
                rs.atomic_write_json(store.path, value)
                migrated = store.migrate(
                    activation_id="activation-0001",
                    checkpoint_id="checkpoint-001",
                    schedule_id="schedule-1",
                    expected_installed_digest=DIGEST,
                    expected_from_schema=6,
                    skill_root=SKILL_ROOT,
                )
                self.assertEqual(migrated["review"]["unarchived_supervisor_thread_ids"], [])
                self.assertEqual(migrated["review"]["archived_supervisor_count"], 1)
                rs.validate_state(migrated)
                rs.resume_maintenance(
                    migrated,
                    checkpoint_id="checkpoint-001",
                    installed_roundlet_digest=DIGEST,
                    current_versions=migrated["versions"],
                    repository_identity=identity(),
                    schedule_id="schedule-1",
                )

    def test_schema_ten_accepted_unarchived_boundary_migrates_safely(self):
        for result in ("PASS", "FINDINGS"):
            with self.subTest(result=result), tempfile.TemporaryDirectory() as temporary:
                value = assigned_state()
                rs.set_candidate(value, SHA_B, clean=True)
                record_draft(value)
                thread_id = f"supervisor-schema-ten-unarchived-{result.lower()}"
                begin_review(value, thread_id)
                rs.accept_supervisor_result(
                    value,
                    thread_id=thread_id,
                    candidate_sha=SHA_B,
                    result=result,
                    non_blocking_items=[] if result == "PASS" else ["repair required"],
                )
                rs.request_maintenance(value, "schema-11 direct unarchived result migration")
                rs.drain_worker_for_maintenance(
                    value, worker_thread_id="worker-11", candidate_sha=SHA_B, clean=True
                )
                rs.create_maintenance_checkpoint(
                    value, checkpoint_id="checkpoint-001", schedule_id="schedule-1", schedule_state="paused"
                )
                value["versions"].update(
                    {"schema": 10, "protocol": "3", "review_contract": "8", "policy": "9"}
                )
                value["maintenance"]["stored_versions"] = copy.deepcopy(value["versions"])
                activation = value["activation"]
                activation["scope_digest"] = rs.compute_scope_digest(
                    activation["repository"], activation["base_branch"], activation["umbrella_issues"],
                    activation["allowed_operations"], value["skill"]["content_digest"],
                    owner_actor=activation["owner_actor"],
                    capability_preflight=activation["capability_preflight"],
                    orchestrator_creation_receipt=activation["orchestrator_creation_receipt"],
                    role_model_snapshot=activation["role_model_snapshot"],
                    role_model_snapshot_digest=activation["role_model_snapshot_digest"],
                    review_policy_snapshot=activation["review_policy_snapshot"],
                    review_policy_snapshot_digest=activation["review_policy_snapshot_digest"],
                    legacy_unbounded_review=activation["legacy_unbounded_review"],
                    protocol_version="3", policy_version="9",
                )
                store = rs.StateStore(temporary)
                rs.atomic_write_json(store.path, value)
                migrated = store.migrate(
                    activation_id="activation-0001",
                    checkpoint_id="checkpoint-001",
                    schedule_id="schedule-1",
                    expected_installed_digest=DIGEST,
                    expected_from_schema=10,
                    skill_root=SKILL_ROOT,
                )
                self.assertEqual(migrated["review"]["unarchived_supervisor_thread_ids"], [])
                self.assertEqual(migrated["review"]["archived_supervisor_count"], 1)
                rs.validate_state(migrated)
                rs.resume_maintenance(
                    migrated,
                    checkpoint_id="checkpoint-001",
                    installed_roundlet_digest=DIGEST,
                    current_versions=migrated["versions"],
                    repository_identity=identity(),
                    schedule_id="schedule-1",
                )

    def test_schema_five_migration_preserves_round_64_and_higher_as_unbounded(self):
        for review_round in (64, 65, 200):
            with self.subTest(review_round=review_round), tempfile.TemporaryDirectory() as temporary:
                old = assigned_state()
                rs.set_candidate(old, SHA_B, clean=True)
                old["task"]["pr_number"] = 22
                old["phase"] = "draft-pr"
                downgrade_to_schema5_unbounded(old)
                old["review"].update(
                    {
                        "round": review_round,
                        "archived_supervisor_count": review_round,
                        "last_supervisor_created_at": "2026-07-14T00:00:00.000001Z",
                    }
                )
                rs.request_maintenance(old, "schema-6 migration")
                rs.create_maintenance_checkpoint(
                    old,
                    checkpoint_id="checkpoint-001",
                    schedule_id="schedule-1",
                    schedule_state="paused",
                )
                store = rs.StateStore(temporary)
                rs.atomic_write_json(store.path, old)
                migrated = store.migrate(
                    activation_id="activation-0001",
                    checkpoint_id="checkpoint-001",
                    schedule_id="schedule-1",
                    expected_installed_digest=DIGEST,
                    expected_from_schema=5,
                    skill_root=SKILL_ROOT,
                )
                self.assertTrue(migrated["activation"]["legacy_unbounded_review"])
                rs.validate_state(migrated)
                rs.resume_maintenance(
                    migrated,
                    checkpoint_id="checkpoint-001",
                    installed_roundlet_digest=DIGEST,
                    current_versions=migrated["versions"],
                    repository_identity=identity(),
                    schedule_id="schedule-1",
                )
                self.assertEqual(
                    rs.preflight_supervisor_creation(migrated)["generation"],
                    review_round + 1,
                )

    def test_migrated_legacy_state_cannot_be_replayed_without_external_authority(self):
        old = assigned_state()
        old["task"]["active_role"] = None
        downgrade_to_schema5_unbounded(old)
        rs.request_maintenance(old, "schema-6 migration")
        rs.create_maintenance_checkpoint(
            old,
            checkpoint_id="checkpoint-001",
            schedule_id="schedule-1",
            schedule_state="paused",
        )
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as replay:
            source_store = rs.StateStore(source)
            rs.atomic_write_json(source_store.path, old)
            source_store.migrate(
                activation_id="activation-0001",
                checkpoint_id="checkpoint-001",
                schedule_id="schedule-1",
                expected_installed_digest=DIGEST,
                expected_from_schema=5,
                skill_root=SKILL_ROOT,
            )
            replay_store = rs.StateStore(replay)
            replay_store.path.write_bytes(source_store.path.read_bytes())
            with self.assertRaisesRegex(rs.ScopeError, "authority receipt"):
                replay_store.load()

    def test_schema_migration_rejects_unverifiable_legacy_review_history(self):
        old = state()
        old["versions"]["schema"] = 1
        old["review"]["round"] = 1
        old["review"]["supervisor_thread_ids"] = ["legacy-supervisor"]
        for key in (
            "unarchived_supervisor_thread_ids",
            "archived_supervisor_count",
            "archived_supervisor_digest",
            "last_supervisor_created_at",
        ):
            old["review"].pop(key)
        with self.assertRaises(rs.MigrationError):
            rs._migrate_state_document(old)

    def test_schema_three_migration_rejects_missing_connector_origin_proof(self):
        old = state()
        old["versions"].update(
            {"schema": 3, "protocol": "2", "review_contract": "2", "policy": "2"}
        )
        old["activation"]["capability_preflight"].pop(
            "connector_read_adapter_receipts"
        )
        with self.assertRaisesRegex(rs.MigrationError, "connector adapter receipt"):
            rs._migrate_state_document(old)

    def test_paused_schema_migration_can_resume_and_failure_is_atomic(self):
        with tempfile.TemporaryDirectory() as temporary:
            paused = self._paused()
            downgrade_to_policy3(paused)
            paused["versions"]["schema"] = 1
            paused["maintenance"]["stored_versions"] = copy.deepcopy(paused["versions"])
            paused["maintenance"].pop("migrated_from_versions", None)
            paused["maintenance"].pop("migration_receipt", None)
            store = rs.StateStore(temporary)
            rs.atomic_write_json(store.path, paused)
            migrated = store.migrate(
                activation_id="activation-0001",
                checkpoint_id="checkpoint-001",
                schedule_id="schedule-1",
                expected_installed_digest=DIGEST,
                expected_from_schema=1,
                target_version=rs.SCHEMA_VERSION,
                skill_root=SKILL_ROOT,
            )
            self.assertEqual(
                migrated["maintenance"]["stored_versions"]["schema"], rs.SCHEMA_VERSION
            )
            self.assertEqual(migrated["maintenance"]["migration_receipt"]["from_schema"], 1)
            rs.resume_maintenance(
                migrated,
                checkpoint_id="checkpoint-001",
                installed_roundlet_digest=migrated["skill"]["content_digest"],
                current_versions=migrated["versions"],
                repository_identity=identity(),
                schedule_id="schedule-1",
            )
            self.assertEqual(migrated["phase"], "worker-running")

        with tempfile.TemporaryDirectory() as temporary:
            paused = self._paused()
            downgrade_to_policy3(paused)
            paused["versions"]["schema"] = 1
            paused["maintenance"]["stored_versions"]["schema"] = 99
            store = rs.StateStore(temporary)
            rs.atomic_write_json(store.path, paused)
            before = store.path.read_bytes()
            with self.assertRaises(rs.MigrationError):
                store.migrate(
                    activation_id="activation-0001",
                    checkpoint_id="checkpoint-001",
                    schedule_id="schedule-1",
                    expected_installed_digest=DIGEST,
                    expected_from_schema=1,
                    target_version=rs.SCHEMA_VERSION,
                    skill_root=SKILL_ROOT,
                )
            self.assertEqual(store.path.read_bytes(), before)

    def test_durable_migration_rejects_every_active_phase_without_writing(self):
        active_states = [state(), assigned_state()]
        selecting = state()
        set_selection(selecting)
        active_states.append(selecting)
        for value in active_states:
            with self.subTest(phase=value["phase"]), tempfile.TemporaryDirectory() as temporary:
                value["versions"]["schema"] = 1
                store = rs.StateStore(temporary)
                rs.atomic_write_json(store.path, value)
                before = store.path.read_bytes()
                with self.assertRaises(rs.MigrationError):
                    store.migrate(
                        activation_id="activation-0001",
                        checkpoint_id="checkpoint-001",
                        schedule_id="schedule-1",
                        expected_installed_digest=DIGEST,
                        expected_from_schema=1,
                        target_version=rs.SCHEMA_VERSION,
                        skill_root=SKILL_ROOT,
                    )
                self.assertEqual(store.path.read_bytes(), before)

    def test_durable_migration_requires_exact_paused_schedule_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = self._paused()
            value["versions"]["schema"] = 1
            value["maintenance"]["stored_versions"]["schema"] = 1
            value["maintenance"]["schedule_state"] = "active"
            store = rs.StateStore(temporary)
            rs.atomic_write_json(store.path, value)
            before = store.path.read_bytes()
            with self.assertRaises(rs.MigrationError):
                store.migrate(
                    activation_id="activation-0001",
                    checkpoint_id="checkpoint-001",
                    schedule_id="schedule-1",
                    expected_installed_digest=DIGEST,
                    expected_from_schema=1,
                    target_version=rs.SCHEMA_VERSION,
                    skill_root=SKILL_ROOT,
                )
            self.assertEqual(store.path.read_bytes(), before)

    def test_durable_migration_requires_root_and_matching_digest_atomically(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = self._paused()
            downgrade_to_policy3(value)
            value["maintenance"]["stored_versions"] = copy.deepcopy(value["versions"])
            store = rs.StateStore(temporary)
            rs.atomic_write_json(store.path, value)
            before = store.path.read_bytes()
            with self.assertRaises(TypeError):
                store.migrate(
                    activation_id="activation-0001", checkpoint_id="checkpoint-001", schedule_id="schedule-1",
                    expected_installed_digest=DIGEST, expected_from_schema=4, target_version=rs.SCHEMA_VERSION,
                )
            with self.assertRaises(rs.MigrationError):
                store.migrate(
                    activation_id="activation-0001", checkpoint_id="checkpoint-001", schedule_id="schedule-1",
                    expected_installed_digest="d" * 64, expected_from_schema=4, target_version=rs.SCHEMA_VERSION,
                    skill_root=SKILL_ROOT,
                )
            self.assertEqual(store.path.read_bytes(), before)

    def test_durable_migration_rejects_config_change_during_digest_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "roundlet"
            shutil.copytree(SKILL_ROOT, root)
            digest = rs.skill_content_digest(root)
            value = self._paused()
            value["skill"]["content_digest"] = digest
            value["maintenance"]["installed_digest"] = digest
            downgrade_to_policy3(value)
            value["maintenance"]["stored_versions"] = copy.deepcopy(value["versions"])
            store = rs.StateStore(temporary)
            rs.atomic_write_json(store.path, value)
            before = store.path.read_bytes()
            original_loader = rs.load_role_model_config

            def mutate_after_load(skill_root):
                loaded = original_loader(skill_root)
                path = Path(skill_root) / "assets" / "roundlet-config.json"
                config = json.loads(path.read_text())
                config["defaults"]["roles"]["worker"]["reasoning_effort"] = "low"
                path.write_text(json.dumps(config))
                return loaded

            with mock.patch.object(rs, "load_role_model_config", side_effect=mutate_after_load):
                with self.assertRaisesRegex(rs.MigrationError, "skill root"):
                    store.migrate(
                        activation_id="activation-0001", checkpoint_id="checkpoint-001", schedule_id="schedule-1",
                        expected_installed_digest=digest, expected_from_schema=4, target_version=rs.SCHEMA_VERSION,
                        skill_root=root,
                    )
            self.assertEqual(store.path.read_bytes(), before)

    def test_policy3_migration_rejects_corrupt_or_expanded_legacy_scope_atomically(self):
        for corrupt in ("digest", "operation"):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as temporary:
                value = self._paused()
                downgrade_to_policy3(value)
                if corrupt == "digest":
                    value["activation"]["scope_digest"] = "0" * 64
                else:
                    value["activation"]["allowed_operations"]["create_draft_prs"] = False
                    refresh_policy3_scope(value)
                    value["activation"]["allowed_operations"]["create_draft_prs"] = True
                value["maintenance"]["stored_versions"] = copy.deepcopy(value["versions"])
                store = rs.StateStore(temporary)
                rs.atomic_write_json(store.path, value)
                before = store.path.read_bytes()
                with self.assertRaisesRegex(rs.MigrationError, "legacy scope"):
                    store.migrate(
                        activation_id="activation-0001", checkpoint_id="checkpoint-001", schedule_id="schedule-1",
                        expected_installed_digest=DIGEST, expected_from_schema=4, target_version=rs.SCHEMA_VERSION,
                        skill_root=SKILL_ROOT,
                    )
                self.assertEqual(store.path.read_bytes(), before)

    def test_policy3_scope_digest_matches_immutable_base_vector(self):
        value = assigned_state()
        value["skill"]["content_digest"] = "a" * 64
        downgrade_to_policy3(value)
        self.assertEqual(
            value["activation"]["scope_digest"],
            "1abf4ccb59ac1e523fdc625e2d926f2271aa3a5a1dd5d7dc94d3820a9f79b4e7",
        )

    def test_policy3_durable_migration_rebinds_new_digest_and_can_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "roundlet"
            shutil.copytree(SKILL_ROOT, root)
            (root / "references" / "operator-guide.md").write_text(
                (root / "references" / "operator-guide.md").read_text() + "\nUpdated review evidence.\n"
            )
            new_digest = rs.skill_content_digest(root)
            self.assertNotEqual(new_digest, DIGEST)

            value = self._paused()
            value["skill"]["content_digest"] = "a" * 64
            value["maintenance"]["installed_digest"] = "a" * 64
            downgrade_to_policy3(value)
            value["maintenance"]["stored_versions"] = copy.deepcopy(value["versions"])
            store = rs.StateStore(temporary)
            rs.atomic_write_json(store.path, value)

            migrated = store.migrate(
                activation_id="activation-0001", checkpoint_id="checkpoint-001", schedule_id="schedule-1",
                expected_installed_digest=new_digest, expected_from_schema=4, target_version=rs.SCHEMA_VERSION,
                skill_root=root,
            )
            self.assertEqual(migrated["skill"]["content_digest"], new_digest)
            self.assertEqual(migrated["maintenance"]["installed_digest"], new_digest)
            self.assertEqual(
                migrated["maintenance"]["migration_receipt"]["original_installed_digest"], "a" * 64
            )
            self.assertEqual(
                migrated["maintenance"]["migration_receipt"]["migrated_installed_digest"], new_digest
            )
            rs.resume_maintenance(
                migrated,
                checkpoint_id="checkpoint-001",
                installed_roundlet_digest=new_digest,
                current_versions=migrated["versions"],
                repository_identity=identity(),
                schedule_id="schedule-1",
            )
            self.assertEqual(migrated["phase"], "worker-running")

    def test_policy3_migration_rejects_unpinned_legacy_profile_without_or_with_mixed_receipts(self):
        for with_task in (False, True):
            with self.subTest(with_task=with_task), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "roundlet"
                shutil.copytree(SKILL_ROOT, root)
                path = root / "assets" / "roundlet-config.json"
                config = json.loads(path.read_text())
                config["legacy_profiles"]["policy_3"]["worker"]["reasoning_effort"] = "low"
                path.write_text(json.dumps(config))
                new_digest = rs.skill_content_digest(root)

                if with_task:
                    value = self._paused()
                    value["review"]["supervisor_creation_receipts"] = [
                        policy3_role_receipt("supervisor", "supervisor-1")
                    ]
                else:
                    value = state()
                    rs.request_maintenance(value, "upgrade")
                    rs.create_maintenance_checkpoint(
                        value,
                        checkpoint_id="checkpoint-001",
                        schedule_id="schedule-1",
                        schedule_state="paused",
                    )
                    self.assertIsNone(value["task"])
                downgrade_to_policy3(value)
                value["maintenance"]["stored_versions"] = copy.deepcopy(value["versions"])
                store = rs.StateStore(temporary)
                rs.atomic_write_json(store.path, value)
                before = store.path.read_bytes()

                with self.assertRaisesRegex(rs.MigrationError, "unrecognized policy-3 legacy profile"):
                    store.migrate(
                        activation_id="activation-0001", checkpoint_id="checkpoint-001", schedule_id="schedule-1",
                        expected_installed_digest=new_digest, expected_from_schema=4, target_version=rs.SCHEMA_VERSION,
                        skill_root=root,
                    )
                self.assertEqual(store.path.read_bytes(), before)

    def test_unknown_migration_fails(self):
        value = state()
        value["versions"]["schema"] = 99
        with self.assertRaises(rs.MigrationError):
            rs._migrate_state_document(value)


class DiscoveryTests(unittest.TestCase):
    def test_same_repository_references_only(self):
        text = "#11 owner/project#12 https://github.com/owner/project/issues/13 other/repo#99"
        self.assertEqual(
            rs.extract_same_repository_issue_numbers(text, "owner/project"),
            [11, 12, 13],
        )

    def test_membership_sources(self):
        membership = rs.discover_membership(
            umbrella_issue=10,
            formal_subissues=[{"repository": "owner/project", "issue": 11}],
            umbrella_body="## Required implementation order\n1. #12\n2. other/repo#99",
            comments=[
                rs.Comment("owner", 7, "Please include #13 as a sub-issue"),
                rs.Comment("stranger", 8, "Please include #14 as a sub-issue"),
            ],
            owner_actor=OWNER_ACTOR,
            current_repository="owner/project",
        )
        self.assertEqual(set(membership), {11, 12, 13})
        self.assertEqual(membership[11], ["formal-sub-issue"])
        self.assertNotIn(14, membership)

    def test_owner_comment_uses_actor_id_not_caller_selected_login(self):
        membership = rs.discover_membership(
            umbrella_issue=10,
            formal_subissues=[],
            umbrella_body="",
            comments=[rs.Comment("owner", 999, "Please include #13 as a sub-issue")],
            owner_actor=OWNER_ACTOR,
            current_repository="owner/project",
        )
        self.assertEqual(membership, {})

        renamed = rs.discover_membership(
            umbrella_issue=10,
            formal_subissues=[],
            umbrella_body="",
            comments=[rs.Comment("renamed-owner", 7, "Please include #13 as a sub-issue")],
            owner_actor=OWNER_ACTOR,
            current_repository="owner/project",
        )
        self.assertEqual(renamed, {13: ["owner-comment"]})

    def test_organization_repository_requires_verified_human_actor(self):
        membership = rs.discover_membership(
            umbrella_issue=10,
            formal_subissues=[],
            umbrella_body="",
            comments=[rs.Comment("human-owner", 7, "Please include #13 as a sub-issue")],
            owner_actor=OWNER_ACTOR,
            current_repository="organization/project",
        )
        self.assertEqual(membership, {13: ["owner-comment"]})

    def test_body_reference_outside_trusted_sections_does_not_expand(self):
        membership = rs.discover_membership(
            umbrella_issue=10,
            formal_subissues=[],
            umbrella_body="## Notes\nMaybe see #99",
            comments=[],
            owner_actor=OWNER_ACTOR,
            current_repository="owner/project",
        )
        self.assertEqual(membership, {})

    def test_explicit_top_level_list_is_membership_but_prose_is_not(self):
        membership = rs.discover_membership(
            umbrella_issue=10,
            formal_subissues=[],
            umbrella_body="- [ ] #11\n- Maybe see #99\n1. owner/project#12",
            comments=[],
            owner_actor=OWNER_ACTOR,
            current_repository="owner/project",
        )
        self.assertEqual(set(membership), {11, 12})

    def test_negative_or_historical_headings_do_not_expand_scope(self):
        membership = rs.discover_membership(
            umbrella_issue=10,
            formal_subissues=[],
            umbrella_body=(
                "## Sub-issues not in scope\n- #98\n"
                "## Historical implementation order (obsolete)\n- #99"
            ),
            comments=[],
            owner_actor=OWNER_ACTOR,
            current_repository="owner/project",
        )
        self.assertEqual(membership, {})

    def test_negative_line_inside_trusted_heading_is_ignored(self):
        body = "## Required implementation order\nDo not include #99\n1. #12"
        membership = rs.discover_membership(
            umbrella_issue=10,
            formal_subissues=[],
            umbrella_body=body,
            comments=[],
            owner_actor=OWNER_ACTOR,
            current_repository="owner/project",
        )
        self.assertEqual(set(membership), {12})
        self.assertEqual(rs.parse_required_order(body, "owner/project"), [12])

    def test_owner_comment_negation_or_incidental_reference_does_not_expand(self):
        membership = rs.discover_membership(
            umbrella_issue=10,
            formal_subissues=[],
            umbrella_body="",
            comments=[
                rs.Comment("owner", 7, "Do not include #98"),
                rs.Comment("owner", 7, "For context, see #99"),
            ],
            owner_actor=OWNER_ACTOR,
            current_repository="owner/project",
        )
        self.assertEqual(membership, {})

    def test_formal_membership_requires_same_repository_identity(self):
        with self.assertRaises(rs.ScopeError):
            rs.discover_membership(
                umbrella_issue=10,
                formal_subissues=[{"repository": "other/repo", "issue": 11}],
                umbrella_body="",
                comments=[],
                owner_actor=OWNER_ACTOR,
                current_repository="owner/project",
            )

    def test_generic_url_fragment_cannot_expand_membership(self):
        text = "https://example.com/search?q=#99"
        self.assertEqual(rs.extract_same_repository_issue_numbers(text, "owner/project"), [])
        external_anchor = "https://github.com/other/repo/issues/99#12"
        self.assertEqual(rs.extract_same_repository_issue_numbers(external_anchor, "owner/project"), [])
        same_anchor = "https://github.com/owner/project/issues/99#12"
        self.assertEqual(rs.extract_same_repository_issue_numbers(same_anchor, "owner/project"), [99])
        self.assertEqual(
            rs.extract_same_repository_issue_numbers("owner/other#99#12", "owner/project"),
            [],
        )

    def test_required_order(self):
        markdown = "## Required implementation order\n1. #12\n2. #11\n## Notes\n#99"
        self.assertEqual(rs.parse_required_order(markdown, "owner/project"), [12, 11])

    def test_required_order_preserves_same_line_and_normalized_reference_order(self):
        markdown = (
            "## Required implementation order\n"
            "#12 then owner/project#11 then "
            "https://github.com/other/repo/issues/98 then "
            "https://github.com/owner/project/issues/10#section"
        )
        self.assertEqual(rs.parse_required_order(markdown, "owner/project"), [12, 11, 10])

    def test_dependency_statement(self):
        edges = rs.parse_dependency_edges("#12 depends on #11", "owner/project")
        self.assertEqual(edges, {(12, 11)})

    def test_dependency_statement_collects_all_local_prerequisites(self):
        edges = rs.parse_dependency_edges(
            "#12 depends on #11, owner/project#10 and other/repo#99",
            "owner/project",
        )
        self.assertEqual(edges, {(12, 11), (12, 10)})

    def test_dependency_parser_ignores_generic_url_fragments(self):
        text = "https://example.com/?x=#12 depends on #11"
        self.assertEqual(rs.parse_dependency_edges(text, "owner/project"), set())
        both_urls = "https://example.com/#12 depends on https://example.net/#11"
        self.assertEqual(rs.parse_dependency_edges(both_urls, "owner/project"), set())

    def test_dependency_matrix(self):
        text = "## Dependency matrix\n| Task | Requires |\n| #12 | #11 |"
        self.assertIn((12, 11), rs.parse_dependency_edges(text, "owner/project"))

    def test_external_dependency_not_parsed_as_local(self):
        text = "#12 depends on other/repo#99"
        self.assertEqual(rs.parse_dependency_edges(text, "owner/project"), set())


def snap(
    issue,
    *,
    umbrella=10,
    completed=False,
    deps=(),
    order=None,
    ambiguous=False,
    external=(),
    priority=0,
    unlocks=0,
    risk=0,
    repository="owner/project",
    open=True,
):
    issue_evidence = issue_connector_evidence(issue, open=open, completed=completed)
    return rs.IssueSnapshot(
        issue=issue,
        umbrella=umbrella,
        repository=repository,
        open=open,
        completion_verified=completed,
        dependencies=tuple(deps),
        external_blockers=tuple(external),
        membership_evidence=(
            formal_membership_evidence(issue, umbrella, issue_evidence["revision"]),
        ),
        issue_evidence=issue_evidence,
        completion_evidence=(
            merged_completion_evidence(issue, issue_evidence["revision"])
            if completed
            else None
        ),
        required_order_index=order,
        ambiguous_active_implementation=ambiguous,
        owner_priority=priority,
        unlocks=unlocks,
        overlap_risk=risk,
    )


class SelectionTests(unittest.TestCase):
    def receipt(self, snapshots, umbrellas=None):
        value = state(umbrellas=umbrellas)
        discovered = {umbrella: [] for umbrella in value["activation"]["umbrella_issues"]}
        for snapshot in snapshots:
            if snapshot.umbrella in discovered:
                discovered[snapshot.umbrella].append(snapshot.issue)
        return select_from_connector(
            value,
            snapshots,
            refresh_manifest(value, discovered, snapshots),
        )

    def test_selects_only_candidate(self):
        receipt = self.receipt([snap(11)])
        self.assertEqual(receipt["selected_issue"], 11)
        self.assertEqual(receipt["status"], "selected")

    def test_hard_dependency_waits(self):
        receipt = self.receipt([snap(11), snap(12, deps=(11,))])
        self.assertEqual(receipt["selected_issue"], 11)
        self.assertIn("waiting for dependencies #11", receipt["excluded_candidates"]["12"])

    def test_completed_dependency_unlocks(self):
        receipt = self.receipt([snap(11, completed=True, open=False), snap(12, deps=(11,))])
        self.assertEqual(receipt["selected_issue"], 12)

    def test_closed_without_verification_does_not_count_complete(self):
        receipt = self.receipt([snap(11, open=False), snap(12, deps=(11,))])
        self.assertIsNone(receipt["selected_issue"])
        self.assertEqual(receipt["status"], "waiting-dependency")

    def test_required_order_precedes_issue_number(self):
        receipt = self.receipt([snap(11, order=1), snap(12, order=0)])
        self.assertEqual(receipt["selected_issue"], 12)

    def test_required_order_does_not_skip_blocked_head(self):
        receipt = self.receipt([snap(11, order=0, external=("external",)), snap(12, order=1)])
        self.assertIsNone(receipt["selected_issue"])

    def test_order_dependency_contradiction_blocks(self):
        with self.assertRaises(rs.SelectionBlocked):
            self.receipt([snap(11, order=0, deps=(12,)), snap(12, order=1)])

    def test_cycle_blocks(self):
        with self.assertRaises(rs.SelectionBlocked):
            self.receipt([snap(11, deps=(12,)), snap(12, deps=(11,))])

    def test_ambiguous_active_pr_permanently_blocks_scope(self):
        with self.assertRaisesRegex(rs.SelectionBlocked, "ambiguous active implementation"):
            self.receipt([snap(11, ambiguous=True)])
        value = state()
        rs.transition_state(value, "blocked")
        self.assertIn(value["phase"], rs.TERMINAL_PHASES)

    def test_cross_repository_snapshot_rejected(self):
        with self.assertRaises(rs.ScopeError):
            self.receipt([snap(11, repository="other/repo")])

    def test_unauthorized_umbrella_rejected(self):
        with self.assertRaises(rs.ScopeError):
            self.receipt([snap(11, umbrella=99)])

    def test_cross_dependency_priority(self):
        receipt = self.receipt(
            [snap(11, umbrella=10), snap(21, umbrella=20), snap(22, umbrella=20, deps=(11,))],
            umbrellas=[10, 20],
        )
        self.assertEqual(receipt["selected_issue"], 11)

    def test_unlocks_then_overlap_then_owner_priority(self):
        receipt = self.receipt(
            [
                snap(11, umbrella=10, unlocks=1, risk=2, priority=1),
                snap(21, umbrella=20, unlocks=2, risk=9, priority=0),
            ],
            umbrellas=[10, 20],
        )
        self.assertEqual(receipt["selected_issue"], 21)

    def test_umbrella_order_tie_break(self):
        receipt = self.receipt(
            [snap(11, umbrella=10), snap(21, umbrella=20)],
            umbrellas=[20, 10],
        )
        self.assertEqual(receipt["selected_issue"], 21)

    def test_scope_complete(self):
        receipt = self.receipt([snap(11, completed=True, open=False)])
        self.assertEqual(receipt["status"], "complete")

    def test_forged_membership_source_cannot_authorize_arbitrary_issue(self):
        value = state()
        issue_evidence = issue_connector_evidence(999)
        snapshot = rs.IssueSnapshot(
            issue=999,
            umbrella=10,
            repository="owner/project",
            membership_evidence=(
                {"source_type": "forged-caller-claim", "verified_by_connector": True},
            ),
            issue_evidence=issue_evidence,
        )
        with self.assertRaisesRegex(rs.ValidationError, "supported connector receipt"):
            select_from_connector(
                value,
                [snapshot],
                refresh_manifest(value, {10: [999]}),
            )

    def test_schema_valid_caller_mappings_lack_connector_origin_capability(self):
        for snapshot in (snap(999), snap(11, completed=True, open=False)):
            value = state()
            fabricated = {
                "refresh_manifest": refresh_manifest(
                    value, {10: [snapshot.issue]}, [snapshot]
                ),
                "snapshot_evidence": [raw_snapshot_document(snapshot)],
                "verified_by_connector": True,
            }
            with self.assertRaisesRegex(rs.ScopeError, "opaque connector refresh"):
                rs.select_next_task(value, fabricated)
            with self.assertRaisesRegex(rs.ScopeError, "service-issued GitHub adapter"):
                rs.execute_connector_refresh(
                    value,
                    refresh_timestamp=REFRESH_TIME,
                    adapter=lambda request: fabricated,
                )

    def test_connector_adapter_binding_rejects_unverified_service_metadata(self):
        value = state()
        core = {
            "verified_by_service": False,
            "connector": "github",
            "operation": rs.CONNECTOR_REFRESH_OPERATION,
            "adapter_id": "github-adapter:forged",
            "activation_id": value["activation"]["id"],
            "repository": "owner/project",
            "repository_id": 123,
            "orchestrator_thread_id": value["activation"]["orchestrator_thread_id"],
            "project_identity": value["activation"]["orchestrator_creation_receipt"][
                "project_identity"
            ],
            "created_at": "2026-07-14T00:00:00Z",
        }
        with self.assertRaisesRegex(rs.ScopeError, "did not verify"):
            rs.bind_github_connector_read_adapter(
                value,
                service_receipt={**core, "receipt_digest": rs.digest_json(core)},
                read_connector=lambda request: {},
            )

    def test_manifest_digest_and_revisions_are_recomputed(self):
        value = state()
        snapshot = snap(11)
        manifest = refresh_manifest(value, {10: [11]}, [snapshot])
        manifest["umbrellas"][0]["membership_evidence_digest"] = "f" * 64
        with self.assertRaisesRegex(rs.ScopeError, "not derived from canonical connector evidence"):
            select_from_connector(
                value,
                [snapshot],
                manifest,
            )

        value = state()
        snapshot = snap(11)
        manifest = refresh_manifest(value, {10: [11]}, [snapshot])
        manifest["umbrellas"][0]["umbrella_revision"] = "f" * 64
        with self.assertRaisesRegex(rs.ScopeError, "umbrella revision was not derived"):
            select_from_connector(
                value,
                [snapshot],
                manifest,
            )

        value = state()
        issue_evidence = issue_connector_evidence(11)
        issue_evidence["revision"] = "f" * 64
        snapshot = rs.IssueSnapshot(
            issue=11,
            umbrella=10,
            repository="owner/project",
            membership_evidence=(
                formal_membership_evidence(11, 10, issue_evidence["revision"]),
            ),
            issue_evidence=issue_evidence,
        )
        with self.assertRaisesRegex(rs.ScopeError, "issue evidence revision was not derived"):
            select_from_connector(
                value,
                [snapshot],
                refresh_manifest(value, {10: [11]}, [snapshot]),
            )

    def test_snapshot_boolean_fields_are_strict(self):
        evidence = issue_connector_evidence(11)
        membership = formal_membership_evidence(11, 10, evidence["revision"])
        with self.assertRaisesRegex(rs.ValidationError, "must be booleans"):
            rs.IssueSnapshot(
                issue=11,
                umbrella=10,
                repository="owner/project",
                open="false",
                membership_evidence=(membership,),
                issue_evidence=evidence,
            )
        with self.assertRaisesRegex(rs.ValidationError, "must be booleans"):
            rs.IssueSnapshot(
                issue=11,
                umbrella=10,
                repository="owner/project",
                completion_verified="caller-says-complete",
                membership_evidence=(membership,),
                issue_evidence=evidence,
                completion_evidence={},
            )

    def test_completion_requires_bound_live_closed_issue_and_merged_pr(self):
        value = state()
        issue_evidence = issue_connector_evidence(11, open=False, completed=True)
        completion = merged_completion_evidence(11, issue_evidence["revision"])
        completion["merged_pr"]["merged"] = False
        snapshot = rs.IssueSnapshot(
            issue=11,
            umbrella=10,
            repository="owner/project",
            open=False,
            completion_verified=True,
            membership_evidence=(
                formal_membership_evidence(11, 10, issue_evidence["revision"]),
            ),
            issue_evidence=issue_evidence,
            completion_evidence=completion,
        )
        with self.assertRaisesRegex(rs.ScopeError, "closed and merged PR"):
            select_from_connector(
                value,
                [snapshot],
                refresh_manifest(value, {10: [11]}, [snapshot]),
            )

    def test_hand_built_selection_cannot_dispatch_arbitrary_issue(self):
        value = state()
        value["phase"] = "selecting-task"
        value["selection"] = {
            "status": "selected",
            "activation_id": value["activation"]["id"],
            "selected_umbrella": 10,
            "selected_issue": 999,
            "base_sha": SHA_A,
        }
        with self.assertRaises(rs.ValidationError):
            rs.validate_state(value)
        with self.assertRaises(rs.ValidationError):
            rs.assign_task(
                value,
                umbrella_issue=10,
                issue=999,
                branch="codex/issue-999",
                worktree="/tmp/999",
                worker_thread_id="worker-999",
                worker_creation_receipt=role_receipt("worker", "worker-999"),
                base_sha=SHA_A,
            )

    def test_refresh_requires_every_umbrella_and_rejects_partial_or_empty_manifest(self):
        value = state(umbrellas=[10, 20])
        incomplete = refresh_manifest(value, {10: [11], 20: []})
        incomplete["umbrellas"] = incomplete["umbrellas"][:1]
        with self.assertRaises(rs.ScopeError):
            select_from_connector(
                value,
                [snap(11, umbrella=10)],
                incomplete,
            )
        empty = refresh_manifest(value, {10: [11], 20: []})
        empty["umbrellas"] = []
        with self.assertRaises(rs.ScopeError):
            select_from_connector(
                value,
                [snap(11, umbrella=10)],
                empty,
            )

    def test_umbrella_as_task_and_completion_without_receipt_are_blocked(self):
        value = state()
        with self.assertRaises(rs.ScopeError):
            select_from_connector(
                value,
                [snap(10, umbrella=10)],
                refresh_manifest(value, {10: [10]}),
            )
        value = state()
        rs.transition_state(value, "selecting-task")
        with self.assertRaises(rs.TransitionError):
            rs.transition_state(value, "scope-complete")


class PersistenceAndMailboxTests(unittest.TestCase):
    def test_atomic_state_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(state())
            self.assertEqual(store.load()["activation"]["id"], "activation-0001")

    def test_schema_one_archive_authority_loads_without_pending_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(state())
            authority = rs.read_json(store.supervisor_archive_authority_path)
            authority.pop("pending_completion")
            authority["schema_version"] = 1
            core = {key: value for key, value in authority.items() if key != "authority_digest"}
            authority["authority_digest"] = rs.digest_json(core)
            rs.atomic_write_json(store.supervisor_archive_authority_path, authority)
            self.assertEqual(store.load()["activation"]["id"], "activation-0001")

    def test_archive_authority_partial_write_recovers_to_consistent_prior_state(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(value)
            durable = store.load()
            begin_review(durable, "supervisor-archive-transaction")
            rs.accept_supervisor_result(
                durable,
                thread_id="supervisor-archive-transaction",
                candidate_sha=SHA_B,
                result="FINDINGS",
                non_blocking_items=["repair required"],
            )
            store.save(durable)
            durable = store.load()
            rs.record_supervisor_archived(
                durable, supervisor_thread_id="supervisor-archive-transaction"
            )
            original_write = rs.atomic_write_json

            def fail_state_replace(path, value, **kwargs):
                if Path(path) == store.path:
                    raise OSError("injected state replacement interruption")
                return original_write(path, value, **kwargs)

            with mock.patch.object(rs, "atomic_write_json", side_effect=fail_state_replace):
                with self.assertRaisesRegex(OSError, "state replacement interruption"):
                    store.save(durable)
            self.assertTrue(store.supervisor_archive_transaction_path.exists())
            recovered = store.load()
            self.assertFalse(store.supervisor_archive_transaction_path.exists())
            self.assertEqual(recovered["review"]["round"], 1)
            self.assertEqual(recovered["review"]["archived_supervisor_count"], 0)
            self.assertEqual(recovered["review"]["archived_supervisor_outcomes"], [])
            self.assertEqual(recovered["review"]["completed_supervisor_count"], 1)
            self.assertIsNotNone(recovered.supervisor_archive_authority["pending_completion"])
            rs.validate_state(recovered)

    def test_oversized_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = state()
            value["retry"] = {"detail": "x" * rs.MAX_STATE_BYTES}
            with self.assertRaises(rs.ValidationError):
                rs.StateStore(temporary).initialize(value)

    def test_state_initialize_is_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(state())
            with self.assertRaises(rs.ValidationError):
                store.initialize(state())

    def test_completed_scope_requires_explicit_fresh_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            completed = state()
            complete_scope(completed)
            completed["maintenance"]["schedule_id"] = "schedule-1"
            store = rs.StateStore(temporary)
            store.initialize(completed)
            replacement = rs.new_state(
                activation_request(),
                identity(),
                activation_id="activation-0002",
                orchestrator_thread_id="orchestrator-1",
                installed_roundlet_digest=DIGEST,
                owner_actor=OWNER_ACTOR,
                capability_preflight=CAPABILITY_PREFLIGHT,
                orchestrator_creation_receipt=role_receipt("orchestrator", "orchestrator-1"),
                skill_root=SKILL_ROOT,
            )
            store.initialize(replacement, replace_completed_scope=True)
            self.assertEqual(store.load()["activation"]["id"], "activation-0002")
            self.assertEqual(store.load()["maintenance"]["schedule_id"], "schedule-1")

    def envelope(self, value, key="receipt-key-0001"):
        return {
            "protocol_version": value["versions"]["protocol"],
            "review_contract_version": value["versions"]["review_contract"],
            "activation_id": value["activation"]["id"],
            "repository": "owner/project",
            "repository_id": 123,
            "selected_issue": value["task"]["issue"],
            "source_role": "worker",
            "source_thread_id": value["task"]["worker_thread_id"],
            "phase": value["phase"],
            "base_sha": value["task"]["base_sha"],
            "candidate_sha": value["task"]["candidate_sha"],
            "idempotency_key": key,
            "timestamp": "2026-07-14T02:00:00Z",
            "handoff": {"status": "done"},
        }

    def test_mailbox_rejects_wrong_thread(self):
        value = assigned_state()
        payload = self.envelope(value)
        payload["candidate_sha"] = SHA_B
        payload["source_thread_id"] = "another-worker"
        with self.assertRaises(rs.MailboxError):
            rs.validate_mailbox_envelope(payload, value, "worker-handoff")

    def test_mailbox_allows_worker_to_advance_candidate(self):
        value = assigned_state()
        payload = self.envelope(value)
        payload["candidate_sha"] = SHA_C
        rs.validate_mailbox_envelope(payload, value, "worker-handoff")

    def test_mailbox_rejects_stale_supervisor_candidate(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        record_draft(value)
        begin_review(value, "supervisor-1")
        payload = self.envelope(value)
        payload.update(
            {
                "source_role": "supervisor",
                "source_thread_id": "supervisor-1",
                "phase": value["phase"],
                "candidate_sha": SHA_C,
            }
        )
        with self.assertRaises(rs.MailboxError):
            rs.validate_mailbox_envelope(payload, value, "supervisor-review")

    def test_consume_records_before_delete_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = assigned_state()
            store = rs.StateStore(temporary)
            store.initialize(value)
            mailboxes = rs.MailboxStore(temporary)
            payload = self.envelope(value)
            payload["candidate_sha"] = SHA_B
            mailboxes.write("worker-handoff", payload, value)
            calls = []
            receipt = mailboxes.consume(
                "worker-handoff",
                store,
                mutate=lambda item: calls.append(item) or {"comment_id": 1},
                advance=lambda current, item, result: current.update(
                    {"retry": {"advanced_with_comment": result["comment_id"]}}
                ),
            )
            self.assertEqual(receipt, {"comment_id": 1})
            self.assertEqual(len(calls), 1)
            self.assertFalse(mailboxes.path("worker-handoff").exists())
            self.assertEqual(
                store.load()["receipts"][payload["idempotency_key"]]["receipt"],
                receipt,
            )
            self.assertEqual(store.load()["retry"]["advanced_with_comment"], 1)

            rs.atomic_write_json(mailboxes.path("worker-handoff"), payload)
            receipt2 = mailboxes.consume(
                "worker-handoff",
                store,
                mutate=lambda item: self.fail("must not duplicate mutation"),
            )
            self.assertEqual(receipt2, receipt)

    def test_reconcile_recovers_mutation_before_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = assigned_state()
            store = rs.StateStore(temporary)
            store.initialize(value)
            mailboxes = rs.MailboxStore(temporary)
            payload = self.envelope(value)
            payload["candidate_sha"] = SHA_B
            mailboxes.write("worker-handoff", payload, value)
            store.begin_mailbox_intent(
                payload["idempotency_key"],
                "worker-handoff",
                rs.digest_json(payload),
            )
            receipt = mailboxes.consume(
                "worker-handoff",
                store,
                reconcile=lambda item: {"comment_id": 9},
                mutate=lambda item: self.fail("reconciled mutation must not repeat"),
            )
            self.assertEqual(receipt["comment_id"], 9)

    def test_pending_receipt_does_not_bypass_current_phase_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = assigned_state()
            store = rs.StateStore(temporary)
            store.initialize(value)
            mailboxes = rs.MailboxStore(temporary)
            payload = self.envelope(value)
            payload["candidate_sha"] = SHA_B
            mailboxes.write("worker-handoff", payload, value)
            store.begin_mailbox_intent(
                payload["idempotency_key"],
                "worker-handoff",
                rs.digest_json(payload),
            )
            changed = store.load()
            rs.request_maintenance(changed, "pause before mutation")
            store.save(changed)
            calls = []
            with self.assertRaises(rs.MailboxError):
                mailboxes.consume(
                    "worker-handoff",
                    store,
                    reconcile=lambda item: calls.append("reconcile") or False,
                    mutate=lambda item: calls.append("mutate") or {"comment_id": 1},
                )
            self.assertEqual(calls, [])

    def test_completed_receipt_replays_after_phase_advance(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = assigned_state()
            store = rs.StateStore(temporary)
            store.initialize(value)
            mailboxes = rs.MailboxStore(temporary)
            payload = self.envelope(value)
            payload["candidate_sha"] = SHA_B
            mailboxes.write("worker-handoff", payload, value)
            payload_digest = rs.digest_json(payload)
            store.begin_mailbox_intent(payload["idempotency_key"], "worker-handoff", payload_digest)
            store.complete_mailbox_intent(
                payload["idempotency_key"],
                "worker-handoff",
                payload_digest,
                {"comment_id": 7},
                update=lambda current: rs.set_candidate(current, SHA_B, clean=True),
            )
            self.assertIsNone(store.load()["task"]["active_role"])
            receipt = mailboxes.consume(
                "worker-handoff",
                store,
                mutate=lambda item: self.fail("completed mutation must not repeat"),
            )
            self.assertEqual(receipt, {"comment_id": 7})
            self.assertFalse(mailboxes.path("worker-handoff").exists())

    def test_unread_mailbox_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = assigned_state()
            mailboxes = rs.MailboxStore(temporary)
            first = self.envelope(value)
            first["candidate_sha"] = SHA_B
            second = copy.deepcopy(first)
            second["candidate_sha"] = SHA_C
            mailboxes.write("worker-handoff", first, value)
            with self.assertRaises(rs.MailboxError):
                mailboxes.write("worker-handoff", second, value)

    def test_malformed_key_blocks_before_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = assigned_state()
            store = rs.StateStore(temporary)
            store.initialize(value)
            mailboxes = rs.MailboxStore(temporary)
            payload = self.envelope(value, key="bad key")
            payload["candidate_sha"] = SHA_B
            rs.atomic_write_json(mailboxes.path("worker-handoff"), payload)
            calls = []
            with self.assertRaises(rs.MailboxError):
                mailboxes.consume(
                    "worker-handoff",
                    store,
                    mutate=lambda item: calls.append(item) or {"comment_id": 1},
                )
            self.assertEqual(calls, [])

    def test_same_key_cannot_bind_a_different_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = assigned_state()
            store = rs.StateStore(temporary)
            store.initialize(value)
            mailboxes = rs.MailboxStore(temporary)
            first = self.envelope(value)
            first["candidate_sha"] = SHA_B
            mailboxes.write("worker-handoff", first, value)
            mailboxes.consume(
                "worker-handoff",
                store,
                mutate=lambda item: {"comment_id": 1},
            )
            second = copy.deepcopy(first)
            second["candidate_sha"] = SHA_C
            calls = []
            with self.assertRaises(rs.MailboxError):
                mailboxes.write("worker-handoff", second, store.load())
            self.assertEqual(calls, [])

    def test_oversized_mailbox_and_receipt_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = assigned_state()
            store = rs.StateStore(temporary)
            store.initialize(value)
            mailboxes = rs.MailboxStore(temporary)
            payload = self.envelope(value)
            payload["candidate_sha"] = SHA_B
            payload["handoff"]["detail"] = "x" * rs.MAX_MAILBOX_BYTES
            with self.assertRaises(rs.MailboxError):
                mailboxes.write("worker-handoff", payload, value)
            small = self.envelope(value)
            small["candidate_sha"] = SHA_B
            digest = rs.digest_json(small)
            store.begin_mailbox_intent(small["idempotency_key"], "worker-handoff", digest)
            with self.assertRaises(rs.MailboxError):
                store.complete_mailbox_intent(
                    small["idempotency_key"],
                    "worker-handoff",
                    digest,
                    {"detail": "x" * rs.MAX_RECEIPT_BYTES},
                )

    def test_near_limit_receipts_are_compacted_by_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = assigned_state()
            store = rs.StateStore(temporary)
            store.initialize(value)
            mailboxes = rs.MailboxStore(temporary)
            for sequence in range(1, 25):
                current = store.load()
                payload = self.envelope(current, key=f"receipt-key-{sequence:04d}")
                payload["candidate_sha"] = SHA_B
                mailboxes.write("worker-handoff", payload, current)
                mailboxes.consume(
                    "worker-handoff",
                    store,
                    mutate=lambda item, number=sequence: {
                        "sequence": number,
                        "detail": "x" * 64_000,
                    },
                )
            current = store.load()
            self.assertGreater(current["receipt_archive"]["count"], 0)
            self.assertLess(len(rs.canonical_json(current).encode("utf-8")), rs.MAX_STATE_BYTES)

    def test_archived_receipt_key_cannot_replay_after_over_one_hundred_rounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = assigned_state()
            store = rs.StateStore(temporary)
            store.initialize(value)
            mailboxes = rs.MailboxStore(temporary)
            first_payload = None
            for sequence in range(1, 161):
                current = store.load()
                payload = self.envelope(current, key=f"receipt-key-{sequence:04d}")
                payload["candidate_sha"] = SHA_B
                if first_payload is None:
                    first_payload = copy.deepcopy(payload)
                mailboxes.write("worker-handoff", payload, current)
                mailboxes.consume(
                    "worker-handoff",
                    store,
                    mutate=lambda item, number=sequence: {"sequence": number},
                )
            current = store.load()
            self.assertEqual(current["mailbox_high_water"]["worker-handoff"], 160)
            self.assertNotIn("receipt-key-0001", current["receipts"])
            first_payload["timestamp"] = "2026-07-14T03:00:00Z"
            with self.assertRaises(rs.MailboxError):
                mailboxes.write("worker-handoff", first_payload, current)

    def test_context_discard_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            mailboxes = rs.MailboxStore(temporary)
            mailboxes.discard_github_context_after_dispatch()
            mailboxes.discard_github_context_after_dispatch()

    def test_github_context_is_durable_before_worker_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = state()
            rs.transition_state(value, "selecting-task")
            issue_evidence = issue_connector_evidence(11)
            snapshot = rs.IssueSnapshot(
                issue=11,
                umbrella=10,
                repository="owner/project",
                membership_evidence=(
                    formal_membership_evidence(11, 10, issue_evidence["revision"]),
                ),
                issue_evidence=issue_evidence,
            )
            value["selection"] = select_from_connector(
                value,
                [snapshot],
                refresh_manifest(value, {10: [11]}, [snapshot]),
            )
            payload = {
                "protocol_version": value["versions"]["protocol"],
                "review_contract_version": value["versions"]["review_contract"],
                "activation_id": value["activation"]["id"],
                "repository": "owner/project",
                "repository_id": 123,
                "selected_issue": 11,
                "source_role": "orchestrator",
                "source_thread_id": "orchestrator-1",
                "phase": "selecting-task",
                "base_sha": SHA_A,
                "candidate_sha": None,
                "idempotency_key": "context-key-0001",
                "timestamp": "2026-07-14T02:00:00Z",
                "context": {"issue": "bounded immutable context"},
            }
            mailboxes = rs.MailboxStore(temporary)
            store = rs.StateStore(temporary)
            store.initialize(value)
            mailboxes.write("github-context", payload, value)
            self.assertTrue(mailboxes.path("github-context").exists())
            receipt = mailboxes.consume(
                "github-context",
                store,
                mutate=lambda item: {
                    "worker_thread_id": "worker-11",
                    "worktree": "/repo-worktrees/issue-11",
                    "branch": "codex/issue-11",
                    "base_sha": SHA_A,
                    "worker_creation_receipt": role_receipt("worker", "worker-11"),
                },
                advance=lambda current, item, result: rs.assign_task(
                    current,
                    umbrella_issue=10,
                    issue=11,
                    branch=result["branch"],
                    worktree=result["worktree"],
                    worker_thread_id=result["worker_thread_id"],
                    worker_creation_receipt=result["worker_creation_receipt"],
                    base_sha=result["base_sha"],
                ),
            )
            self.assertEqual(receipt["worker_thread_id"], "worker-11")
            self.assertEqual(store.load()["phase"], "worker-running")
            self.assertFalse(mailboxes.path("github-context").exists())

    def test_unauthorized_github_context_never_invokes_worker_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            operations = activation_request()["authorize"]
            operations["create_task_branches"] = False
            value = state(operations=operations)
            rs.transition_state(value, "selecting-task")
            issue_evidence = issue_connector_evidence(11)
            snapshot = rs.IssueSnapshot(
                issue=11,
                umbrella=10,
                repository="owner/project",
                membership_evidence=(
                    formal_membership_evidence(11, 10, issue_evidence["revision"]),
                ),
                issue_evidence=issue_evidence,
            )
            value["selection"] = select_from_connector(
                value,
                [snapshot],
                refresh_manifest(value, {10: [11]}, [snapshot]),
            )
            payload = {
                "protocol_version": value["versions"]["protocol"],
                "review_contract_version": value["versions"]["review_contract"],
                "activation_id": value["activation"]["id"],
                "repository": "owner/project",
                "repository_id": 123,
                "selected_issue": 11,
                "source_role": "orchestrator",
                "source_thread_id": "orchestrator-1",
                "phase": "selecting-task",
                "base_sha": SHA_A,
                "candidate_sha": None,
                "idempotency_key": "context-key-0001",
                "timestamp": "2026-07-14T02:00:00Z",
            }
            store = rs.StateStore(temporary)
            store.initialize(value)
            mailboxes = rs.MailboxStore(temporary)
            rs.atomic_write_json(mailboxes.path("github-context"), payload)
            calls = []
            with self.assertRaises(rs.MailboxError):
                mailboxes.consume(
                    "github-context",
                    store,
                    mutate=lambda item: calls.append(item) or {"worker_thread_id": "forbidden"},
                )
            self.assertEqual(calls, [])
            self.assertEqual(store.load()["mailbox_high_water"]["github-context"], 0)

    def test_unauthorized_draft_pr_worker_handoff_never_invokes_callback(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = assigned_state()
            set_operation(value, "create_draft_prs", False)
            payload = self.envelope(value)
            payload["candidate_sha"] = SHA_B
            store = rs.StateStore(temporary)
            store.initialize(value)
            mailboxes = rs.MailboxStore(temporary)
            rs.atomic_write_json(mailboxes.path("worker-handoff"), payload)
            calls = []
            with self.assertRaises(rs.MailboxError):
                mailboxes.consume(
                    "worker-handoff",
                    store,
                    mutate=lambda item: calls.append(item) or {"pr_number": 22},
                )
            self.assertEqual(calls, [])
            self.assertEqual(store.load()["mailbox_high_water"]["worker-handoff"], 0)

    def test_concurrent_consumers_execute_one_mutation_and_one_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = assigned_state()
            store = rs.StateStore(temporary)
            store.initialize(value)
            mailboxes = rs.MailboxStore(temporary)
            payload = self.envelope(value)
            payload["candidate_sha"] = SHA_B
            mailboxes.write("worker-handoff", payload, value)
            entered = threading.Event()
            release = threading.Event()
            calls = []
            outcomes = []

            def mutate(item):
                calls.append(item["idempotency_key"])
                entered.set()
                release.wait(5)
                return {"comment_id": 1}

            def consume():
                try:
                    outcomes.append(mailboxes.consume("worker-handoff", store, mutate=mutate))
                except rs.RoundletError as exc:
                    outcomes.append(type(exc).__name__)

            first = threading.Thread(target=consume)
            second = threading.Thread(target=consume)
            first.start()
            self.assertTrue(entered.wait(2))
            second.start()
            release.set()
            first.join(5)
            second.join(5)
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(calls, [payload["idempotency_key"]])
            durable = store.load()["receipts"][payload["idempotency_key"]]
            self.assertEqual(durable["status"], "complete")
            self.assertEqual(durable["receipt"], {"comment_id": 1})
            self.assertIn({"comment_id": 1}, outcomes)


class CompactionTests(unittest.TestCase):
    def test_task_compaction_is_bounded(self):
        value = premerge_state()
        value["phase"] = "task-done"
        value["task"]["merge_sha"] = SHA_C
        rs.compact_completed_task(
            value,
            issue_url="https://github.com/owner/project/issues/11",
            pr_url="https://github.com/owner/project/pull/22",
            merge_sha=SHA_C,
            completed_at="2026-07-14T03:00:00Z",
        )
        self.assertIsNone(value["task"])
        self.assertEqual(value["completed_tasks"][0]["review_rounds"], 2)
        self.assertEqual(value["completed_tasks"][0]["terminal_review"]["outcome"], "FINAL_SUPERVISOR_PASS")
        self.assertEqual(value["completed_tasks"][0]["terminal_review"]["round"], 2)
        self.assertNotIn("changed_files", value["completed_tasks"][0])

    def test_task_compaction_retains_exhausted_worker_finalized_outcome(self):
        value = assigned_state()
        set_review_budget(value, 1)
        rs.set_candidate(value, SHA_B, clean=True)
        value["task"].update({"pr_number": 22, "pr_url": "https://github.com/owner/project/pull/22", "pr_ready": True})
        value["phase"] = "ready"
        begin_review(value, "supervisor-budget", final=True)
        rs.accept_supervisor_result(
            value,
            thread_id="supervisor-budget",
            candidate_sha=SHA_B,
            result="FINDINGS",
            non_blocking_items=["fix this"],
        )
        rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-budget")
        rs.record_worker_final_dispositions(
            value,
            worker_thread_id="worker-11",
            head_sha=SHA_C,
            clean=True,
            tests_passed=True,
            dispositions=[{"finding": "fix this", "disposition": "FIXED", "evidence": "test"}],
        )
        rs.begin_worker_merge_readiness(value)
        rs.record_worker_ready_to_merge(value, worker_thread_id="worker-11", head_sha=SHA_C, clean=True)
        value["phase"] = "task-done"
        value["task"]["merge_sha"] = SHA_D
        rs.compact_completed_task(
            value,
            issue_url="https://github.com/owner/project/issues/11",
            pr_url="https://github.com/owner/project/pull/22",
            merge_sha=SHA_D,
            completed_at="2026-07-14T03:00:00Z",
        )
        terminal = value["completed_tasks"][0]["terminal_review"]
        self.assertEqual(terminal["outcome"], "REVIEW_BUDGET_EXHAUSTED_WORKER_FINALIZED")
        self.assertEqual(terminal["reviewed_candidate_sha"], SHA_B)
        self.assertEqual(terminal["candidate_sha"], SHA_C)

    def test_scope_compaction_writes_one_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = state()
            complete_scope(value)
            summary = rs.compact_scope(value, temporary, completed_at="2026-07-14T04:00:00Z")
            self.assertEqual(summary["final_result"], "scope-complete")
            files = sorted(path.name for path in Path(temporary).iterdir())
            self.assertEqual(files, ["last-scope-summary.json", "state.json"])


class RoleModelConfigTests(unittest.TestCase):
    def copy_skill(self, directory):
        destination = Path(directory) / "roundlet"
        shutil.copytree(SKILL_ROOT, destination)
        return destination

    def test_validated_config_and_cli_output_are_canonical(self):
        config = rs.load_role_model_config(SKILL_ROOT)
        self.assertEqual(config["config_digest"], rs.digest_json({key: config[key] for key in ("schema_version", "defaults", "legacy_profiles")}))
        completed = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts" / "orchestration_state.py"), "role-config", "--skill-root", str(SKILL_ROOT)],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout), config)

    def test_config_rejects_missing_unknown_or_invalid_role_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_skill(temporary)
            path = root / "assets" / "roundlet-config.json"
            path.unlink()
            with self.assertRaisesRegex(rs.ValidationError, "missing"):
                rs.load_role_model_config(root)
        for mutation in (
            lambda value: value.update({"unknown": True}),
            lambda value: value["defaults"]["roles"].pop("worker"),
            lambda value: value["defaults"]["roles"]["worker"].update({"model": "bad model"}),
            lambda value: value["defaults"]["roles"]["worker"].update({"reasoning_effort": "soft"}),
            lambda value: value.update({"schema_version": 1}),
            lambda value: value.update({"schema_version": True}),
            lambda value: value.update({"schema_version": 1.0}),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_skill(temporary)
                path = root / "assets" / "roundlet-config.json"
                value = json.loads(path.read_text())
                mutation(value)
                path.write_text(json.dumps(value))
                with self.assertRaises(rs.ValidationError):
                    rs.load_role_model_config(root)


    def test_config_rejects_invalid_review_policy_values(self):
        for bad in (True, 0, -1, 1.5, 65):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_skill(temporary)
                path = root / "assets" / "roundlet-config.json"
                value = json.loads(path.read_text())
                value["defaults"]["review"]["max_supervisor_cycles"] = bad
                path.write_text(json.dumps(value))
                with self.assertRaises(rs.ValidationError):
                    rs.load_role_model_config(root)
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_skill(temporary)
            path = root / "assets" / "roundlet-config.json"
            value = json.loads(path.read_text())
            value["defaults"]["review"]["extra"] = 5
            path.write_text(json.dumps(value))
            with self.assertRaises(rs.ValidationError):
                rs.load_role_model_config(root)
        for bad in (True, 0, -1, 1.5, 6):
            with self.subTest(converge_after=bad), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_skill(temporary)
                path = root / "assets" / "roundlet-config.json"
                value = json.loads(path.read_text())
                value["defaults"]["review"]["converge_after_supervisor_cycles"] = bad
                path.write_text(json.dumps(value))
                with self.assertRaises(rs.ValidationError):
                    rs.load_role_model_config(root)
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_skill(temporary)
            path = root / "assets" / "roundlet-config.json"
            value = json.loads(path.read_text())
            value["defaults"]["review"].pop("converge_after_supervisor_cycles")
            path.write_text(json.dumps(value))
            with self.assertRaises(rs.ValidationError):
                rs.load_role_model_config(root)

    def test_config_rejects_duplicate_keys_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_skill(temporary)
            path = root / "assets" / "roundlet-config.json"
            path.write_text('{"schema_version":1,"schema_version":1,"defaults":{},"legacy_profiles":{}}}')
            with self.assertRaisesRegex(rs.ValidationError, "duplicate"):
                rs.load_role_model_config(root)
            path.write_text('{"schema_version":2,"defaults":{"roles":{"worker":{"model":"x","model":"y","reasoning_effort":"high"}},"legacy_profiles":{}}}')
            with self.assertRaisesRegex(rs.ValidationError, "duplicate"):
                rs.load_role_model_config(root)
            path.write_bytes(b"\xff")
            with self.assertRaisesRegex(rs.ValidationError, "unreadable"):
                rs.load_role_model_config(root)
            completed = subprocess.run(
                [sys.executable, str(root / "scripts" / "orchestration_state.py"), "role-config", "--skill-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("BLOCKED", completed.stderr)

    def test_activation_requires_root_and_matching_digest(self):
        kwargs = {
            "activation_id": "activation-0001",
            "orchestrator_thread_id": "orchestrator-1",
            "installed_roundlet_digest": DIGEST,
            "owner_actor": OWNER_ACTOR,
            "capability_preflight": CAPABILITY_PREFLIGHT,
            "orchestrator_creation_receipt": role_receipt("orchestrator", "orchestrator-1"),
        }
        with self.assertRaises(TypeError):
            rs.new_state(activation_request(), identity(), **kwargs)
        with self.assertRaises(rs.GuardError):
            rs.new_state(activation_request(), identity(), **{**kwargs, "skill_root": SKILL_ROOT, "installed_roundlet_digest": "d" * 64})

    def test_activation_rejects_config_change_during_digest_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_skill(temporary)
            digest = rs.skill_content_digest(root)
            original_loader = rs.load_role_model_config
            receipt = role_receipt("orchestrator", "orchestrator-1")

            def mutate_after_load(skill_root):
                loaded = original_loader(skill_root)
                path = Path(skill_root) / "assets" / "roundlet-config.json"
                value = json.loads(path.read_text())
                value["defaults"]["roles"]["worker"]["reasoning_effort"] = "low"
                path.write_text(json.dumps(value))
                return loaded

            with mock.patch.object(rs, "load_role_model_config", side_effect=mutate_after_load):
                with self.assertRaisesRegex(rs.GuardError, "changed while"):
                    rs.new_state(
                        activation_request(), identity(), activation_id="activation-0001", orchestrator_thread_id="orchestrator-1",
                        installed_roundlet_digest=digest, owner_actor=OWNER_ACTOR, capability_preflight=CAPABILITY_PREFLIGHT,
                        orchestrator_creation_receipt=receipt, skill_root=root,
                    )

    def test_activation_binds_snapshot_to_receipts_and_scope(self):
        digest = rs.skill_content_digest(SKILL_ROOT)
        value = rs.new_state(
            activation_request(), identity(), activation_id="activation-0001", orchestrator_thread_id="orchestrator-1",
            installed_roundlet_digest=digest, owner_actor=OWNER_ACTOR, capability_preflight=CAPABILITY_PREFLIGHT,
            orchestrator_creation_receipt=role_receipt("orchestrator", "orchestrator-1"), skill_root=SKILL_ROOT,
        )
        snapshot = copy.deepcopy(value["activation"]["role_model_snapshot"])
        self.assertEqual(value["activation"]["role_model_snapshot_digest"], rs.role_model_snapshot_digest(snapshot))
        value["activation"]["role_model_snapshot"]["worker"]["reasoning_effort"] = "low"
        with self.assertRaises(rs.ScopeError):
            rs.validate_state(value)

    def test_config_change_does_not_replace_existing_activation_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_skill(temporary)
            digest = rs.skill_content_digest(root)
            value = rs.new_state(
                activation_request(), identity(), activation_id="activation-0001", orchestrator_thread_id="orchestrator-1",
                installed_roundlet_digest=digest, owner_actor=OWNER_ACTOR, capability_preflight=CAPABILITY_PREFLIGHT,
                orchestrator_creation_receipt=role_receipt("orchestrator", "orchestrator-1"), skill_root=root,
            )
            before = copy.deepcopy(value["activation"]["role_model_snapshot"])
            path = root / "assets" / "roundlet-config.json"
            config = json.loads(path.read_text())
            config["defaults"]["roles"]["worker"]["reasoning_effort"] = "low"
            path.write_text(json.dumps(config))
            rs.validate_state(value)
            self.assertEqual(value["activation"]["role_model_snapshot"], before)

    def test_policy3_migration_keeps_legacy_snapshot(self):
        value = assigned_state()
        downgrade_to_policy3(value)
        migrated = rs._migrate_state_document(value)
        legacy = rs.load_role_model_config(SKILL_ROOT)["legacy_profiles"]["policy_3"]
        self.assertEqual(migrated["activation"]["role_model_snapshot"], legacy)
        with self.assertRaisesRegex(rs.ScopeError, "durable StateStore migration gateway"):
            rs.validate_state(migrated)


class SkillDigestTests(unittest.TestCase):
    def copy_skill(self, directory, relative_destination):
        destination = Path(directory) / relative_destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            SKILL_ROOT,
            destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        return destination

    def test_skill_digest_is_stable_lowercase_sha256(self):
        first = rs.skill_content_digest(SKILL_ROOT)
        second = rs.skill_content_digest(SKILL_ROOT)
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{64}$")

    def test_skill_digest_is_independent_of_parent_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            first_root = self.copy_skill(temporary, "first/roundlet")
            second_root = self.copy_skill(temporary, "second/nested/roundlet")
            self.assertEqual(
                rs.skill_content_digest(first_root),
                rs.skill_content_digest(second_root),
            )

    def test_skill_digest_changes_for_every_included_file(self):
        baseline = rs.skill_content_digest(SKILL_ROOT)
        included_files = [
            path.relative_to(SKILL_ROOT)
            for path in SKILL_ROOT.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and not path.name.endswith((".pyc", ".pyo"))
        ]
        with tempfile.TemporaryDirectory() as temporary:
            for index, relative in enumerate(included_files):
                with self.subTest(path=relative.as_posix()):
                    copied_root = self.copy_skill(temporary, f"case-{index}/roundlet")
                    changed = copied_root / relative
                    changed.write_bytes(changed.read_bytes() + b"\nroundlet-digest-regression\n")
                    self.assertNotEqual(rs.skill_content_digest(copied_root), baseline)

    def test_skill_digest_changes_when_relative_path_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied_root = self.copy_skill(temporary, "roundlet")
            baseline = rs.skill_content_digest(copied_root)
            operator_guide = copied_root / "references" / "operator-guide.md"
            operator_guide.rename(operator_guide.with_name("operator-manual.md"))
            self.assertNotEqual(rs.skill_content_digest(copied_root), baseline)

    def test_skill_digest_ignores_python_cache_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied_root = self.copy_skill(temporary, "roundlet")
            baseline = rs.skill_content_digest(copied_root)
            cache = copied_root / "scripts" / "__pycache__"
            cache.mkdir()
            (cache / "orchestration_state.cpython-313.pyc").write_bytes(b"cache")
            (copied_root / "scripts" / "ignored.pyc").write_bytes(b"cache")
            (copied_root / "scripts" / "ignored.pyo").write_bytes(b"cache")
            self.assertEqual(rs.skill_content_digest(copied_root), baseline)

    def test_repository_root_is_not_a_skill_root(self):
        with self.assertRaisesRegex(rs.ValidationError, "does not contain SKILL.md"):
            rs.skill_content_digest(REPO_ROOT)


class ScriptedRunner(rs.CommandRunner):
    def __init__(self, *, candidate=SHA_B):
        self.calls = []
        self.candidate = candidate

    def run(self, args, cwd=None):
        args = list(args)
        self.calls.append((args, str(cwd) if cwd else None))
        if args[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return str(cwd) if str(cwd) == "/repo-worktrees/issue-11" else "/repo"
        if args[:3] == ["git", "rev-parse", "--git-common-dir"]:
            return "/repo/.git"
        if args[:4] == ["git", "remote", "get-url", "--all"]:
            return "https://github.com/owner/project.git"
        if args[:5] == ["git", "remote", "get-url", "--push", "--all"]:
            return "https://github.com/owner/project.git"
        if args[:3] == ["git", "status", "--porcelain=v1"]:
            return ""
        if args[:3] == ["git", "branch", "--show-current"]:
            return "codex/issue-11" if str(cwd) == "/repo-worktrees/issue-11" else "main"
        if args[:2] == ["git", "rev-parse"]:
            ref = args[2]
            if ref == "HEAD" and str(cwd) == "/repo-worktrees/issue-11":
                return self.candidate
            if ref in {"HEAD", "refs/heads/main", "refs/remotes/origin/main"}:
                return SHA_A
            if ref == "refs/heads/codex/issue-11":
                return self.candidate
        if args[:2] == ["git", "push"]:
            return ""
        if args[:3] == ["git", "merge-base", "--is-ancestor"]:
            return ""
        if args[:3] == ["git", "worktree", "list"]:
            return "worktree /repo-worktrees/issue-11\nbranch refs/heads/codex/issue-11"
        if args[:3] == ["git", "worktree", "remove"]:
            return ""
        if args[:3] == ["git", "branch", "-d"]:
            return ""
        if args[:2] in (["git", "fetch"], ["git", "merge"]):
            return ""
        raise AssertionError(f"unexpected command: {args}")


class DetachedRunner(ScriptedRunner):
    def __init__(self):
        super().__init__()
        self.head = SHA_A

    def run(self, args, cwd=None):
        args = list(args)
        if args[:3] == ["git", "branch", "--show-current"]:
            self.calls.append((args, str(cwd) if cwd else None))
            return ""
        if args[:3] == ["git", "worktree", "list"]:
            self.calls.append((args, str(cwd) if cwd else None))
            return (
                "worktree /repo\nHEAD " + self.head + "\ndetached\n\n"
                "worktree /owner-checkout\nHEAD " + SHA_A + "\nbranch refs/heads/main"
            )
        if args[:2] == ["git", "merge"]:
            self.calls.append((args, str(cwd) if cwd else None))
            self.head = SHA_B
            return ""
        if args[:2] == ["git", "rev-parse"]:
            self.calls.append((args, str(cwd) if cwd else None))
            ref = args[2]
            if ref == "HEAD":
                return self.head
            if ref == "refs/heads/main":
                return SHA_A
            if ref == "refs/remotes/origin/main":
                return SHA_B
        return super().run(args, cwd)


class CleanupRunner(ScriptedRunner):
    def __init__(self, *, root_head=SHA_A):
        super().__init__()
        self.root_head = root_head

    def run(self, args, cwd=None):
        args = list(args)
        location = str(cwd) if cwd else None
        if args[:3] == ["git", "branch", "--show-current"]:
            self.calls.append((args, location))
            return "main"
        if args[:3] == ["git", "worktree", "list"]:
            self.calls.append((args, location))
            return "worktree /repo\nbranch refs/heads/main"
        if args[:3] == ["git", "branch", "--list"]:
            self.calls.append((args, location))
            return "  codex/issue-11"
        if args[:2] == ["git", "rev-parse"]:
            ref = args[2]
            if ref == "HEAD" and location == "/repo":
                self.calls.append((args, location))
                return self.root_head
            if ref == "refs/heads/main":
                self.calls.append((args, location))
                return SHA_A
            if ref == "refs/remotes/origin/main":
                self.calls.append((args, location))
                return SHA_C
            if ref == "refs/heads/codex/issue-11":
                self.calls.append((args, location))
                return SHA_B
        if args[:3] == ["git", "merge-base", "--is-ancestor"]:
            self.calls.append((args, location))
            if args[3] == SHA_D:
                raise rs.GuardError("clean orchestration checkout is ahead of remote base")
            return ""
        if args[:2] == ["git", "merge"]:
            self.calls.append((args, location))
            self.root_head = SHA_C
            return ""
        if args[:3] == ["git", "branch", "-d"]:
            self.calls.append((args, location))
            return ""
        return super().run(args, cwd)


class GuardTests(unittest.TestCase):
    def cleanup_state(self, directory):
        digest = rs.skill_content_digest(SKILL_ROOT)
        value = premerge_state()
        value["skill"]["content_digest"] = digest
        value["activation"]["scope_digest"] = rs.compute_scope_digest(
            value["activation"]["repository"],
            value["activation"]["base_branch"],
            value["activation"]["umbrella_issues"],
            value["activation"]["allowed_operations"],
            digest,
            owner_actor=value["activation"]["owner_actor"],
            capability_preflight=value["activation"]["capability_preflight"],
            orchestrator_creation_receipt=value["activation"]["orchestrator_creation_receipt"],
            role_model_snapshot=value["activation"]["role_model_snapshot"],
            role_model_snapshot_digest=value["activation"]["role_model_snapshot_digest"],
            review_policy_snapshot=value["activation"]["review_policy_snapshot"],
            review_policy_snapshot_digest=value["activation"]["review_policy_snapshot_digest"],
            legacy_unbounded_review=value["activation"]["legacy_unbounded_review"],
        )
        record_merge(value)
        record_close(value)
        rs.record_children_archived(
            value,
            worker_thread_id="worker-11",
            supervisor_thread_ids=[],
        )
        store = rs.StateStore(directory)
        store.initialize(value)
        return store, digest

    def guarded_state(self, directory):
        digest = rs.skill_content_digest(SKILL_ROOT)
        value = rs.new_state(
            activation_request(),
            identity(),
            activation_id="activation-0001",
            orchestrator_thread_id="orchestrator-1",
            installed_roundlet_digest=digest,
            owner_actor=OWNER_ACTOR,
            capability_preflight=CAPABILITY_PREFLIGHT,
            orchestrator_creation_receipt=role_receipt("orchestrator", "orchestrator-1"),
            skill_root=SKILL_ROOT,
            now="2026-07-14T00:00:00Z",
        )
        rs.transition_state(value, "selecting-task")
        set_selection(value)
        rs.assign_task(
            value,
            umbrella_issue=10,
            issue=11,
            branch="codex/issue-11",
            worktree="/repo-worktrees/issue-11",
            worker_thread_id="worker-11",
            worker_creation_receipt=role_receipt("worker", "worker-11"),
            base_sha=SHA_A,
        )
        rs.set_candidate(value, SHA_B, clean=True)
        store = rs.StateStore(directory)
        store.initialize(value)
        return store, digest

    def test_guarded_push_uses_exact_recorded_shape(self):
        with tempfile.TemporaryDirectory() as temporary:
            store, digest = self.guarded_state(temporary)
            runner = ScriptedRunner()
            guard = rs.GuardedGit(
                store,
                activation_id="activation-0001",
                installed_digest=digest,
                skill_root=SKILL_ROOT,
                runner=runner,
            )
            guard.push_task_branch()
            commands = [call[0] for call in runner.calls]
            self.assertIn(["git", "push", "origin", "codex/issue-11"], commands)
            self.assertFalse(any("--force" in command for command in commands))

    def test_guarded_push_accepts_completed_final_repair_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            digest = rs.skill_content_digest(SKILL_ROOT)
            value = assigned_state(digest=digest)
            set_review_budget(value, 1)
            rs.set_candidate(value, SHA_B, clean=True)
            value["task"].update({"pr_number": 22, "pr_url": "https://github.com/owner/project/pull/22"})
            value["task"]["pr_ready"] = True
            value["phase"] = "ready"
            begin_review(value, "supervisor-budget", final=True)
            rs.accept_supervisor_result(
                value,
                thread_id="supervisor-budget",
                candidate_sha=SHA_B,
                result="FINDINGS",
                non_blocking_items=["fix this"],
            )
            rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-budget")
            rs.record_worker_final_dispositions(
                value,
                worker_thread_id="worker-11",
                head_sha=SHA_C,
                clean=True,
                tests_passed=True,
                dispositions=[{"finding": "fix this", "disposition": "FIXED", "evidence": "test"}],
            )
            store = rs.StateStore(temporary)
            store.initialize(value)
            runner = ScriptedRunner(candidate=SHA_C)
            guard = rs.GuardedGit(
                store,
                activation_id="activation-0001",
                installed_digest=digest,
                skill_root=SKILL_ROOT,
                runner=runner,
            )
            guard.push_task_branch()
            self.assertIn(
                (["git", "push", "origin", "codex/issue-11"], "/repo-worktrees/issue-11"),
                runner.calls,
            )

    def test_guarded_push_rejects_cross_repository_worktree_before_push(self):
        with tempfile.TemporaryDirectory() as temporary:
            store, digest = self.guarded_state(temporary)

            class CrossRepositoryRunner(ScriptedRunner):
                def run(self, args, cwd=None):
                    args = list(args)
                    if str(cwd) == "/repo-worktrees/issue-11" and (
                        args[:4] == ["git", "remote", "get-url", "--all"]
                        or args[:5] == ["git", "remote", "get-url", "--push", "--all"]
                    ):
                        self.calls.append((args, str(cwd)))
                        return "https://github.com/other/project.git"
                    return super().run(args, cwd)

            runner = CrossRepositoryRunner()
            guard = rs.GuardedGit(
                store,
                activation_id="activation-0001",
                installed_digest=digest,
                skill_root=SKILL_ROOT,
                runner=runner,
            )
            with self.assertRaises((rs.ScopeError, rs.GuardError)):
                guard.push_task_branch()
            self.assertFalse(any(call[0][:2] == ["git", "push"] for call in runner.calls))

    def test_guarded_push_requires_completed_handoff_and_base_ancestry(self):
        with tempfile.TemporaryDirectory() as temporary:
            store, digest = self.guarded_state(temporary)
            active = store.load()
            active["task"]["active_role"] = "worker"
            store.save(active)
            active_runner = ScriptedRunner()
            active_guard = rs.GuardedGit(
                store,
                activation_id="activation-0001",
                installed_digest=digest,
                skill_root=SKILL_ROOT,
                runner=active_runner,
            )
            with self.assertRaises(rs.GuardError):
                active_guard.push_task_branch()
            self.assertFalse(any(call[0][:2] == ["git", "push"] for call in active_runner.calls))

        with tempfile.TemporaryDirectory() as temporary:
            store, digest = self.guarded_state(temporary)

            class UnrelatedCandidateRunner(ScriptedRunner):
                def run(self, args, cwd=None):
                    if list(args)[:3] == ["git", "merge-base", "--is-ancestor"]:
                        self.calls.append((list(args), str(cwd) if cwd else None))
                        raise rs.GuardError("candidate is unrelated to task base")
                    return super().run(args, cwd)

            runner = UnrelatedCandidateRunner()
            guard = rs.GuardedGit(
                store,
                activation_id="activation-0001",
                installed_digest=digest,
                skill_root=SKILL_ROOT,
                runner=runner,
            )
            with self.assertRaises(rs.GuardError):
                guard.push_task_branch()
            self.assertFalse(any(call[0][:2] == ["git", "push"] for call in runner.calls))

    def test_repository_identity_rejects_multiple_or_mismatched_origin_urls(self):
        class MultipleFetchRunner(ScriptedRunner):
            def run(self, args, cwd=None):
                if list(args)[:4] == ["git", "remote", "get-url", "--all"]:
                    return (
                        "https://github.com/owner/project.git\n"
                        "https://github.com/owner/mirror.git"
                    )
                return super().run(args, cwd)

        with self.assertRaises(rs.GuardError):
            rs.resolve_repository_identity("/repo", "main", runner=MultipleFetchRunner())

        class MismatchedPushRunner(ScriptedRunner):
            def run(self, args, cwd=None):
                if list(args)[:5] == ["git", "remote", "get-url", "--push", "--all"]:
                    return "https://github.com/other/project.git"
                return super().run(args, cwd)

        with self.assertRaises(rs.GuardError):
            rs.resolve_repository_identity("/repo", "main", runner=MismatchedPushRunner())

    def test_guard_rejects_wrong_activation(self):
        with tempfile.TemporaryDirectory() as temporary:
            store, digest = self.guarded_state(temporary)
            with self.assertRaises(rs.GuardError):
                rs.GuardedGit(
                    store,
                    activation_id="activation-wrong",
                    installed_digest=digest,
                    skill_root=SKILL_ROOT,
                    runner=ScriptedRunner(),
                )

    def test_guard_rejects_wrong_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            store, _ = self.guarded_state(temporary)
            with self.assertRaises(rs.GuardError):
                rs.GuardedGit(
                    store,
                    activation_id="activation-0001",
                    installed_digest="f" * 64,
                    skill_root=SKILL_ROOT,
                    runner=ScriptedRunner(),
                )

    def test_detached_sync_can_refresh_for_the_next_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            digest = rs.skill_content_digest(SKILL_ROOT)
            value = premerge_state()
            value["skill"]["content_digest"] = digest
            value["activation"]["scope_digest"] = rs.compute_scope_digest(
                value["activation"]["repository"],
                value["activation"]["base_branch"],
                value["activation"]["umbrella_issues"],
                value["activation"]["allowed_operations"],
                digest,
                owner_actor=value["activation"]["owner_actor"],
                capability_preflight=value["activation"]["capability_preflight"],
                orchestrator_creation_receipt=value["activation"]["orchestrator_creation_receipt"],
                role_model_snapshot=value["activation"]["role_model_snapshot"],
                role_model_snapshot_digest=value["activation"]["role_model_snapshot_digest"],
                review_policy_snapshot=value["activation"]["review_policy_snapshot"],
                review_policy_snapshot_digest=value["activation"]["review_policy_snapshot_digest"],
                legacy_unbounded_review=value["activation"]["legacy_unbounded_review"],
            )
            record_merge(value)
            record_close(value)
            value["task"]["cleanup"] = {key: True for key in rs.LOCAL_CLEANUP_KEYS}
            rs.transition_state(value, "sync-base")
            store = rs.StateStore(temporary)
            store.initialize(value)
            runner = DetachedRunner()
            first = rs.GuardedGit(
                store,
                activation_id="activation-0001",
                installed_digest=digest,
                skill_root=SKILL_ROOT,
                runner=runner,
            )
            first.sync_base()
            self.assertEqual(store.load()["phase"], "task-done")
            second = rs.GuardedGit(
                store,
                activation_id="activation-0001",
                installed_digest=digest,
                skill_root=SKILL_ROOT,
                runner=runner,
            )
            second.refresh_base()
            self.assertEqual(store.load()["activation"]["base_sha"], SHA_B)

    def test_effective_base_owner_uses_exact_porcelain_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            store, digest = self.guarded_state(temporary)

            class PrefixCollisionRunner(DetachedRunner):
                def run(self, args, cwd=None):
                    if list(args)[:3] == ["git", "worktree", "list"]:
                        self.calls.append((list(args), str(cwd) if cwd else None))
                        return "worktree /repo2\nbranch refs/heads/main-old"
                    return super().run(args, cwd)

            runner = PrefixCollisionRunner()
            runner.head = SHA_B
            guard = rs.GuardedGit(
                store,
                activation_id="activation-0001",
                installed_digest=digest,
                skill_root=SKILL_ROOT,
                runner=runner,
            )
            effective = rs.RepositoryIdentity(
                **{
                    **guard.identity.__dict__,
                    "head_sha": SHA_B,
                    "local_base_sha": SHA_A,
                    "remote_base_sha": SHA_B,
                }
            )
            with self.assertRaises(rs.GuardError):
                guard._assert_effective_base_identity(effective, Path("/repo"))

    def test_cleanup_fast_forwards_before_safe_no_upstream_branch_delete(self):
        with tempfile.TemporaryDirectory() as temporary:
            store, digest = self.cleanup_state(temporary)
            runner = CleanupRunner()
            guard = rs.GuardedGit(
                store,
                activation_id="activation-0001",
                installed_digest=digest,
                skill_root=SKILL_ROOT,
                runner=runner,
            )
            guard.remove_task_worktree()
            guard.delete_local_task_branch()
            commands = [call[0] for call in runner.calls]
            merge_index = commands.index(["git", "merge", "--ff-only", "origin/main"])
            delete_index = commands.index(["git", "branch", "-d", "codex/issue-11"])
            self.assertLess(merge_index, delete_index)

    def test_cleanup_rejects_clean_orchestration_commit_ahead_of_remote(self):
        with tempfile.TemporaryDirectory() as temporary:
            store, digest = self.cleanup_state(temporary)
            runner = CleanupRunner(root_head=SHA_D)
            guard = rs.GuardedGit(
                store,
                activation_id="activation-0001",
                installed_digest=digest,
                skill_root=SKILL_ROOT,
                runner=runner,
            )
            with self.assertRaises(rs.GuardError):
                guard.remove_task_worktree()
            self.assertFalse(any(call[0][:3] == ["git", "branch", "-d"] for call in runner.calls))

    def test_cleanup_rejects_worktree_switched_to_unrelated_branch(self):
        with tempfile.TemporaryDirectory() as temporary:
            store, digest = self.cleanup_state(temporary)

            class SwitchedBranchRunner(CleanupRunner):
                def run(self, args, cwd=None):
                    args = list(args)
                    location = str(cwd) if cwd else None
                    if args[:3] == ["git", "worktree", "list"]:
                        self.calls.append((args, location))
                        return (
                            "worktree /repo\nHEAD " + SHA_A + "\nbranch refs/heads/main\n\n"
                            "worktree /repo-worktrees/issue-11\nHEAD "
                            + SHA_B
                            + "\nbranch refs/heads/owner/unrelated"
                        )
                    if args[:3] == ["git", "branch", "--show-current"] and location == "/repo-worktrees/issue-11":
                        self.calls.append((args, location))
                        return "owner/unrelated"
                    return super().run(args, cwd)

            runner = SwitchedBranchRunner()
            guard = rs.GuardedGit(
                store,
                activation_id="activation-0001",
                installed_digest=digest,
                skill_root=SKILL_ROOT,
                runner=runner,
            )
            with self.assertRaisesRegex(rs.GuardError, "porcelain branch differs"):
                guard.remove_task_worktree()
            self.assertFalse(any(call[0][:3] == ["git", "worktree", "remove"] for call in runner.calls))


class StaticSkillTests(unittest.TestCase):
    def test_repository_layout_contract(self):
        expected = {
            ".github/workflows/ci.yml",
            ".gitignore",
            "AGENTS.md",
            "tests/test_orchestration_state.py",
        }
        actual = {
            path.relative_to(REPO_ROOT).as_posix()
            for path in REPO_ROOT.rglob("*")
            if path.is_file()
            and repository_path_is_outside_skill_tree(path)
            and ".git" not in path.relative_to(REPO_ROOT).parts
            and "__pycache__" not in path.parts
            and not path.name.endswith((".pyc", ".pyo"))
        }
        self.assertEqual(actual, expected)
        self.assertEqual(
            {path.name for path in (REPO_ROOT / "skills").iterdir()},
            {"roundlet"},
        )
        for old_payload_root in ("SKILL.md", "agents", "assets", "references", "scripts"):
            self.assertFalse((REPO_ROOT / old_payload_root).exists())

    def test_repository_layout_filter_includes_nested_noncanonical_skills_path(self):
        self.assertTrue(
            repository_path_is_outside_skill_tree(REPO_ROOT / "docs" / "skills" / "rogue.txt")
        )
        self.assertFalse(repository_path_is_outside_skill_tree(SKILL_ROOT / "SKILL.md"))

    def test_publishable_skill_contract(self):
        expected = {
            "SKILL.md",
            "agents/openai.yaml",
            "assets/roundlet.rules",
            "assets/roundlet-config.json",
            "references/operator-guide.md",
            "references/thread-prompts.md",
            "scripts/orchestration_state.py",
        }
        actual = {
            path.relative_to(SKILL_ROOT).as_posix()
            for path in SKILL_ROOT.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and not path.name.endswith((".pyc", ".pyo"))
        }
        self.assertEqual(actual, expected)
        for excluded in ("tests", "AGENTS.md", ".gitignore"):
            self.assertFalse((SKILL_ROOT / excluded).exists())

    def test_role_model_literals_exist_only_in_configuration(self):
        for path in SKILL_ROOT.rglob("*"):
            if (
                not path.is_file()
                or "__pycache__" in path.parts
                or path.suffix in {".pyc", ".pyo"}
                or path == SKILL_ROOT / "assets" / "roundlet-config.json"
            ):
                continue
            with self.subTest(path=path):
                self.assertNotIn("gpt-5", path.read_text(encoding="utf-8"))

    def test_skill_frontmatter_has_only_name_and_description(self):
        text = (SKILL_ROOT / "SKILL.md").read_text()
        match = rs.re.match(r"^---\n(.*?)\n---", text, rs.re.DOTALL)
        self.assertIsNotNone(match)
        keys = [
            line.split(":", 1)[0]
            for line in match.group(1).splitlines()
            if line and not line.startswith((" ", "\t"))
        ]
        self.assertEqual(keys, ["name", "description"])
        self.assertLess(len(text.splitlines()), 500)

    def test_openai_yaml_contract(self):
        text = (SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn('display_name: "Roundlet"', text)
        description = rs.re.search(r'short_description: "([^"]+)"', text).group(1)
        self.assertGreaterEqual(len(description), 25)
        self.assertLessEqual(len(description), 64)
        self.assertIn("$roundlet", text)
        self.assertIn('value: "github"', text)
        self.assertIn("allow_implicit_invocation: false", text)

    def test_gitignore_covers_runtime_and_test_artifacts(self):
        entries = set((REPO_ROOT / ".gitignore").read_text().splitlines())
        self.assertTrue({".codex-log/", ".pytest_cache/", "__pycache__/", "*.py[cod]"} <= entries)

    def test_no_extraneous_documents_or_icons(self):
        forbidden = {
            "README.md",
            "CHANGELOG.md",
            "INSTALLATION_GUIDE.md",
            "QUICK_REFERENCE.md",
        }
        self.assertFalse(any((REPO_ROOT / name).exists() for name in forbidden))
        self.assertFalse(any(path.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".ico"} for path in REPO_ROOT.rglob("*")))

    def test_agents_policy_stays_source_repository_only(self):
        text = (REPO_ROOT / "AGENTS.md").read_text().casefold()
        for runtime_protocol in (
            "github connector",
            ".codex-log/roundlet",
            "activation id",
            "mailbox",
            "target repository",
        ):
            self.assertNotIn(runtime_protocol, text)

    def test_agents_policy_uses_publishable_skill_root(self):
        text = (REPO_ROOT / "AGENTS.md").read_text()
        self.assertIn("`skills/roundlet` as the canonical skill source root", text)
        self.assertIn("`skill-creator/scripts/quick_validate.py` against `skills/roundlet`", text)

    def test_runtime_has_no_prohibited_dependency_markers(self):
        text = (SKILL_ROOT / "scripts/orchestration_state.py").read_text().casefold()
        for marker in (
            "loop-orchestrator",
            "copilot",
            ".agent-runs",
            "sqlite",
            "agent_loop_",
            "copilot_",
        ):
            self.assertNotIn(marker, text)

    def test_worker_prompt_returns_handoff_and_root_owns_mailbox(self):
        prompts = (SKILL_ROOT / "references/thread-prompts.md").read_text()
        skill = (SKILL_ROOT / "SKILL.md").read_text()
        self.assertIn("Do not write a mailbox file", prompts)
        self.assertIn("root Orchestrator validates that response", skill)

    def test_converging_prior_findings_contract_is_consistent(self):
        prompts = (SKILL_ROOT / "references/thread-prompts.md").read_text()
        skill = (SKILL_ROOT / "SKILL.md").read_text()
        for text in (prompts, skill):
            self.assertIn("bounded earlier finding/repair summaries", text)
            self.assertIn("independent recheck targets", text)
            self.assertIn("authority or proof", text)

    def test_skill_internal_links_resolve_within_publishable_root(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text()
        local_targets = {
            target
            for target in rs.re.findall(r"\]\(([^)]+)\)", skill)
            if "://" not in target and not target.startswith("#")
        }
        self.assertTrue(
            {
                "references/operator-guide.md",
                "references/thread-prompts.md",
                "assets/roundlet.rules",
                "scripts/orchestration_state.py",
            }
            <= local_targets
        )
        for target in local_targets:
            with self.subTest(target=target):
                self.assertEqual(
                    resolve_skill_link_target(target),
                    (SKILL_ROOT / target).resolve(),
                )

    def test_skill_internal_links_reject_path_traversal(self):
        with self.assertRaisesRegex(ValueError, "escapes publishable root"):
            resolve_skill_link_target("../../AGENTS.md")

    def test_operator_installed_paths_and_source_path_contract(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text()
        guide = (SKILL_ROOT / "references/operator-guide.md").read_text()
        self.assertIn("<installed-roundlet>/scripts/orchestration_state.py", guide)
        self.assertIn("--skill-root <installed-roundlet>", guide)
        source_path = f"`{rs.DOCUMENTATION_ONLY_OPERATOR_GUIDE_PATH}`"
        self.assertIn(source_path, skill)
        self.assertIn(source_path, guide)

    def test_rules_do_not_allow_broad_git_or_interpreter_prefixes(self):
        text = (SKILL_ROOT / "assets/roundlet.rules").read_text()
        self.assertNotIn('pattern = ["git", "push"]', text)
        self.assertNotIn('pattern = ["<PYTHON>"]', text)
        self.assertNotIn('decision = "allow"\n    justification = "Force', text)
        for placeholder in (
            "<TARGET_ROOT>",
            "<BASE_BRANCH>",
            "<PYTHON>",
            "<ROUNDLET_SCRIPT>",
            "<STATE_DIR>",
            "<ACTIVATION_ID>",
            "<INSTALLED_DIGEST>",
            "<SKILL_ROOT>",
        ):
            self.assertIn(placeholder, text)

    def test_guarded_rule_prefix_cannot_override_exact_cli_identity(self):
        codex = shutil.which("codex")
        if codex is None:
            self.skipTest("codex CLI is unavailable for execpolicy regression")
        template_values = {
            "--state-dir": "<STATE_DIR>",
            "--activation-id": "<ACTIVATION_ID>",
            "--installed-digest": "<INSTALLED_DIGEST>",
            "--skill-root": "<SKILL_ROOT>",
        }
        runtime_values = {
            "--state-dir": "/tmp/roundlet-state",
            "--activation-id": "activation-0001",
            "--installed-digest": "a" * 64,
            "--skill-root": str(SKILL_ROOT),
        }
        for command in rs.GUARDED_CLI_COMMANDS:
            template = ["<PYTHON>", "<ROUNDLET_SCRIPT>", command]
            runtime = [sys.executable, str(SKILL_ROOT / "scripts/orchestration_state.py"), command]
            for option in rs.GUARDED_CLI_OPTIONS:
                template.extend([option, template_values[option]])
                runtime.extend([option, runtime_values[option]])
            rs.validate_guarded_cli_shape(runtime[2:])
            for option in rs.GUARDED_CLI_OPTIONS:
                with self.subTest(command=command, repeated=option):
                    policy = subprocess.run(
                        [
                            codex,
                            "execpolicy",
                            "check",
                            "--rules",
                            str(SKILL_ROOT / "assets/roundlet.rules"),
                            *template,
                            option,
                            "<OVERRIDE>",
                        ],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    self.assertEqual(json.loads(policy.stdout)["decision"], "allow")
                    blocked = subprocess.run(
                        [*runtime, option, "override"],
                        check=False,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    self.assertEqual(blocked.returncode, 2)
                    self.assertIn("exact immutable argument order", blocked.stderr)


if __name__ == "__main__":
    unittest.main()
