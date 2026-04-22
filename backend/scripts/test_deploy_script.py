import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path("/Users/lewisliu/Dev/playground/bpiper")
SCRIPT = REPO / "deploy.sh"


def write_stub(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def run_script(*args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="deploy-script-test-") as td:
        tmpdir = Path(td)
        bin_dir = tmpdir / "bin"
        bin_dir.mkdir()
        log_file = tmpdir / "docker.log"

        write_stub(
            bin_dir / "docker",
            f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"{log_file}\"\nexit 0\n",
        )
        write_stub(bin_dir / "ssh", "#!/bin/sh\nexit 0\n")
        write_stub(bin_dir / "scp", "#!/bin/sh\nexit 0\n")
        write_stub(bin_dir / "git", "#!/bin/sh\necho stub-user\n")
        write_stub(
            bin_dir / "du",
            "#!/bin/sh\necho '123M\t'$2\n",
        )

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env["TMPDIR"] = td
        if extra_env:
            env.update(extra_env)

        result = subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
        )
        result.docker_log = log_file.read_text() if log_file.exists() else ""
        return result


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"Expected to find {needle!r} in:\n{haystack}")


def test_build_amd64_uses_buildx_platform() -> None:
    result = run_script("build", "--arch", "amd64")
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    assert_contains(result.docker_log, "buildx build --platform linux/amd64")
    assert_contains(result.docker_log, "-f backend/Dockerfile --load backend")
    assert_contains(result.docker_log, "-f frontend/Dockerfile")
    assert_contains(result.docker_log, "--load frontend")


def test_build_arm64_uses_buildx_platform() -> None:
    result = run_script("build", "--arch", "arm64")
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    assert_contains(result.docker_log, "buildx build --platform linux/arm64")


def test_release_pushes_multi_arch() -> None:
    result = run_script("release", extra_env={"GHCR_USER": "demo-user", "IMAGE_TAG": "v1.2.3"})
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    assert_contains(result.docker_log, "buildx build --platform linux/amd64,linux/arm64")
    assert_contains(result.docker_log, "--push")
    assert_contains(result.docker_log, "ghcr.io/demo-user/bioinfoflow-backend:v1.2.3")
    assert_contains(result.docker_log, "ghcr.io/demo-user/bioinfoflow-frontend:v1.2.3")


def test_help_mentions_arch_release_and_ghcr() -> None:
    result = run_script("--help")
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    assert_contains(result.stdout, "--arch amd64|arm64")
    assert_contains(result.stdout, "release")
    assert_contains(result.stdout, "GHCR setup")
    assert_contains(result.stdout, "docker login ghcr.io")


if __name__ == "__main__":
    tests = [
        test_build_amd64_uses_buildx_platform,
        test_build_arm64_uses_buildx_platform,
        test_release_pushes_multi_arch,
        test_help_mentions_arch_release_and_ghcr,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
