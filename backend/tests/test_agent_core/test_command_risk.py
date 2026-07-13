from __future__ import annotations

from types import MappingProxyType, SimpleNamespace

import pytest

from app.services.agent_core.permissions.command_risk import (
    CommandRiskAssessment,
    CommandTargetProfile,
    assess_command_risk,
    command_target_profile_from_context,
)
from app.services.agent_core.permissions.policy import PermissionPolicy


LOCAL_SANDBOXED = CommandTargetProfile(
    kind="local",
    trust_domain="developer-machine",
    identity="local-user",
    sandbox_strength="enforced",
    read_roots=("/workspace",),
    write_roots=("/workspace",),
    working_directory="/workspace",
    network_allowed=False,
)
LOCAL_UNSANDBOXED = CommandTargetProfile(
    kind="local",
    trust_domain="developer-machine",
    identity="local-user",
    sandbox_strength="none",
    read_roots=("/workspace",),
    write_roots=("/workspace",),
    working_directory="/workspace",
    network_allowed=True,
)
REMOTE = CommandTargetProfile(
    kind="remote_ssh",
    trust_domain="cluster.example.org",
    identity="alice",
    sandbox_strength="none",
    read_roots=("/analysis/project",),
    write_roots=("/analysis/project",),
    working_directory="/analysis/project",
    network_allowed=True,
    connection_id="conn-a",
)


@pytest.mark.parametrize(
    "target,command,expected",
    [
        (LOCAL_SANDBOXED, "cat README.md", "act_low"),
        (LOCAL_SANDBOXED, "cat /etc/passwd", "act_high"),
        (LOCAL_UNSANDBOXED, "hostname", "act_low"),
        (REMOTE, "hostname", "act_low"),
        (REMOTE, "df -h", "act_low"),
        (REMOTE, "phoenixcli --profile sz01 pipeline list --output json", "act_low"),
        (REMOTE, "cat /analysis/project/input/sequence.list", "act_low"),
        (REMOTE, "cat /etc/passwd", "act_high"),
        (REMOTE, "cat $HOME/.ssh/config", "act_high"),
        (REMOTE, "touch output.txt", "act_high"),
        (REMOTE, "curl https://example.org", "external"),
        (REMOTE, "rm -rf output", "destructive"),
    ],
)
def test_target_aware_command_matrix(target, command, expected):
    assert assess_command_risk(command, target=target).level == expected


@pytest.mark.parametrize(
    "command,expected_paths",
    [
        (
            "grep -n leaf /analysis/project/input/sequence.list",
            ["/analysis/project/input/sequence.list"],
        ),
        (
            "wc -l /analysis/project/input/sequence.list",
            ["/analysis/project/input/sequence.list"],
        ),
        (
            "sort /analysis/project/input/sequence.list",
            ["/analysis/project/input/sequence.list"],
        ),
        (
            "diff /analysis/project/a.txt /analysis/project/b.txt",
            ["/analysis/project/a.txt", "/analysis/project/b.txt"],
        ),
        ("jq '.sample' /analysis/project/data.json", ["/analysis/project/data.json"]),
    ],
)
def test_remote_raw_read_extracts_common_file_operands(command, expected_paths):
    assessment = assess_command_risk(command, target=REMOTE)

    assert assessment.level == "act_low"
    assert assessment.referenced_paths == expected_paths


@pytest.mark.parametrize(
    "command",
    [
        "grep leaf /etc/passwd",
        "wc -l /etc/passwd",
        "sort /etc/passwd",
        "diff /analysis/project/a.txt /etc/passwd",
        "jq '.user' /etc/passwd",
        "grep --files-from=/etc/passwd leaf",
        "sort --random-source=/etc/passwd /analysis/project/input.txt",
        "grep --unknown-path-option /analysis/project/input.txt",
    ],
)
def test_remote_raw_read_outside_or_ambiguous_paths_fail_closed(command):
    assessment = assess_command_risk(command, target=REMOTE)

    assert assessment.level == "act_high"
    assert any(
        marker in " ".join(assessment.reasons)
        for marker in ("outside", "cannot be proven", "option")
    )


@pytest.mark.parametrize(
    "command",
    [
        "dangercli pipeline list",
        "mycli status",
        "phoenixcli arbitrary list",
        "phoenixcli pipeline list delete",
        "phoenixcli pipeline submit",
    ],
)
def test_unknown_or_ambiguous_cli_commands_are_not_auto_run(command):
    assert assess_command_risk(command, target=REMOTE).level == "act_high"


@pytest.mark.parametrize(
    "command",
    [
        "phoenixcli pipeline list",
        "phoenixcli --no-interactive --profile sz01 pipeline list --output json",
        "squeue -u alice",
        "module avail nextflow",
        "nextflow -version",
    ],
)
def test_known_remote_diagnostic_grammar_is_auto_runnable(command):
    assert assess_command_risk(command, target=REMOTE).level == "act_low"


def test_assessment_records_semantics_and_canonical_boundary():
    assessment = assess_command_risk(
        "cat /analysis/project/input/sequence.list | head -20",
        target=REMOTE,
        requested_connection_id="conn-a",
    )

    assert isinstance(assessment, CommandRiskAssessment)
    assert assessment.effects == ["read"]
    assert assessment.confidence == "medium"
    assert assessment.referenced_paths == ["/analysis/project/input/sequence.list"]
    assert assessment.protected_resources == []
    assert assessment.target["kind"] == "remote_ssh"
    assert assessment.target["connection_id"] == "conn-a"
    assert assessment.boundary == {
        "enforced": False,
        "sandbox_strength": "none",
        "working_directory": "/analysis/project",
    }
    assert any("remote SSH account" in reason for reason in assessment.reasons)


@pytest.mark.parametrize(
    "command,kind",
    [
        ("echo token > ~/.ssh/authorized_keys", "ssh"),
        ("sed -i s/old/new/ /etc/sudoers", "sudoers"),
        ("printf x > ~/.bashrc", "shell_startup"),
        ("rm -f /workspace/AGENTS.md", "agent_policy"),
        ("printf x > /workspace/.env", "credential"),
    ],
)
def test_protected_resource_writes_always_require_explicit_approval(command, kind):
    assessment = assess_command_risk(command, target=LOCAL_UNSANDBOXED)

    assert assessment.requires_explicit_approval is True
    assert {item["kind"] for item in assessment.protected_resources} == {kind}
    assert (
        PermissionPolicy()
        .decide(
            risk=assessment,
            permission_mode="bypass",
            automation_mode="autonomous",
        )
        .decision
        == "ask"
    )


def test_in_place_editor_does_not_treat_program_as_a_path():
    assessment = assess_command_risk(
        "sed -i 's/old/new/' /etc/sudoers",
        target=LOCAL_UNSANDBOXED,
    )

    assert assessment.referenced_paths == ["/etc/sudoers"]


def test_connection_mismatch_is_hard_blocked_in_every_mode():
    assessment = assess_command_risk(
        "hostname",
        target=REMOTE,
        requested_connection_id="conn-b",
    )

    assert assessment.hard_blocked is True
    assert any("connection" in reason for reason in assessment.reasons)
    policy = PermissionPolicy()
    for mode in ("ask_each_action", "guarded_auto", "bypass"):
        assert (
            policy.decide(
                risk=assessment,
                permission_mode=mode,
                automation_mode="autonomous",
            ).decision
            == "deny"
        )


def test_nested_destructive_sink_is_denied_even_in_bypass():
    assessment = assess_command_risk(
        "find / -exec rm -rf {} +",
        target=LOCAL_UNSANDBOXED,
    )

    assert assessment.hard_blocked is True
    assert assessment.confidence == "high"
    assert (
        PermissionPolicy()
        .decide(
            risk=assessment,
            permission_mode="bypass",
            automation_mode="autonomous",
        )
        .decision
        == "deny"
    )


@pytest.mark.parametrize(
    "command",
    [
        "tee /dev/md0 < disk.img",
        "cp disk.img /dev/dm-0",
        "dd if=disk.img of=/dev/loop0",
        "mkfs.ext4 /dev/zram0",
        "install disk.img /dev/rdisk0",
    ],
)
def test_extended_block_device_sinks_are_denied_in_bypass(command):
    assessment = assess_command_risk(command, target=LOCAL_UNSANDBOXED)

    assert assessment.hard_blocked is True
    assert (
        PermissionPolicy()
        .decide(
            risk=assessment,
            permission_mode="bypass",
            automation_mode="autonomous",
        )
        .decision
        == "deny"
    )


def test_command_risk_audit_snapshot_is_bounded_and_structured():
    assessment = assess_command_risk(
        "cat /analysis/project/input/sequence.list",
        target=REMOTE,
    )

    assert assessment.audit_snapshot() == {
        "level": "act_low",
        "effects": ["read"],
        "confidence": "medium",
        "reasons": assessment.reasons,
        "referenced_paths": ["/analysis/project/input/sequence.list"],
        "protected_resources": [],
        "target": assessment.target,
        "boundary": assessment.boundary,
        "hard_blocked": False,
        "requires_explicit_approval": False,
    }
    assert len(assessment.assessment_fingerprint()) == 64
    assert assessment.assessment_fingerprint() == assessment.assessment_fingerprint()


def test_local_target_profile_records_per_command_sandbox_disable():
    context = SimpleNamespace(
        execution_target=MappingProxyType({"type": "local"}),
        boundary=MappingProxyType({"sandboxed": True, "network_allowed": False}),
        effective_roots=("/workspace",),
        remote_identity=None,
    )

    target = command_target_profile_from_context(
        context,
        action_input={
            "cwd": "/workspace",
            "dangerously_disable_sandbox": True,
        },
    )

    assert target.sandbox_strength == "none"
    assert target.network_allowed is True
