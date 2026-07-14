from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))

import orchestration_state as rs


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40
DIGEST = "d" * 64


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
        now="2026-07-14T00:00:00Z",
    )


def set_selection(value, *, umbrella=10, issue=11, base=SHA_A):
    value["selection"] = {
        "status": "selected",
        "activation_id": value["activation"]["id"],
        "selected_umbrella": umbrella,
        "selected_issue": issue,
        "base_sha": base,
    }


def assigned_state(*, umbrellas=None):
    value = state(umbrellas=umbrellas)
    rs.transition_state(value, "selecting-task")
    set_selection(value, umbrella=(umbrellas or [10])[0])
    rs.assign_task(
        value,
        umbrella_issue=(umbrellas or [10])[0],
        issue=11,
        branch="codex/issue-11",
        worktree="/repo-worktrees/issue-11",
        worker_thread_id="worker-11",
        base_sha=SHA_A,
    )
    return value


def pass_identity_for(value, candidate=SHA_B):
    if not value["review"]["supervisor_thread_ids"]:
        value["review"]["round"] = 1
        value["review"]["supervisor_thread_ids"] = ["supervisor-pass"]
        value["review"]["unarchived_supervisor_thread_ids"] = ["supervisor-pass"]
        value["review"]["last_supervisor_created_at"] = "2026-07-14T00:00:00Z"
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
            "thread_id": thread_id,
            "generation": generation,
            "created": True,
            "created_at": f"2026-07-14T00:00:00.{generation:06d}Z",
        },
    )


def premerge_state():
    value = assigned_state()
    rs.set_candidate(value, SHA_B, clean=True)
    rs.record_draft_pr(
        value,
        repository="owner/project",
        repository_id=123,
        issue=11,
        pr_number=22,
        pr_url="https://github.com/owner/project/pull/22",
        pr_state="open",
        draft=True,
        base_sha=SHA_A,
        head_sha=SHA_B,
        branch="codex/issue-11",
    )
    begin_review(value, "supervisor-initial")
    rs.accept_supervisor_result(
        value,
        thread_id="supervisor-initial",
        candidate_sha=SHA_B,
        result="PASS",
    )
    rs.record_supervisor_archived(value, supervisor_thread_id="supervisor-initial")
    rs.set_candidate(value, SHA_B, clean=True)
    rs.record_pr_ready(
        value,
        repository="owner/project",
        repository_id=123,
        pr_number=22,
        head_sha=SHA_B,
    )
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
        value["selection"] = {"source_body_digest": "changed"}
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
                base_sha=SHA_B,
            )

    def test_candidate_requires_clean_worktree(self):
        with self.assertRaises(rs.GuardError):
            rs.set_candidate(assigned_state(), SHA_B, clean=False)

    def test_draft_pr_receipt_binds_exact_task(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        rs.record_draft_pr(
            value,
            repository="owner/project",
            repository_id=123,
            issue=11,
            pr_number=22,
            pr_url="https://github.com/owner/project/pull/22",
            pr_state="open",
            draft=True,
            base_sha=SHA_A,
            head_sha=SHA_B,
            branch="codex/issue-11",
        )
        self.assertEqual(value["phase"], "draft-pr")
        self.assertEqual(value["task"]["pr_number"], 22)

    def test_draft_pr_receipt_requires_live_open_draft_readback(self):
        for pr_state, draft in (("closed", True), ("open", False)):
            with self.subTest(pr_state=pr_state, draft=draft):
                value = assigned_state()
                rs.set_candidate(value, SHA_B, clean=True)
                with self.assertRaises(rs.GuardError):
                    rs.record_draft_pr(
                        value,
                        repository="owner/project",
                        repository_id=123,
                        issue=11,
                        pr_number=22,
                        pr_url="https://github.com/owner/project/pull/22",
                        pr_state=pr_state,
                        draft=draft,
                        base_sha=SHA_A,
                        head_sha=SHA_B,
                        branch="codex/issue-11",
                    )
                self.assertEqual(value["phase"], "worker-running")
                self.assertIsNone(value["task"]["draft_pr_receipt"])

    def test_draft_pr_rejects_wrong_repository(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        with self.assertRaises(rs.ScopeError):
            rs.record_draft_pr(
                value,
                repository="other/project",
                repository_id=123,
                issue=11,
                pr_number=22,
                pr_url="https://github.com/other/project/pull/22",
                pr_state="open",
                draft=True,
                base_sha=SHA_A,
                head_sha=SHA_B,
                branch="codex/issue-11",
            )

    def test_merge_then_exact_issue_close_receipts(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        rs.record_draft_pr(
            value,
            repository="owner/project",
            repository_id=123,
            issue=11,
            pr_number=22,
            pr_url="https://github.com/owner/project/pull/22",
            pr_state="open",
            draft=True,
            base_sha=SHA_A,
            head_sha=SHA_B,
            branch="codex/issue-11",
        )
        value["phase"] = "merging"
        rs.record_merge_receipt(
            value,
            repository="owner/project",
            repository_id=123,
            pr_number=22,
            expected_head_sha=SHA_B,
            merge_sha=SHA_C,
            merge_method="merge",
        )
        self.assertEqual(value["phase"], "closing-issue")
        rs.record_issue_close_receipt(
            value,
            repository="owner/project",
            repository_id=123,
            issue=11,
            state_reason="completed",
        )
        self.assertEqual(value["phase"], "cleanup")
        self.assertEqual(value["task"]["issue_close_receipt"]["issue"], 11)

    def test_issue_close_rejects_unselected_issue(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        value["task"]["pr_number"] = 22
        value["task"]["merge_receipt"] = {"merge_sha": SHA_C}
        value["phase"] = "closing-issue"
        with self.assertRaises(rs.ScopeError):
            rs.record_issue_close_receipt(
                value,
                repository="owner/project",
                repository_id=123,
                issue=12,
                state_reason="completed",
            )

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

    def test_review_history_stays_bounded_across_two_hundred_fresh_rounds(self):
        value = assigned_state()
        rs.set_candidate(value, SHA_B, clean=True)
        value["task"]["pr_number"] = 22
        value["phase"] = "draft-pr"
        for review_round in range(1, 201):
            thread_id = f"supervisor-{review_round}"
            begin_review(value, thread_id)
            rs.accept_supervisor_result(
                value,
                thread_id=thread_id,
                candidate_sha=SHA_B,
                result="FINDINGS",
            )
            rs.record_supervisor_archived(value, supervisor_thread_id=thread_id)
            rs.set_candidate(value, SHA_B, clean=True)
        rs.validate_state(value)
        self.assertEqual(value["review"]["round"], 200)
        self.assertEqual(value["review"]["archived_supervisor_count"], 200)
        self.assertLessEqual(len(value["review"]["supervisor_thread_ids"]), 64)
        self.assertEqual(value["review"]["unarchived_supervisor_thread_ids"], [])
        self.assertLess(len(rs.canonical_json(value).encode("utf-8")), rs.MAX_STATE_BYTES)

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
                "thread_id": "supervisor-whole",
                "generation": 1,
                "created": True,
                "created_at": "2026-07-14T00:00:00Z",
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
                "thread_id": "supervisor-fractional",
                "generation": 2,
                "created": True,
                "created_at": "2026-07-14T00:00:00.1Z",
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
        live = {
            "scope_valid": True,
            "membership_valid": True,
            "worker_ready_to_merge": True,
            "worktree_clean": True,
            "tests_passed": True,
            "checks_passed": True,
            "pr_ready": True,
            "mergeable": True,
            "no_conflict": True,
            "no_new_blocker": True,
            "no_maintenance_request": True,
            "head_sha": SHA_B,
            "repository": "owner/project",
            "repository_id": 123,
            "issue": 11,
            "pr_number": 22,
            "pr_url": "https://github.com/owner/project/pull/22",
            "base_sha": SHA_A,
            "base_branch": "main",
            "branch": "codex/issue-11",
            "merge_method": "merge",
        }
        self.assertEqual(rs.verify_premerge_gates(value, live), [])
        live["checks_passed"] = False
        self.assertIn("required GitHub checks are not passing", rs.verify_premerge_gates(value, live))

    def test_premerge_rejects_durable_maintenance_and_missing_repository_id(self):
        value = premerge_state()
        live = {
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
            "head_sha": SHA_B,
            "repository": "owner/project",
            "repository_id": None,
            "issue": 11,
            "pr_number": 22,
            "pr_url": "https://github.com/owner/project/pull/22",
            "base_sha": SHA_A,
            "base_branch": "main",
            "branch": "codex/issue-11",
            "merge_method": "merge",
        }
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
            )

    def _paused(self):
        value = assigned_state()
        value["task"]["active_role"] = None
        rs.request_maintenance(value, "upgrade")
        rs.create_maintenance_checkpoint(
            value,
            checkpoint_id="checkpoint-001",
            schedule_id="schedule-1",
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
            changed_paths=["references/operator-guide.md"],
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
        migrated = rs.migrate_state_document(old)
        self.assertEqual(migrated["versions"]["schema"], 2)
        self.assertEqual(migrated["completed_tasks"], [])
        self.assertEqual(migrated["skill"]["source_repository"], "ythdelmar68/roundlet")

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
            rs.migrate_state_document(old)

    def test_paused_schema_migration_can_resume_and_failure_is_atomic(self):
        with tempfile.TemporaryDirectory() as temporary:
            paused = self._paused()
            paused["versions"]["schema"] = 1
            paused["maintenance"]["stored_versions"]["schema"] = 1
            paused["maintenance"].pop("migrated_from_versions", None)
            paused["maintenance"].pop("migration_receipt", None)
            store = rs.StateStore(temporary)
            rs.atomic_write_json(store.path, paused)
            migrated = store.migrate()
            self.assertEqual(migrated["maintenance"]["stored_versions"]["schema"], 2)
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
            paused["versions"]["schema"] = 1
            paused["maintenance"]["stored_versions"]["schema"] = 99
            store = rs.StateStore(temporary)
            rs.atomic_write_json(store.path, paused)
            before = store.path.read_bytes()
            with self.assertRaises(rs.MigrationError):
                store.migrate()
            self.assertEqual(store.path.read_bytes(), before)

    def test_unknown_migration_fails(self):
        value = state()
        value["versions"]["schema"] = 99
        with self.assertRaises(rs.MigrationError):
            rs.migrate_state_document(value)


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
                rs.Comment("owner", "Please include #13 as a sub-issue"),
                rs.Comment("stranger", "Please include #14 as a sub-issue"),
            ],
            owner_login="owner",
            current_repository="owner/project",
        )
        self.assertEqual(set(membership), {11, 12, 13})
        self.assertEqual(membership[11], ["formal-sub-issue"])
        self.assertNotIn(14, membership)

    def test_body_reference_outside_trusted_sections_does_not_expand(self):
        membership = rs.discover_membership(
            umbrella_issue=10,
            formal_subissues=[],
            umbrella_body="## Notes\nMaybe see #99",
            comments=[],
            owner_login="owner",
            current_repository="owner/project",
        )
        self.assertEqual(membership, {})

    def test_explicit_top_level_list_is_membership_but_prose_is_not(self):
        membership = rs.discover_membership(
            umbrella_issue=10,
            formal_subissues=[],
            umbrella_body="- [ ] #11\n- Maybe see #99\n1. owner/project#12",
            comments=[],
            owner_login="owner",
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
            owner_login="owner",
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
            owner_login="owner",
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
                rs.Comment("owner", "Do not include #98"),
                rs.Comment("owner", "For context, see #99"),
            ],
            owner_login="owner",
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
                owner_login="owner",
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
    return rs.IssueSnapshot(
        issue=issue,
        umbrella=umbrella,
        repository=repository,
        open=open,
        completion_verified=completed,
        dependencies=tuple(deps),
        external_blockers=tuple(external),
        membership_sources=("formal-sub-issue",),
        required_order_index=order,
        ambiguous_active_implementation=ambiguous,
        owner_priority=priority,
        unlocks=unlocks,
        overlap_risk=risk,
        revision=f"r{issue}",
    )


class SelectionTests(unittest.TestCase):
    def receipt(self, snapshots, umbrellas=None):
        value = state(umbrellas=umbrellas)
        return rs.select_next_task(value, snapshots, refresh_timestamp="2026-07-14T01:00:00Z")

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


class PersistenceAndMailboxTests(unittest.TestCase):
    def test_atomic_state_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = rs.StateStore(temporary)
            store.initialize(state())
            self.assertEqual(store.load()["activation"]["id"], "activation-0001")

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
            rs.transition_state(completed, "selecting-task")
            rs.transition_state(completed, "scope-complete")
            completed["maintenance"]["schedule_id"] = "schedule-1"
            store = rs.StateStore(temporary)
            store.initialize(completed)
            replacement = rs.new_state(
                activation_request(),
                identity(),
                activation_id="activation-0002",
                orchestrator_thread_id="orchestrator-1",
                installed_roundlet_digest=DIGEST,
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
        rs.record_draft_pr(
            value,
            repository="owner/project",
            repository_id=123,
            issue=11,
            pr_number=22,
            pr_url="https://github.com/owner/project/pull/22",
            pr_state="open",
            draft=True,
            base_sha=SHA_A,
            head_sha=SHA_B,
            branch="codex/issue-11",
        )
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
            value["selection"] = rs.select_next_task(
                value,
                [
                    rs.IssueSnapshot(
                        issue=11,
                        umbrella=10,
                        repository="owner/project",
                        membership_sources=("formal-sub-issue",),
                    )
                ],
                refresh_timestamp="2026-07-14T01:00:00Z",
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
                },
                advance=lambda current, item, result: rs.assign_task(
                    current,
                    umbrella_issue=10,
                    issue=11,
                    branch=result["branch"],
                    worktree=result["worktree"],
                    worker_thread_id=result["worker_thread_id"],
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
            value["selection"] = rs.select_next_task(
                value,
                [
                    rs.IssueSnapshot(
                        issue=11,
                        umbrella=10,
                        repository="owner/project",
                        membership_sources=("formal-sub-issue",),
                    )
                ],
                refresh_timestamp="2026-07-14T01:00:00Z",
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


class CompactionTests(unittest.TestCase):
    def test_task_compaction_is_bounded(self):
        value = assigned_state()
        value["phase"] = "task-done"
        value["task"]["merge_sha"] = SHA_C
        value["review"]["round"] = 4
        rs.compact_completed_task(
            value,
            issue_url="https://github.com/owner/project/issues/11",
            pr_url="https://github.com/owner/project/pull/22",
            merge_sha=SHA_C,
            completed_at="2026-07-14T03:00:00Z",
        )
        self.assertIsNone(value["task"])
        self.assertEqual(value["completed_tasks"][0]["review_rounds"], 4)
        self.assertNotIn("changed_files", value["completed_tasks"][0])

    def test_scope_compaction_writes_one_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = state()
            value["phase"] = "scope-complete"
            summary = rs.compact_scope(value, temporary, completed_at="2026-07-14T04:00:00Z")
            self.assertEqual(summary["final_result"], "scope-complete")
            files = sorted(path.name for path in Path(temporary).iterdir())
            self.assertEqual(files, ["last-scope-summary.json", "state.json"])

    def test_skill_digest_is_stable(self):
        first = rs.skill_content_digest(ROOT)
        second = rs.skill_content_digest(ROOT)
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{64}$")


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
        digest = rs.skill_content_digest(ROOT)
        value = premerge_state()
        value["skill"]["content_digest"] = digest
        value["activation"]["scope_digest"] = rs.compute_scope_digest(
            value["activation"]["repository"],
            value["activation"]["base_branch"],
            value["activation"]["umbrella_issues"],
            value["activation"]["allowed_operations"],
            digest,
        )
        rs.transition_state(value, "merging")
        rs.record_merge_receipt(
            value,
            repository="owner/project",
            repository_id=123,
            pr_number=22,
            expected_head_sha=SHA_B,
            merge_sha=SHA_C,
            merge_method="merge",
        )
        rs.record_issue_close_receipt(
            value,
            repository="owner/project",
            repository_id=123,
            issue=11,
            state_reason="completed",
        )
        rs.record_children_archived(
            value,
            worker_thread_id="worker-11",
            supervisor_thread_ids=[],
        )
        store = rs.StateStore(directory)
        store.initialize(value)
        return store, digest

    def guarded_state(self, directory):
        digest = rs.skill_content_digest(ROOT)
        value = rs.new_state(
            activation_request(),
            identity(),
            activation_id="activation-0001",
            orchestrator_thread_id="orchestrator-1",
            installed_roundlet_digest=digest,
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
                skill_root=ROOT,
                runner=runner,
            )
            guard.push_task_branch()
            commands = [call[0] for call in runner.calls]
            self.assertIn(["git", "push", "origin", "codex/issue-11"], commands)
            self.assertFalse(any("--force" in command for command in commands))

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
                skill_root=ROOT,
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
                skill_root=ROOT,
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
                skill_root=ROOT,
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
                    skill_root=ROOT,
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
                    skill_root=ROOT,
                    runner=ScriptedRunner(),
                )

    def test_detached_sync_can_refresh_for_the_next_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            digest = rs.skill_content_digest(ROOT)
            value = premerge_state()
            value["skill"]["content_digest"] = digest
            value["activation"]["scope_digest"] = rs.compute_scope_digest(
                value["activation"]["repository"],
                value["activation"]["base_branch"],
                value["activation"]["umbrella_issues"],
                value["activation"]["allowed_operations"],
                digest,
            )
            rs.transition_state(value, "merging")
            rs.record_merge_receipt(
                value,
                repository="owner/project",
                repository_id=123,
                pr_number=22,
                expected_head_sha=SHA_B,
                merge_sha=SHA_C,
                merge_method="merge",
            )
            rs.record_issue_close_receipt(
                value,
                repository="owner/project",
                repository_id=123,
                issue=11,
                state_reason="completed",
            )
            value["task"]["cleanup"] = {key: True for key in rs.LOCAL_CLEANUP_KEYS}
            rs.transition_state(value, "sync-base")
            store = rs.StateStore(temporary)
            store.initialize(value)
            runner = DetachedRunner()
            first = rs.GuardedGit(
                store,
                activation_id="activation-0001",
                installed_digest=digest,
                skill_root=ROOT,
                runner=runner,
            )
            first.sync_base()
            self.assertEqual(store.load()["phase"], "task-done")
            second = rs.GuardedGit(
                store,
                activation_id="activation-0001",
                installed_digest=digest,
                skill_root=ROOT,
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
                skill_root=ROOT,
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
                skill_root=ROOT,
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
                skill_root=ROOT,
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
                skill_root=ROOT,
                runner=runner,
            )
            with self.assertRaisesRegex(rs.GuardError, "porcelain branch differs"):
                guard.remove_task_worktree()
            self.assertFalse(any(call[0][:3] == ["git", "worktree", "remove"] for call in runner.calls))


class StaticSkillTests(unittest.TestCase):
    def test_canonical_skeleton(self):
        expected = {
            ".gitignore",
            "AGENTS.md",
            "SKILL.md",
            "agents/openai.yaml",
            "assets/roundlet.rules",
            "references/operator-guide.md",
            "references/thread-prompts.md",
            "scripts/orchestration_state.py",
            "tests/test_orchestration_state.py",
        }
        actual = {
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("*")
            if path.is_file()
            and ".git" not in path.relative_to(ROOT).parts
            and "__pycache__" not in path.parts
            and not path.name.endswith(".pyc")
        }
        self.assertEqual(actual, expected)

    def test_skill_frontmatter_has_only_name_and_description(self):
        text = (ROOT / "SKILL.md").read_text()
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
        text = (ROOT / "agents/openai.yaml").read_text()
        self.assertIn('display_name: "Roundlet"', text)
        description = rs.re.search(r'short_description: "([^"]+)"', text).group(1)
        self.assertGreaterEqual(len(description), 25)
        self.assertLessEqual(len(description), 64)
        self.assertIn("$roundlet", text)
        self.assertIn('value: "github"', text)
        self.assertIn("allow_implicit_invocation: false", text)

    def test_gitignore_covers_runtime_and_test_artifacts(self):
        entries = set((ROOT / ".gitignore").read_text().splitlines())
        self.assertTrue({".codex-log/", ".pytest_cache/", "__pycache__/", "*.py[cod]"} <= entries)

    def test_no_extraneous_documents_or_icons(self):
        forbidden = {
            "README.md",
            "CHANGELOG.md",
            "INSTALLATION_GUIDE.md",
            "QUICK_REFERENCE.md",
        }
        self.assertFalse(any((ROOT / name).exists() for name in forbidden))
        self.assertFalse(any(path.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".ico"} for path in ROOT.rglob("*")))

    def test_agents_policy_stays_source_repository_only(self):
        text = (ROOT / "AGENTS.md").read_text().casefold()
        for runtime_protocol in (
            "github connector",
            ".codex-log/roundlet",
            "activation id",
            "mailbox",
            "target repository",
        ):
            self.assertNotIn(runtime_protocol, text)

    def test_runtime_has_no_prohibited_dependency_markers(self):
        text = (ROOT / "scripts/orchestration_state.py").read_text().casefold()
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
        prompts = (ROOT / "references/thread-prompts.md").read_text()
        skill = (ROOT / "SKILL.md").read_text()
        self.assertIn("Do not write a mailbox file", prompts)
        self.assertIn("root Orchestrator validates that response", skill)

    def test_rules_do_not_allow_broad_git_or_interpreter_prefixes(self):
        text = (ROOT / "assets/roundlet.rules").read_text()
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
            "--skill-root": str(ROOT),
        }
        for command in rs.GUARDED_CLI_COMMANDS:
            template = ["<PYTHON>", "<ROUNDLET_SCRIPT>", command]
            runtime = [sys.executable, str(ROOT / "scripts/orchestration_state.py"), command]
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
                            str(ROOT / "assets/roundlet.rules"),
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
