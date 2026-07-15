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
BYPASS_TARGETS = [LOCAL_UNSANDBOXED, REMOTE]


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


def test_fd_duplication_redirect_is_not_a_write_sink():
    assessment = assess_command_risk("cat missing.json 2>&1", target=REMOTE)

    assert assessment.level == "act_low"
    assert assessment.effects == ["read"]
    assert assessment.requires_explicit_approval is False


def test_numeric_output_redirect_target_is_still_a_file_sink():
    assessment = assess_command_risk("echo ok > 2", target=REMOTE)

    assert assessment.level == "act_high"
    assert assessment.effects == ["write"]
    assert assessment.requires_explicit_approval is False


def test_remote_full_access_allows_literal_inline_filter_pipeline():
    command = (
        "phoenixcli --no-interactive task list --output json --page-size 100 "
        "2>&1 | python3 -c \"import sys,json; "
        "data=json.load(sys.stdin); print(len(data.get('data', [])))\""
    )

    assessment = assess_command_risk(command, target=REMOTE)

    assert "write" not in assessment.effects
    assert assessment.requires_explicit_approval is False
    assert (
        PermissionPolicy()
        .decide(
            risk=assessment,
            permission_mode="bypass",
            automation_mode="assisted",
        )
        .decision
        == "allow"
    )


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
        "sandbox_bypass_requested": False,
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


@pytest.mark.parametrize(
    "command",
    [
        "install payload ~/.ssh/authorized_keys",
        "dd if=payload of=~/.ssh/authorized_keys",
        "printf payload | tee ~/.ssh/authorized_keys",
        "cp payload ~/.ssh/authorized_keys",
        "cp payload ~/.ssh/authorized_keys --suffix .bak",
        "mv payload ~/.ssh/authorized_keys",
        "printf payload > ~/.ssh/authorized_keys",
        "sort -o ~/.ssh/authorized_keys input.txt",
        "sort -o~/.ssh/authorized_keys input.txt",
        "diff --output=~/.ssh/changes.patch before.txt after.txt",
        "diff --output ~/.ssh/changes.patch before.txt after.txt",
        "git diff --output=~/.ssh/changes.patch HEAD~1 HEAD",
        "git diff --output ~/.ssh/changes.patch HEAD~1 HEAD",
    ],
)
def test_every_supported_write_sink_protects_credential_destinations(command):
    assessment = assess_command_risk(command, target=LOCAL_UNSANDBOXED)

    assert assessment.requires_explicit_approval is True
    assert "write" in assessment.effects
    assert {item["kind"] for item in assessment.protected_resources} == {"ssh"}
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


@pytest.mark.parametrize(
    "command",
    [
        "ln -s /tmp/evil /home/alice/.ssh/config",
        "ln /tmp/evil /home/alice/.ssh/authorized_keys",
        "tar -xf payload.tar -C /home/alice/.ssh",
        "tar -xf payload.tar --directory=/home/alice/.ssh",
        "unzip payload.zip -d /home/alice/.ssh",
        "rsync payload /home/alice/.ssh/authorized_keys",
    ],
)
def test_archive_link_and_sync_sinks_protect_credential_destinations(command):
    assessment = assess_command_risk(command, target=LOCAL_UNSANDBOXED)

    assert assessment.requires_explicit_approval is True
    assert "write" in assessment.effects
    assert {item["kind"] for item in assessment.protected_resources} == {"ssh"}
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


def test_unknown_non_read_command_with_protected_path_fails_ask():
    assessment = assess_command_risk(
        "credential-rewriter /home/alice/.ssh/config",
        target=LOCAL_UNSANDBOXED,
    )

    assert assessment.requires_explicit_approval is True
    assert {item["kind"] for item in assessment.protected_resources} == {"ssh"}
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


def test_unrelated_protected_read_does_not_turn_a_safe_sink_into_protected_write():
    assessment = assess_command_risk(
        "cat ~/.ssh/config && printf ok > output.txt",
        target=LOCAL_UNSANDBOXED,
    )

    assert assessment.requires_explicit_approval is False
    assert {item["kind"] for item in assessment.protected_resources} == {"ssh"}


@pytest.mark.parametrize(
    "command",
    [
        "cp -r source output",
        "mv --no-clobber source output",
        "install -m 600 source output",
    ],
)
def test_known_copy_move_options_keep_concrete_destinations_confident(command):
    assessment = assess_command_risk(command, target=LOCAL_UNSANDBOXED)

    assert assessment.requires_explicit_approval is False


def test_protected_symlink_target_propagates_through_same_command_chain():
    assessment = assess_command_risk(
        "ln -s ~/.ssh/authorized_keys /tmp/key-a && "
        "ln -s /tmp/key-a /tmp/key-b && "
        "tee /tmp/key-b < payload",
        target=LOCAL_UNSANDBOXED,
    )

    assert assessment.requires_explicit_approval is True
    assert {item["path"] for item in assessment.protected_resources} == {
        "~/.ssh/authorized_keys"
    }


def test_relative_symlink_target_is_resolved_from_link_directory_in_same_chain():
    assessment = assess_command_risk(
        "ln -s ~/.ssh/authorized_keys /tmp/key-a && "
        "ln -s key-a /tmp/key-b && "
        "tee /tmp/key-b < payload",
        target=LOCAL_UNSANDBOXED,
    )

    assert assessment.requires_explicit_approval is True
    assert {item["path"] for item in assessment.protected_resources} == {
        "~/.ssh/authorized_keys"
    }


@pytest.mark.parametrize(
    "command",
    [
        "cp payload $DESTINATION",
        "install --target-directory=$DESTINATION payload",
        "dd if=payload of=$(resolve_destination)",
        "printf payload | tee ${DESTINATION}",
        "diff --output=$PATCH_PATH before.txt after.txt",
    ],
)
def test_remote_indirect_write_destinations_require_explicit_approval(command):
    assessment = assess_command_risk(command, target=REMOTE)

    assert assessment.requires_explicit_approval is True
    assert assessment.confidence == "low"
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
        "cp disk.img /dev/root --suffix .bak",
        "dd if=disk.img of=/dev/loop0",
        "mkfs.ext4 /dev/zram0",
        "install disk.img /dev/rdisk0",
        "mv disk.img /dev/root --suffix .bak",
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


def test_unknown_device_alias_write_is_denied_in_bypass():
    assessment = assess_command_risk(
        "dd if=disk.img of=/dev/disk/by-uuid/volume-alias",
        target=LOCAL_UNSANDBOXED,
    )

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


@pytest.mark.parametrize(
    "command",
    [
        "printf data | tee $TARGET",
        "cp disk.img ${DESTINATION}",
        "dd if=disk.img of=$(resolve_device)",
        "printf data > /dev/$DEVICE_NAME",
        "mv disk.img /dev/disk/by-id/*",
        "cp --target-directory=$DESTINATION disk.img",
        "install -t ${DESTINATION} disk.img",
        "sed -i 's/old/new/' $TARGET",
    ],
)
def test_indirect_device_capable_write_targets_require_explicit_approval(command):
    assessment = assess_command_risk(command, target=LOCAL_UNSANDBOXED)

    assert assessment.hard_blocked is False
    assert assessment.requires_explicit_approval is True
    assert assessment.confidence == "low"
    assert any(
        "indirect" in reason or "unresolved" in reason for reason in assessment.reasons
    )
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


def test_compound_symlink_to_unsafe_device_is_hard_blocked():
    assessment = assess_command_risk(
        "ln -s /dev/root /tmp/device-alias && dd if=disk.img of=/tmp/device-alias",
        target=LOCAL_UNSANDBOXED,
    )

    assert assessment.hard_blocked is True
    assert assessment.level == "critical"


def test_compound_relative_symlink_alias_is_normalized_before_sink_check():
    assessment = assess_command_risk(
        "ln -s /dev/root device-alias && dd if=disk.img of=./device-alias",
        target=LOCAL_UNSANDBOXED,
    )

    assert assessment.hard_blocked is True


def test_compound_symlink_with_unknown_target_requires_explicit_approval():
    assessment = assess_command_risk(
        "ln -s $TARGET /tmp/device-alias && tee /tmp/device-alias < disk.img",
        target=LOCAL_UNSANDBOXED,
    )

    assert assessment.hard_blocked is False
    assert assessment.requires_explicit_approval is True
    assert assessment.confidence == "low"
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


@pytest.mark.parametrize("path", ["/dev/shm/cache.bin", "/dev/pts/4"])
def test_non_block_device_subtrees_are_explicit_not_hard_blocked(path):
    assessment = assess_command_risk(
        f"tee {path} < data.bin",
        target=LOCAL_UNSANDBOXED,
    )

    assert assessment.hard_blocked is False
    assert assessment.requires_explicit_approval is True
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
    assert target.sandbox_bypass_requested is True


def test_sandbox_opt_out_always_requires_explicit_approval_even_in_bypass():
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
            "command": "pwd",
            "dangerously_disable_sandbox": True,
        },
    )

    assessment = assess_command_risk("pwd", target=target)

    assert assessment.requires_explicit_approval is True
    assert assessment.boundary["sandbox_bypass_requested"] is True
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


@pytest.mark.parametrize(
    "command",
    [
        "sh -c '$COMMAND'",
        'bash -lc "echo reboot"',
        "python -c \"print('reboot')\"",
        'python3 -c "$SCRIPT"',
        "node -e \"console.log('shutdown')\"",
    ],
)
def test_unproven_inline_code_or_danger_literals_require_explicit_approval(command):
    assessment = assess_command_risk(command, target=LOCAL_UNSANDBOXED)

    assert assessment.hard_blocked is False
    assert assessment.requires_explicit_approval is True
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


@pytest.mark.parametrize(
    "command",
    [
        "python3.13 -c \"print('ok')\"",
        "nodejs -e \"console.log('ok')\"",
        "ruby3.4 -e \"puts 'ok'\"",
        "perl5.40 -e \"print 'ok'\"",
        "php8.4 -r \"echo 'ok';\"",
    ],
)
def test_versioned_and_alternate_inline_interpreters_require_approval(command):
    assessment = assess_command_risk(command, target=LOCAL_UNSANDBOXED)

    assert assessment.hard_blocked is False
    assert assessment.requires_explicit_approval is True


@pytest.mark.parametrize(
    "command",
    [
        "python3.13 -c 'import os; os.system(\"reboot\")'",
        'nodejs -e \'require("child_process").execSync("reboot")\'',
        "ruby3.4 -e 'system(\"reboot\")'",
        "perl5.40 -e 'system(\"reboot\")'",
        "php8.4 -r 'system(\"reboot\");'",
    ],
)
def test_versioned_interpreter_literal_hardlines_are_denied(command):
    assessment = assess_command_risk(command, target=LOCAL_UNSANDBOXED)

    assert assessment.level == "critical"
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


@pytest.mark.parametrize("target", BYPASS_TARGETS, ids=["local", "ssh"])
@pytest.mark.parametrize(
    "command",
    [
        "command -p reboot",
        "command -- reboot",
        "nohup -- reboot",
        "exec -a harmless reboot",
        "sudo --user root reboot",
        "timeout --signal KILL 1 reboot",
        "nice --adjustment 10 reboot",
        "systemctl --host remote reboot",
        "busybox ash -c reboot",
        "xargs command -p reboot",
        "find / -exec command -p rm -rf {} +",
        "find . -exec reboot {} +",
        "find /tmp -exec command -p reboot {} +",
        "(reboot)",
        "{ reboot; }",
        "if true; then reboot; fi",
        "printf reboot | sh",
        "echo reboot | bash",
        "printf reboot | busybox sh",
        "x=reboot; $x",
        "x=re; ${x}boot",
        "cmd=reboot; command $cmd",
        "f(){ reboot; }; f",
        "f () { reboot; }; f",
        "function f { reboot; }; f",
        "function f () { reboot; }; f",
        "sh -c 'f () { reboot; }; f'",
        "bash -c 'f () { reboot; }; f'",
        "zsh -c 'f () { reboot; }; f'",
        "cat <(reboot)",
        "sh <<'EOF'\nreboot\nEOF",
        "env -S 'reboot'",
        "env --split-string='reboot'",
        "xargs env --split-string='reboot'",
        "env -Sreboot",
        "xargs env -Sreboot",
        "env -iSreboot",
        "env -iS reboot",
        "env -viSreboot",
        "xargs env -iSreboot",
        "xargs env -iS reboot",
        "perl5.40 '-Esystem(\"reboot\")'",
        "perl5.40 -we 'system(\"reboot\")'",
        "perl5.40 -wE 'system(\"reboot\")'",
        "perl5.40 -lwe 'system(\"reboot\")'",
        "perl5.40 -nwe 'system(\"reboot\")'",
        "perl5.40 -ple 'system(\"reboot\")'",
        "perl5.40 -fe 'system(\"reboot\")'",
        "perl5.40 -Se 'system(\"reboot\")'",
        "perl5.40 -Xe 'system(\"reboot\")'",
        "perl5.40 -0e 'system(\"reboot\")'",
        "perl5.40 -0777e 'system(\"reboot\")'",
        "perl5.40 -0777E 'system(\"reboot\")'",
        "perl5.40 '-lwEsystem(\"reboot\")'",
        "ruby3.4 -we 'system(\"reboot\")'",
        "ruby3.4 -nle 'system(\"reboot\")'",
        "ruby3.4 -0e 'system(\"reboot\")'",
        "ruby3.4 -0777e 'system(\"reboot\")'",
        "ruby3.4 -We 'system(\"reboot\")'",
        "ruby3.4 -W0e 'system(\"reboot\")'",
        "ruby3.4 -W2e 'system(\"reboot\")'",
        "ruby3.4 -Te 'system(\"reboot\")'",
        "ruby3.4 -T2e 'system(\"reboot\")'",
        "ruby3.4 -Kue 'system(\"reboot\")'",
        "ruby3.4 -Kee 'system(\"reboot\")'",
        "perl5.40 -l141e 'system(\"reboot\")'",
        "perl5.40 -l141E 'system(\"reboot\")'",
        "ruby3.4 '-apwesystem(\"reboot\")'",
        "php8.4 '-Bsystem(\"reboot\");'",
        "php8.4 '-Rsystem(\"reboot\");'",
        "php8.4 '-Esystem(\"reboot\");'",
    ],
)
def test_literal_catastrophic_nested_commands_are_denied_in_bypass(target, command):
    assessment = assess_command_risk(command, target=target)

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


@pytest.mark.parametrize("target", BYPASS_TARGETS, ids=["local", "ssh"])
@pytest.mark.parametrize(
    "command",
    [
        "(printf ok)",
        "if true; then printf ok; fi",
        "for reboot in one; do printf ok; done",
        "diff <(cat before.txt) <(cat after.txt)",
        "sh <<'EOF'\nprintf ok\nEOF",
        "env --split-string='printf ok'",
        "env '-Sprintf ok'",
        "xargs env '-Sprintf ok'",
        "env '-iSprintf ok'",
        "env -iS 'printf ok'",
        "env -viS 'printf ok'",
        "xargs env '-iSprintf ok'",
        "xargs env -iS 'printf ok'",
        "printf 'printf ok' | sh",
        "printf 'printf ok' | busybox sh",
        "safe=printf; $safe ok",
        "safe=printf; command $safe ok",
        "f(){ printf ok; }; f",
        "f () { printf ok; }; f",
        "function f { printf ok; }; f",
        "function f () { printf ok; }; f",
        "sh -c 'f () { printf ok; }; f'",
        "bash -c 'f () { printf ok; }; f'",
        "zsh -c 'f () { printf ok; }; f'",
        "find . -exec sh -c 'printf ok' {} +",
        "perl5.40 '-Eprint(\"ok\")'",
        "perl5.40 -we 'print(\"ok\")'",
        "perl5.40 -wE 'print(\"ok\")'",
        "perl5.40 -lwe 'print(\"ok\")'",
        "perl5.40 -nwe 'print(\"ok\")'",
        "perl5.40 -ple 'print(\"ok\")'",
        "perl5.40 -fe 'print(\"ok\")'",
        "perl5.40 -Se 'print(\"ok\")'",
        "perl5.40 -Xe 'print(\"ok\")'",
        "perl5.40 -0e 'print(\"ok\")'",
        "perl5.40 -0777e 'print(\"ok\")'",
        "perl5.40 -0777E 'print(\"ok\")'",
        "ruby3.4 -we 'puts(\"ok\")'",
        "ruby3.4 -nle 'puts(\"ok\")'",
        "ruby3.4 -0e 'puts(\"ok\")'",
        "ruby3.4 -0777e 'puts(\"ok\")'",
        "ruby3.4 -We 'puts(\"ok\")'",
        "ruby3.4 -W0e 'puts(\"ok\")'",
        "ruby3.4 -W2e 'puts(\"ok\")'",
        "ruby3.4 -Te 'puts(\"ok\")'",
        "ruby3.4 -T2e 'puts(\"ok\")'",
        "ruby3.4 -Kue 'puts(\"ok\")'",
        "ruby3.4 -Kee 'puts(\"ok\")'",
        "perl5.40 -l141e 'print(\"ok\")'",
        "perl5.40 -l141E 'print(\"ok\")'",
        "ruby3.4 '-apweputs(\"ok\")'",
        "php8.4 '-Becho \"ok\";'",
        "php8.4 '-Recho \"ok\";'",
        "php8.4 '-Eecho \"ok\";'",
        "php8.4 -F worker.php",
    ],
)
def test_unsupported_shell_grammar_fails_ask_in_bypass(target, command):
    assessment = assess_command_risk(command, target=target)

    assert assessment.hard_blocked is False
    assert assessment.requires_explicit_approval is True
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


@pytest.mark.parametrize("target", BYPASS_TARGETS, ids=["local", "ssh"])
@pytest.mark.parametrize(
    "command",
    [
        "python3.13 '-cprint(\"ok\")'",
        "nodejs '--eval=console.log(\"ok\")'",
        "ruby3.4 '-eputs(\"ok\")'",
        "perl5.40 '-eprint(\"ok\")'",
    ],
)
def test_attached_inline_interpreter_source_requires_approval(target, command):
    assessment = assess_command_risk(command, target=target)

    assert assessment.hard_blocked is False
    assert assessment.requires_explicit_approval is True
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


@pytest.mark.parametrize("target", BYPASS_TARGETS, ids=["local", "ssh"])
@pytest.mark.parametrize(
    "command",
    [
        "python3.13 '-cimport os; os.system(\"reboot\")'",
        'nodejs \'--eval=require("child_process").execSync("reboot")\'',
        "ruby3.4 '-esystem(\"reboot\")'",
        "perl5.40 '-esystem(\"reboot\")'",
    ],
)
def test_attached_inline_interpreter_hardlines_are_denied(target, command):
    assessment = assess_command_risk(command, target=target)

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


@pytest.mark.parametrize("target", BYPASS_TARGETS, ids=["local", "ssh"])
@pytest.mark.parametrize(
    "command",
    [
        "printf x >| /home/alice/.ssh/config",
        "rsync payload /home/alice/.ssh/authorized_keys --log-file /tmp/rsync.log",
        "credential-rewriter --dest=/home/alice/.ssh/config",
        "tar -xf payload.tar -C /home/alice",
        "tar xf payload.tar",
        "tar xCf /home/alice payload.tar",
        "unzip payload.zip -d /home/alice",
        "rsync payload /home/alice/.ssh/authorized_keys --out-format %n",
        "rsync payload /tmp/output -T/home/alice/.ssh",
        "rsync -avT/home/alice/.ssh payload /tmp/output",
        "rsync -vaT/home/alice/.ssh payload /tmp/output",
    ],
)
def test_opaque_or_protected_write_sinks_fail_ask_in_bypass(target, command):
    assessment = assess_command_risk(command, target=target)

    assert assessment.hard_blocked is False
    assert assessment.requires_explicit_approval is True
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


@pytest.mark.parametrize("target", BYPASS_TARGETS, ids=["local", "ssh"])
@pytest.mark.parametrize(
    "command",
    [
        "command -v reboot",
        "tar -tf payload.tar",
        "tar tf payload.tar",
        "unzip -l payload.zip",
        "unzip -Z1 payload.zip",
        "unzip -p payload.zip report.txt",
        "unzip -c payload.zip report.txt",
        "python3.13 script.py",
        "perl5.40 script.pl",
        "perl5.40 -Mstrictwe script.pl",
        "perl5.40 -Ilibe script.pl",
        "perl5.40 -0777 script.pl",
        "perl5.40 -0x1Fe script.pl",
        "ruby3.4 -Ilibe script.rb",
        "ruby3.4 -rwebrick script.rb",
        "ruby3.4 -0777 script.rb",
        "ruby3.4 -W:deprecated script.rb",
        "ruby3.4 -T2 script.rb",
        "ruby3.4 -Ke script.rb",
        "perl5.40 -l141 script.pl",
        "php8.4 script.php",
        "printf reboot",
        "find . -exec printf ok {} +",
    ],
)
def test_provable_non_inline_or_read_only_analogs_do_not_force_approval(
    target, command
):
    assessment = assess_command_risk(command, target=target)

    assert assessment.hard_blocked is False
    assert assessment.requires_explicit_approval is False
    assert (
        PermissionPolicy()
        .decide(
            risk=assessment,
            permission_mode="bypass",
            automation_mode="autonomous",
        )
        .decision
        == "allow"
    )


@pytest.mark.parametrize("target", BYPASS_TARGETS, ids=["local", "ssh"])
@pytest.mark.parametrize(
    "command",
    [
        "rsync payload /tmp/output -T/tmp/rsync-work",
        "rsync -avT/tmp/rsync-work payload /tmp/output",
        "rsync -vaT/tmp/rsync-work payload /tmp/output",
    ],
)
def test_non_protected_attached_rsync_temp_dir_does_not_force_approval(target, command):
    assessment = assess_command_risk(
        command,
        target=target,
    )

    assert assessment.hard_blocked is False
    assert assessment.requires_explicit_approval is False
    assert (
        PermissionPolicy()
        .decide(
            risk=assessment,
            permission_mode="bypass",
            automation_mode="autonomous",
        )
        .decision
        == "allow"
    )


@pytest.mark.parametrize(
    "command",
    [
        "xargs rm -rf",
        "printf '/\\n' | xargs rm -rf",
    ],
)
def test_unknown_xargs_destructive_targets_require_explicit_approval(command):
    assessment = assess_command_risk(command, target=LOCAL_UNSANDBOXED)

    assert assessment.hard_blocked is False
    assert assessment.requires_explicit_approval is True
