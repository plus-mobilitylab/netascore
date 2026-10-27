"""Builds the Docker image of NetAScore - on macOS, Linux, and Windows (requires Python 3.9+, Git, and Docker).

The version is read from settings.py (NETASCORE_VERSION), the code state from Git (passed to the image as build argument
NETASCORE_COMMIT - recorded in the output metadata of each run).

Local build (default): image for the platform of this machine, loaded into the local Docker installation:
    python scripts/build_docker_image.py
    -> netascore:<version> and netascore:latest

Release build: image for linux/amd64 and linux/arm64 (e.g. Apple silicon), pushed to Docker Hub (requires 'docker login'
and Docker Buildx). Only for a committed state with the release tag v<version>:
    python scripts/build_docker_image.py --push [--latest]
    -> plusmobilitylab/netascore:<version> (and :latest)

Use --dry-run to show the Docker commands without running them.
"""
import argparse
import os
import re
import subprocess
import sys

REPOSITORY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IMAGE = "plusmobilitylab/netascore"
RELEASE_PLATFORMS = "linux/amd64,linux/arm64"
BUILDER = "netascore-builder"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def run(args: list, dry_run: bool = False, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Runs a command (argument list - no shell, works the same on all platforms)."""
    print("$ " + subprocess.list2cmdline(args))
    if dry_run:
        return subprocess.CompletedProcess(args, 0, "", "")
    return subprocess.run(args, cwd=REPOSITORY_DIR, check=check, text=True, capture_output=capture)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPOSITORY_DIR, capture_output=True, text=True, check=True).stdout.strip()


def get_version() -> str:
    with open(os.path.join(REPOSITORY_DIR, "settings.py"), encoding="utf-8") as f:
        match = re.search(r'^NETASCORE_VERSION = "([^"]+)"', f.read(), re.MULTILINE)
    if not match:
        fail("NETASCORE_VERSION not found in settings.py")
    return match.group(1)


def get_code_state() -> tuple:
    """Code state as determined by NetAScore (settings.py)"""
    try:
        describe = git("describe", "--tags", "--dirty", "--always")
        branch = git("rev-parse", "--abbrev-ref", "HEAD")
        tags = git("tag", "--points-at", "HEAD").split()
    except (OSError, subprocess.CalledProcessError):
        fail("Git is required to determine the code state (run the script inside the NetAScore Git repository)")
    commit = describe if branch in ("", "HEAD") else f"{branch}, {describe}"
    return commit, describe.endswith("-dirty"), tags


def check_docker(need_buildx: bool) -> None:
    try:
        subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, check=True)
    except FileNotFoundError:
        fail("Docker not found - please install Docker (Docker Desktop on macOS / Windows)")
    except subprocess.CalledProcessError:
        fail("Docker is installed but not running - please start Docker")
    if need_buildx and subprocess.run(["docker", "buildx", "version"], capture_output=True).returncode != 0:
        fail("Docker Buildx is required for multi-platform builds (included in Docker Desktop; on Linux: package docker-buildx)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Docker image of NetAScore (local build or multi-platform release).")
    parser.add_argument("--push", action="store_true",
                        help=f"release build for {RELEASE_PLATFORMS}, pushed to the registry (requires 'docker login')")
    parser.add_argument("--latest", action="store_true", help="also tag the image as 'latest' (always set for local builds)")
    parser.add_argument("--image", default=None, help=f"image name (default: '{DEFAULT_IMAGE}' with --push, 'netascore' otherwise)")
    parser.add_argument("--platforms", default=None, help=f"target platforms (default: {RELEASE_PLATFORMS} with --push, this machine otherwise)")
    parser.add_argument("--allow-dirty", action="store_true", help="allow --push with uncommitted changes (not recommended)")
    parser.add_argument("--allow-untagged", action="store_true", help="allow --push without release tag v<version> at the current commit")
    parser.add_argument("--dry-run", action="store_true", help="only show the Docker commands")
    args = parser.parse_args()

    if not args.push and args.platforms and "," in args.platforms:
        fail("several platforms can only be built with --push (the local Docker image store holds one platform per tag)")
    version = get_version()
    commit, dirty, tags = get_code_state()
    image = args.image or (DEFAULT_IMAGE if args.push else "netascore")
    print(f"NetAScore {version} - code state: {commit}")

    if args.push:
        # a published image has to correspond exactly to a release
        if dirty and not args.allow_dirty:
            fail("uncommitted changes - commit them first (or use --allow-dirty)")
        if f"v{version}" not in tags and not args.allow_untagged:
            fail(f"the current commit has no release tag v{version} (tags: {', '.join(tags) or 'none'}) - "
                 "build the released state (or use --allow-untagged)")
    elif dirty:
        print("note: uncommitted changes are included in the image (code state ends with '-dirty')")

    if not args.dry_run:
        check_docker(need_buildx=args.push or args.platforms is not None)

    tag_args = ["-t", f"{image}:{version}"]
    if args.latest or not args.push:
        tag_args += ["-t", f"{image}:latest"]
    build_args = ["--build-arg", f"NETASCORE_COMMIT={commit}", "--label", f"org.opencontainers.image.version={version}",
                  "--label", f"org.opencontainers.image.revision={git('rev-parse', 'HEAD')}"]

    if args.push or args.platforms:
        # multi-platform build with Buildx (builder with the docker-container driver, created once)
        if not args.dry_run and subprocess.run(["docker", "buildx", "inspect", BUILDER], capture_output=True).returncode != 0:
            run(["docker", "buildx", "create", "--name", BUILDER, "--driver", "docker-container"])
        elif args.dry_run:
            print(f"(creates the Buildx builder '{BUILDER}' if it does not exist)")
        output = ["--push"] if args.push else ["--load"]
        run(["docker", "buildx", "build", "--builder", BUILDER, "--platform", args.platforms or RELEASE_PLATFORMS,
             *build_args, *tag_args, *output, "."], dry_run=args.dry_run)
    else:
        run(["docker", "build", *build_args, *tag_args, "."], dry_run=args.dry_run)

    if not args.dry_run:
        print(f"done: {', '.join(t for t in tag_args if t != '-t')}" + (" (pushed)" if args.push else ""))
        if not args.push:
            print(f"test: docker run --rm {image}:{version} --help")


if __name__ == "__main__":
    main()
