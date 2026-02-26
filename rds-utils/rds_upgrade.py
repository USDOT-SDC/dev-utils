#!/usr/bin/env python3
"""
RDS Upgrade Manager

CLI tool for managing AWS RDS / Aurora version upgrades with:
  - Automatic intermediate-version path calculation via BFS
  - Crash-resilient progress tracking (JSON state file)
  - Resume support across sessions
  - Automatic boto3 session refresh for 60-min rotating credentials
  - Dry-run mode

Usage:
    python rds_upgrade.py
"""

import json
import sys
import time
import traceback
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_FILE = Path(__file__).parent / "config.json"
STATE_FILE = Path(__file__).parent / "upgrade_state.json"
POLL_INTERVAL_SECONDS = 60

AUTH_ERROR_CODES = frozenset(
    {"ExpiredTokenException", "AuthFailure", "InvalidClientTokenId", "AccessDeniedException"}
)

ENGINE_DISPLAY = {
    "aurora-postgresql": "Aurora PostgreSQL",
    "mariadb": "MariaDB",
}

STATUS_COLORS = {
    "completed": "green",
    "failed": "red",
    "in_progress": "yellow",
    "pending": "blue",
    "skipped": "dim",
    "not started": "dim",
}

console = Console()


# ---------------------------------------------------------------------------
# State Management
# ---------------------------------------------------------------------------


class StateManager:
    """Manages persistent upgrade state for crash resilience and resume support.

    State is stored as a JSON file on disk. Every mutation is immediately
    flushed so a crash mid-upgrade loses at most the current poll interval.
    """

    def __init__(self, state_file: Path = STATE_FILE) -> None:
        """Initialize state manager and load existing state.

        Args:
            state_file: Path to the JSON state file.
        """
        self.state_file = state_file
        self.state = self._load()

    def _load(self) -> dict:
        """Load state from disk.

        Returns:
            Parsed state dict, or an empty state if the file doesn't exist or
            is corrupt.
        """
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                console.print(
                    f"[yellow]Warning: state file unreadable ({exc}), starting fresh.[/yellow]"
                )

        return {"upgrades": {}}

    def reload(self) -> None:
        """Reload state from disk, picking up any external edits."""
        self.state = self._load()

    def save(self) -> None:
        """Flush current state to disk."""
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2, default=str)

    def get(self, arn: str) -> Optional[dict]:
        """Return state for a single resource.

        Args:
            arn: Resource ARN.

        Returns:
            State dict for the resource, or None if not yet tracked.
        """
        return self.state["upgrades"].get(arn)

    def update(self, arn: str, **kwargs) -> None:
        """Update fields for a resource and persist immediately.

        Args:
            arn: Resource ARN.
            **kwargs: Fields to set / overwrite.
        """
        if arn not in self.state["upgrades"]:
            self.state["upgrades"][arn] = {}
        self.state["upgrades"][arn].update(kwargs)
        self.state["upgrades"][arn]["last_updated"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def has_resumable(self) -> bool:
        """Return True if any upgrade is in a resumable (non-terminal) state.

        Returns:
            True if pending or in_progress upgrades exist.
        """
        resumable = {"pending", "in_progress"}
        return any(
            v.get("status") in resumable for v in self.state["upgrades"].values()
        )


# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------


class SessionManager:
    """Creates fresh boto3 sessions on every client request.

    Because credentials are renewed externally (e.g. AWS SSO or a credential
    helper) by writing to the named profile, we must create a new
    ``boto3.Session`` each time we need a client. A cached session would hold
    on to the old (expired) credentials.
    """

    def __init__(self, profile: str, region: str) -> None:
        """Initialize session manager.

        Args:
            profile: AWS named profile (e.g. "sdc-dev").
            region: AWS region (e.g. "us-east-1").
        """
        self.profile = profile
        self.region = region

    def client(self, service: str):
        """Create and return a fresh boto3 client.

        Args:
            service: AWS service name (e.g. "rds").

        Returns:
            A fresh boto3 service client.
        """
        session = boto3.Session(profile_name=self.profile, region_name=self.region)
        return session.client(service)

    def rds(self):
        """Convenience wrapper — returns a fresh RDS client.

        Returns:
            A fresh boto3 RDS client.
        """
        return self.client("rds")


# ---------------------------------------------------------------------------
# ARN Utilities
# ---------------------------------------------------------------------------


def arn_resource_id(arn: str) -> str:
    """Extract the resource identifier (last segment) from an ARN.

    Args:
        arn: Full AWS ARN string.

    Returns:
        Resource ID string (e.g. "aurora-dataexport-edge").
    """
    return arn.split(":")[-1]


def arn_region(arn: str) -> str:
    """Extract the region from an ARN.

    Args:
        arn: Full AWS ARN string.

    Returns:
        Region string (e.g. "us-east-1").
    """
    return arn.split(":")[3]


# ---------------------------------------------------------------------------
# AWS Helpers
# ---------------------------------------------------------------------------


def get_current_version(rds_client, resource: dict) -> Optional[str]:
    """Fetch the live engine version of a cluster or instance from AWS.

    Args:
        rds_client: boto3 RDS client.
        resource: Resource definition dict from config.

    Returns:
        Engine version string, or None on error.
    """
    resource_id = arn_resource_id(resource["arn"])

    try:
        if resource["type"] == "cluster":
            resp = rds_client.describe_db_clusters(DBClusterIdentifier=resource_id)
            return resp["DBClusters"][0]["EngineVersion"]
        else:
            resp = rds_client.describe_db_instances(DBInstanceIdentifier=resource_id)
            return resp["DBInstances"][0]["EngineVersion"]
    except ClientError as exc:
        console.print(
            f"  [red]Error fetching version for {resource['name']}: {exc}[/red]"
        )
        return None


def get_aws_status(rds_client, resource: dict) -> tuple[Optional[str], Optional[str]]:
    """Fetch the current AWS status and engine version of a resource.

    Args:
        rds_client: boto3 RDS client.
        resource: Resource definition dict from config.

    Returns:
        Tuple of (status, engine_version). Both None on non-auth error.

    Raises:
        ClientError: Re-raised for auth-related errors so the caller can handle
            credential expiry gracefully.
    """
    resource_id = arn_resource_id(resource["arn"])

    try:
        if resource["type"] == "cluster":
            resp = rds_client.describe_db_clusters(DBClusterIdentifier=resource_id)
            cluster = resp["DBClusters"][0]
            return cluster["Status"], cluster["EngineVersion"]
        else:
            resp = rds_client.describe_db_instances(DBInstanceIdentifier=resource_id)
            inst = resp["DBInstances"][0]
            return inst["DBInstanceStatus"], inst["EngineVersion"]
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in AUTH_ERROR_CODES:
            raise
        console.print(
            f"  [red]Error polling {resource['name']}: {exc}[/red]"
        )
        return None, None


# ---------------------------------------------------------------------------
# Upgrade Path (BFS)
# ---------------------------------------------------------------------------


def get_upgrade_path(
    rds_client,
    engine: str,
    current_version: str,
    target_version: str,
) -> list[str]:
    """Find the shortest upgrade path from current to target version.

    Performs a BFS over the graph of valid AWS upgrade targets, starting from
    ``current_version`` and finding the fewest-hops path to ``target_version``.

    Args:
        rds_client: boto3 RDS client.
        engine: Engine string (e.g. "aurora-postgresql", "mariadb").
        current_version: The version the resource is currently running.
        target_version: The desired final version.

    Returns:
        Ordered list of versions to upgrade *through* (excluding
        ``current_version``, including ``target_version``). Empty list if the
        resource is already at the target or no valid path exists.
    """
    if current_version == target_version:
        return []

    queue: deque[list[str]] = deque([[current_version]])
    visited: set[str] = {current_version}

    while queue:
        path = queue.popleft()
        current = path[-1]

        try:
            resp = rds_client.describe_db_engine_versions(
                Engine=engine,
                EngineVersion=current,
            )
        except ClientError as exc:
            console.print(
                f"  [yellow]Warning: could not get upgrade targets for "
                f"{engine} {current}: {exc}[/yellow]"
            )
            continue

        for version_info in resp.get("DBEngineVersions", []):
            for upgrade_target in version_info.get("ValidUpgradeTarget", []):
                next_ver = upgrade_target["EngineVersion"]

                if next_ver in visited:
                    continue

                new_path = path + [next_ver]

                if next_ver == target_version:
                    return new_path[1:]  # drop the starting version

                visited.add(next_ver)
                queue.append(new_path)

    return []  # no path found


# ---------------------------------------------------------------------------
# Upgrade Execution
# ---------------------------------------------------------------------------


def trigger_upgrade(
    rds_client,
    resource: dict,
    target_version: str,
    dry_run: bool = False,
) -> bool:
    """Trigger a single version upgrade step on a cluster or instance.

    Args:
        rds_client: boto3 RDS client.
        resource: Resource definition dict from config.
        target_version: Version to upgrade to for this step.
        dry_run: If True, log intent without making any AWS API calls.

    Returns:
        True if the upgrade was triggered (or would be in dry-run mode).
        False on API error.
    """
    resource_id = arn_resource_id(resource["arn"])
    label = f"{resource['env']}/{resource['name']}"

    if dry_run:
        console.print(
            f"  [cyan][DRY RUN][/cyan] Would upgrade [bold]{label}[/bold] → {target_version}"
        )
        return True

    try:
        if resource["type"] == "cluster":
            rds_client.modify_db_cluster(
                DBClusterIdentifier=resource_id,
                EngineVersion=target_version,
                ApplyImmediately=True,
                AllowMajorVersionUpgrade=True,
            )
        else:
            rds_client.modify_db_instance(
                DBInstanceIdentifier=resource_id,
                EngineVersion=target_version,
                ApplyImmediately=True,
                AllowMajorVersionUpgrade=True,
            )

        console.print(
            f"  [green]Upgrade triggered:[/green] [bold]{label}[/bold] → {target_version}"
        )
        return True

    except ClientError as exc:
        console.print(f"  [red]Failed to trigger upgrade for {label}: {exc}[/red]")
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# Polling Loop
# ---------------------------------------------------------------------------


def poll_upgrades(
    resources: list[dict],
    state_manager: StateManager,
    sessions: dict[str, SessionManager],
) -> None:
    """Monitor in-progress upgrades, triggering the next hop when each step completes.

    Creates a fresh boto3 client at the start of every poll iteration so that
    externally-refreshed credentials (from the named profile) are always used.
    Auth errors are logged and retried on the next iteration rather than
    crashing the loop.

    Args:
        resources: Resources to monitor.
        state_manager: State manager instance.
        sessions: Mapping of env name → SessionManager.
    """
    console.print(
        "\n[bold]Monitoring upgrades "
        "(Ctrl+C to stop monitoring — upgrades continue in AWS)...[/bold]\n"
    )

    # Kick off step 0 for any resource that is still "pending"
    for resource in resources:
        state = state_manager.get(resource["arn"])
        if not state or state.get("status") != "pending":
            continue

        step_version = state["upgrade_path"][0]
        try:
            rds = sessions[resource["env"]].rds()
            ok = trigger_upgrade(rds, resource, step_version)
            if ok:
                state_manager.update(resource["arn"], status="in_progress")
            else:
                state_manager.update(resource["arn"], status="failed")
        except ClientError as exc:
            console.print(
                f"  [red]Could not start upgrade for {resource['name']}: {exc}[/red]"
            )
            state_manager.update(resource["arn"], status="failed", error=str(exc))

    # Main poll loop
    try:
        while True:
            all_done = True

            for resource in resources:
                state = state_manager.get(resource["arn"])
                if not state or state.get("status") in ("completed", "failed", "skipped"):
                    continue

                all_done = False
                label = f"{resource['env']}/{resource['name']}"
                path: list[str] = state["upgrade_path"]
                step_idx: int = state.get("step_idx", 0)
                step_version: str = path[step_idx]

                try:
                    rds = sessions[resource["env"]].rds()
                    aws_status, engine_version = get_aws_status(rds, resource)

                    if aws_status is None:
                        continue

                    if aws_status == "available" and engine_version == step_version:
                        # This step finished — move on
                        console.print(
                            f"  [green]✓ {label}[/green] step done → {step_version}"
                        )
                        state_manager.update(resource["arn"], current_version=step_version)

                        next_idx = step_idx + 1
                        if next_idx >= len(path):
                            state_manager.update(
                                resource["arn"], status="completed", step_idx=step_idx
                            )
                            console.print(
                                f"  [bold green]✓✓ {label} fully upgraded to {step_version}[/bold green]"
                            )
                        else:
                            next_version = path[next_idx]
                            state_manager.update(resource["arn"], step_idx=next_idx)
                            ok = trigger_upgrade(rds, resource, next_version)
                            if not ok:
                                state_manager.update(resource["arn"], status="failed")

                    elif aws_status in ("failed", "restore-error", "inaccessible-encryption-credentials"):
                        console.print(
                            f"  [red]✗ {label}[/red] AWS status: {aws_status}"
                        )
                        state_manager.update(resource["arn"], status="failed")

                    else:
                        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                        console.print(
                            f"  [yellow]~ {label}[/yellow] "
                            f"{aws_status} @ {engine_version}  [{ts}]"
                        )

                except ClientError as exc:
                    code = exc.response["Error"]["Code"]
                    if code in AUTH_ERROR_CODES:
                        console.print(
                            f"  [yellow]Auth token expired for '{resource['env']}' profile "
                            f"— retrying next poll (credentials should refresh automatically)[/yellow]"
                        )
                    else:
                        console.print(
                            f"  [red]Poll error for {resource['name']}: {exc}[/red]"
                        )
                        traceback.print_exc()

            if all_done:
                console.print("\n[bold green]All upgrades complete![/bold green]")
                break

            console.print(
                f"\n  [dim]Next poll in {POLL_INTERVAL_SECONDS}s ...[/dim]"
            )
            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        console.print(
            "\n\n[yellow]Monitoring paused. "
            "Upgrades are still running in AWS.[/yellow]\n"
            "[yellow]Relaunch the script and choose [bold]Resume[/bold] "
            "to continue monitoring.[/yellow]"
        )


# ---------------------------------------------------------------------------
# Display Helpers
# ---------------------------------------------------------------------------


def build_status_table(resources: list[dict], state_manager: StateManager) -> Table:
    """Build a Rich table showing the upgrade status of all tracked resources.

    Args:
        resources: Resource list from config.
        state_manager: State manager with current progress.

    Returns:
        Populated Rich Table ready to print.
    """
    table = Table(
        title="RDS Upgrade Status",
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold magenta",
    )
    table.add_column("Env", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Engine")
    table.add_column("Current", style="yellow")
    table.add_column("Target", style="green")
    table.add_column("Path")
    table.add_column("Status")
    table.add_column("Updated", style="dim")

    for resource in resources:
        state = state_manager.get(resource["arn"])

        if state:
            current = state.get("current_version", "?")
            path = state.get("upgrade_path", [])
            step_idx = state.get("step_idx", 0)
            step_str = f"{step_idx + 1}/{len(path)}" if path else "—"
            status = state.get("status", "unknown")
            color = STATUS_COLORS.get(status, "white")
            status_cell = f"[{color}]{status}[/{color}]"
            updated = (state.get("last_updated") or "")[:19]
        else:
            current = "?"
            step_str = "—"
            status_cell = "[dim]not started[/dim]"
            updated = ""

        engine_label = ENGINE_DISPLAY.get(resource["engine"], resource["engine"])

        table.add_row(
            resource["env"],
            resource["name"],
            engine_label,
            current,
            resource["target_version"],
            step_str,
            status_cell,
            updated,
        )

    return table


# ---------------------------------------------------------------------------
# Menu Actions
# ---------------------------------------------------------------------------


def action_list(
    config: dict,
    state_manager: StateManager,
    sessions: dict[str, SessionManager],
) -> None:
    """Fetch live versions from AWS and display a status table.

    Args:
        config: Loaded configuration.
        state_manager: State manager instance.
        sessions: Mapping of env → SessionManager.
    """
    console.print("\n[bold]Fetching live versions from AWS...[/bold]")

    for resource in config["resources"]:
        env = resource["env"]
        label = f"{env}/{resource['name']}"

        try:
            rds = sessions[env].rds()
            version = get_current_version(rds, resource)

            if version is not None:
                existing = state_manager.get(resource["arn"]) or {}
                state_manager.update(
                    resource["arn"],
                    name=resource["name"],
                    env=env,
                    engine=resource["engine"],
                    current_version=version,
                    target_version=resource["target_version"],
                    status=existing.get("status", "not started"),
                )
                console.print(f"  {label}: {version}")

        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in AUTH_ERROR_CODES:
                console.print(
                    f"  [yellow]Auth error for '{env}' profile — "
                    f"credentials may need renewal[/yellow]"
                )
            else:
                console.print(f"  [red]Error for {label}: {exc}[/red]")

    console.print()
    console.print(build_status_table(config["resources"], state_manager))


def select_env(available_envs: list[str]) -> Optional[list[str]]:
    """Prompt the user to select which environment(s) to target.

    Args:
        available_envs: List of environment names from config.

    Returns:
        List of selected environment names, or None if the user cancelled.
    """
    console.print("\n[bold]Select environment:[/bold]")
    console.print("  [A] All environments")
    for i, env in enumerate(available_envs, start=1):
        console.print(f"  [{i}] {env}")
    console.print("  [B] Back")

    choice = input("\nSelect: ").strip().upper()

    if choice == "B":
        return None
    if choice == "A":
        return available_envs

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(available_envs):
            return [available_envs[idx]]
    except ValueError:
        pass

    console.print("[yellow]Invalid choice.[/yellow]")
    return None


def action_plan(
    config: dict,
    state_manager: StateManager,
    sessions: dict[str, SessionManager],
    envs: Optional[list[str]] = None,
    dry_run: bool = False,
) -> list[dict]:
    """Calculate upgrade paths for resources that need upgrading.

    Queries AWS for each resource's current version, then uses BFS to find the
    shortest hop-path to the configured target version. Results are written to
    the state file even if ``dry_run`` is True.

    Args:
        config: Loaded configuration.
        state_manager: State manager instance.
        sessions: Mapping of env → SessionManager.
        envs: Optional list of environment names to restrict to.
        dry_run: If True, annotate output but don't persist "pending" status.

    Returns:
        List of resource dicts ready for upgrade (with ``upgrade_path`` added).
    """
    prefix = "[cyan][DRY RUN][/cyan] " if dry_run else ""
    console.print(f"\n{prefix}[bold]Calculating upgrade paths...[/bold]\n")

    planned: list[dict] = []
    resources = (
        [r for r in config["resources"] if r["env"] in envs]
        if envs
        else config["resources"]
    )

    for resource in resources:
        env = resource["env"]
        label = f"{env}/{resource['name']}"

        try:
            rds = sessions[env].rds()
            current = get_current_version(rds, resource)

            if current is None:
                console.print(f"  [red]Skipping {label} — could not get current version[/red]")
                continue

            if current == resource["target_version"]:
                console.print(
                    f"  [green]✓ {label}[/green] "
                    f"already at {current} (target)"
                )
                state_manager.update(
                    resource["arn"],
                    status="skipped",
                    current_version=current,
                )
                continue

            path = get_upgrade_path(rds, resource["engine"], current, resource["target_version"])

            if not path:
                console.print(
                    f"  [red]✗ {label}[/red] "
                    f"no upgrade path found: {current} → {resource['target_version']}"
                )
                state_manager.update(
                    resource["arn"],
                    status="failed",
                    current_version=current,
                    error="No valid upgrade path found",
                )
                continue

            steps_display = " → ".join([current] + path)
            console.print(f"  [white]{label}[/white]: {steps_display}")

            if not dry_run:
                state_manager.update(
                    resource["arn"],
                    name=resource["name"],
                    env=env,
                    engine=resource["engine"],
                    type=resource["type"],
                    current_version=current,
                    target_version=resource["target_version"],
                    upgrade_path=path,
                    step_idx=0,
                    status="pending",
                )

            resource = dict(resource)
            resource["upgrade_path"] = path
            resource["current_version"] = current
            planned.append(resource)

        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in AUTH_ERROR_CODES:
                console.print(
                    f"  [yellow]Auth error for '{env}' profile — skipping {label}[/yellow]"
                )
            else:
                console.print(f"  [red]Error planning {label}: {exc}[/red]")
                traceback.print_exc()

    return planned


def action_upgrade(
    config: dict,
    state_manager: StateManager,
    sessions: dict[str, SessionManager],
    dry_run: bool = False,
) -> None:
    """Interactive upgrade flow: env selection → plan → confirm → execute.

    Args:
        config: Loaded configuration.
        state_manager: State manager instance.
        sessions: Mapping of env → SessionManager.
        dry_run: If True, plan and display without executing any upgrades.
    """
    available_envs = list(config["aws_profiles"].keys())
    selected_envs = select_env(available_envs)

    if selected_envs is None:
        return

    planned = action_plan(config, state_manager, sessions, envs=selected_envs, dry_run=dry_run)

    if not planned:
        console.print("[yellow]Nothing to upgrade.[/yellow]")
        return

    if dry_run:
        console.print("\n[cyan][DRY RUN] No changes were made.[/cyan]")
        return

    console.print()
    confirm = input("Proceed with the upgrades above? [y/N]: ").strip().lower()
    if confirm != "y":
        # Roll back pending status since user cancelled
        for resource in planned:
            existing = state_manager.get(resource["arn"]) or {}
            if existing.get("status") == "pending":
                state_manager.update(resource["arn"], status="not started")
        console.print("[yellow]Aborted.[/yellow]")
        return

    poll_upgrades(planned, state_manager, sessions)


def action_resume(
    config: dict,
    state_manager: StateManager,
    sessions: dict[str, SessionManager],
) -> None:
    """Resume monitoring of pending or in-progress upgrades from saved state.

    Args:
        config: Loaded configuration.
        state_manager: State manager instance.
        sessions: Mapping of env → SessionManager.
    """
    resumable: list[dict] = []

    for resource in config["resources"]:
        state = state_manager.get(resource["arn"])
        if state and state.get("status") in ("pending", "in_progress"):
            resource = dict(resource)
            resource["upgrade_path"] = state["upgrade_path"]
            resource["current_version"] = state.get("current_version", "?")
            resumable.append(resource)

    if not resumable:
        console.print("[yellow]No pending or in-progress upgrades to resume.[/yellow]")
        return

    console.print(f"\n[bold]Resuming {len(resumable)} upgrade(s)...[/bold]")
    for r in resumable:
        state = state_manager.get(r["arn"]) or {}
        remaining = r["upgrade_path"][state.get("step_idx", 0):]
        steps = " → ".join([r["current_version"]] + remaining)
        console.print(f"  {r['env']}/{r['name']}: {steps}")

    console.print()
    confirm = input("Resume polling these upgrades? [y/N]: ").strip().lower()
    if confirm != "y":
        console.print("[yellow]Aborted.[/yellow]")
        return

    poll_upgrades(resumable, state_manager, sessions)


def action_check_targets(
    config: dict,
    sessions: dict[str, SessionManager],
    envs: Optional[list[str]] = None,
) -> None:
    """Query AWS for valid upgrade targets and show reachability of configured targets.

    For each resource, fetches the current version then calls
    ``describe_db_engine_versions`` to list direct ``ValidUpgradeTarget``
    entries. Also runs the BFS path-finder and reports whether the configured
    ``target_version`` is directly reachable, reachable via intermediate hops,
    or not reachable at all.

    Args:
        config: Loaded configuration.
        sessions: Mapping of env → SessionManager.
        envs: Optional list of environment names to restrict to.
    """
    resources = (
        [r for r in config["resources"] if r["env"] in envs]
        if envs
        else config["resources"]
    )

    console.print("\n[bold]Querying ValidUpgradeTarget from AWS...[/bold]\n")

    table = Table(
        title="Valid Upgrade Targets",
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold magenta",
    )
    table.add_column("Env", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Engine")
    table.add_column("Current", style="yellow")
    table.add_column("Config Target", style="green")
    table.add_column("Direct Targets (AWS)")
    table.add_column("Reachable?")

    for resource in resources:
        env = resource["env"]
        label = f"{env}/{resource['name']}"
        engine_label = ENGINE_DISPLAY.get(resource["engine"], resource["engine"])
        configured_target = resource["target_version"]

        try:
            rds = sessions[env].rds()
            current = get_current_version(rds, resource)

            if current is None:
                table.add_row(
                    env, resource["name"], engine_label, "?", configured_target,
                    "[red]error[/red]", "[red]unknown[/red]",
                )
                continue

            # Fetch direct upgrade targets for the current version
            resp = rds.describe_db_engine_versions(
                Engine=resource["engine"],
                EngineVersion=current,
            )

            direct_targets: list[str] = []
            for version_info in resp.get("DBEngineVersions", []):
                for t in version_info.get("ValidUpgradeTarget", []):
                    direct_targets.append(t["EngineVersion"])

            direct_targets.sort()
            direct_str = ", ".join(direct_targets) if direct_targets else "[dim]none[/dim]"

            # Determine reachability of the configured target
            if current == configured_target:
                reachable_cell = "[green]✓ already there[/green]"
            elif configured_target in direct_targets:
                reachable_cell = "[green]✓ direct[/green]"
            else:
                path = get_upgrade_path(rds, resource["engine"], current, configured_target)
                if path:
                    hops = len(path)
                    hop_str = " → ".join(path)
                    reachable_cell = (
                        f"[yellow]~ {hops} hop{'s' if hops > 1 else ''}[/yellow]\n"
                        f"[dim]{hop_str}[/dim]"
                    )
                else:
                    reachable_cell = "[red]✗ no path found[/red]"

            table.add_row(
                env,
                resource["name"],
                engine_label,
                current,
                configured_target,
                direct_str,
                reachable_cell,
            )

        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in AUTH_ERROR_CODES:
                console.print(
                    f"  [yellow]Auth error for '{env}' profile — skipping {label}[/yellow]"
                )
                table.add_row(
                    env, resource["name"], engine_label, "?", configured_target,
                    "[yellow]auth error[/yellow]", "[yellow]unknown[/yellow]",
                )
            else:
                console.print(f"  [red]Error for {label}: {exc}[/red]")
                traceback.print_exc()
                table.add_row(
                    env, resource["name"], engine_label, "?", configured_target,
                    "[red]error[/red]", "[red]unknown[/red]",
                )

    console.print(table)


# ---------------------------------------------------------------------------
# Connection Testing
# ---------------------------------------------------------------------------


def _get_ssm_password(session_manager: SessionManager, ssm_name: str) -> Optional[str]:
    """Fetch a SecureString parameter from SSM Parameter Store.

    Args:
        session_manager: SessionManager for the resource's environment.
        ssm_name: SSM parameter name (e.g. "/dev/edgedb_external/postgres_password").

    Returns:
        Decrypted parameter value, or None on error.
    """
    try:
        ssm = session_manager.client("ssm")
        response = ssm.get_parameter(Name=ssm_name, WithDecryption=True)
        return response["Parameter"]["Value"]
    except ClientError as exc:
        console.print(f"  [red]SSM error fetching '{ssm_name}': {exc}[/red]")
        return None


def _test_pg_connection(host: str, port: int, user: str, password: str, dbname: str) -> tuple[bool, str]:
    """Attempt a PostgreSQL connection and return (success, detail).

    Args:
        host: Database hostname.
        port: Database port.
        user: Database username.
        password: Database password.
        dbname: Database name.

    Returns:
        Tuple of (success, detail_message).
    """
    try:
        import psycopg
    except ImportError:
        return False, "psycopg not installed — run: pip install 'psycopg[binary]'"

    try:
        conn = psycopg.connect(
            host=host, port=port, user=user, password=password,
            dbname=dbname, connect_timeout=10,
        )
        cur = conn.cursor()
        cur.execute("SELECT version();")
        row = cur.fetchone()
        conn.close()
        return True, row[0] if row else "connected (no version returned)"
    except Exception as exc:
        return False, str(exc)


def _test_mariadb_connection(host: str, port: int, user: str, password: str, database: str) -> tuple[bool, str]:
    """Attempt a MariaDB connection and return (success, detail).

    Args:
        host: Database hostname.
        port: Database port.
        user: Database username.
        password: Database password.
        database: Database name.

    Returns:
        Tuple of (success, detail_message).
    """
    try:
        import pymysql
    except ImportError:
        return False, "pymysql not installed — run: pip install pymysql"

    try:
        conn = pymysql.connect(
            host=host, port=port, user=user, password=password,
            database=database, connect_timeout=10,
        )
        cur = conn.cursor()
        cur.execute("SELECT VERSION();")
        row = cur.fetchone()
        conn.close()
        return True, row[0] if row else "connected (no version returned)"
    except Exception as exc:
        return False, str(exc)


def select_resource(config: dict) -> Optional[list[dict]]:
    """Prompt the user to select one or all resources that have connection_details.

    Args:
        config: Loaded configuration.

    Returns:
        List of selected resource dicts, or None if the user cancelled.
    """
    candidates = [r for r in config["resources"] if "connection_details" in r]

    if not candidates:
        console.print("[yellow]No resources have connection_details in config.[/yellow]")
        return None

    console.print("\n[bold]Select database to test:[/bold]")
    console.print("  [A] All")
    for i, r in enumerate(candidates, start=1):
        cd = r["connection_details"]
        engine_label = ENGINE_DISPLAY.get(r["engine"], r["engine"])
        console.print(
            f"  [{i}] {r['env']}/{r['name']}"
            f"  ({engine_label})"
            f"  {cd['host']}:{cd['port']}"
        )
    console.print("  [B] Back")

    choice = input("\nSelect: ").strip().upper()

    if choice == "B":
        return None
    if choice == "A":
        return candidates

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(candidates):
            return [candidates[idx]]
    except ValueError:
        pass

    console.print("[yellow]Invalid choice.[/yellow]")
    return None


def action_test_connections(
    config: dict,
    sessions: dict[str, SessionManager],
) -> None:
    """Test connectivity to selected databases by fetching passwords from SSM and connecting.

    Args:
        config: Loaded configuration.
        sessions: Mapping of env → SessionManager.
    """
    selected = select_resource(config)
    if selected is None:
        return

    console.print()

    table = Table(
        title="Database Connection Test Results",
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold magenta",
    )
    table.add_column("Env", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Engine")
    table.add_column("Host")
    table.add_column("DB")
    table.add_column("Result")
    table.add_column("Detail")

    for resource in selected:
        env = resource["env"]
        label = f"{env}/{resource['name']}"
        cd = resource["connection_details"]
        engine_label = ENGINE_DISPLAY.get(resource["engine"], resource["engine"])

        console.print(f"  Testing {label} ...")

        # Fetch password from SSM
        pwd_config = cd["password"]
        if pwd_config.get("type") != "ssm":
            table.add_row(
                env, resource["name"], engine_label, cd["host"], cd["database"],
                "[red]error[/red]", f"Unsupported password type: {pwd_config.get('type')}",
            )
            continue

        password = _get_ssm_password(sessions[env], pwd_config["name"])
        if password is None:
            table.add_row(
                env, resource["name"], engine_label, cd["host"], cd["database"],
                "[red]error[/red]", "Could not retrieve SSM parameter",
            )
            continue

        # Test the connection
        if resource["engine"] == "aurora-postgresql":
            success, detail = _test_pg_connection(
                cd["host"], cd["port"], cd["username"], password, cd["database"]
            )
        elif resource["engine"] == "mariadb":
            success, detail = _test_mariadb_connection(
                cd["host"], cd["port"], cd["username"], password, cd["database"]
            )
        else:
            success, detail = False, f"Unsupported engine: {resource['engine']}"

        result_cell = "[green]✓ connected[/green]" if success else "[red]✗ failed[/red]"
        # Truncate long version strings so the table stays readable
        detail_display = detail[:80] + "…" if len(detail) > 80 else detail

        table.add_row(
            env, resource["name"], engine_label,
            cd["host"], cd["database"],
            result_cell, detail_display,
        )

    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# Main Menu
# ---------------------------------------------------------------------------


def build_sessions(config: dict) -> dict[str, SessionManager]:
    """Build a SessionManager per environment using ARN-derived regions.

    Args:
        config: Loaded configuration.

    Returns:
        Mapping of env name → SessionManager.
    """
    profiles: dict[str, str] = config["aws_profiles"]
    resources: list[dict] = config["resources"]

    sessions: dict[str, SessionManager] = {}
    for env, profile in profiles.items():
        # Derive region from the first ARN in this env (all same-region assumption)
        region = next(
            (arn_region(r["arn"]) for r in resources if r["env"] == env),
            "us-east-1",
        )
        sessions[env] = SessionManager(profile=profile, region=region)

    return sessions


def main_menu(config: dict) -> None:
    """Display and handle the interactive main menu loop.

    Args:
        config: Loaded configuration.
    """
    sessions = build_sessions(config)
    state_manager = StateManager()

    while True:
        state_manager.reload()
        has_resumable = state_manager.has_resumable()
        resume_label = (
            "[bold]Resume pending upgrades[/bold] [yellow](available)[/yellow]"
            if has_resumable
            else "Resume pending upgrades [dim](none)[/dim]"
        )

        console.print()
        console.print(
            Panel.fit(
                "[bold cyan]          RDS Upgrade Manager          [/bold cyan]",
                subtitle="AWS RDS / Aurora version upgrades",
                box=box.DOUBLE_EDGE,
            )
        )
        console.print()
        console.print(f"  [1] List resources (fetch live versions from AWS)")
        console.print(f"  [2] Check valid upgrade targets (AWS reachability)")
        console.print(f"  [3] Plan upgrades (show steps, no changes)")
        console.print(f"  [4] Run upgrades")
        console.print(f"  [5] Dry run (plan + confirm messages, no AWS calls)")
        console.print(f"  [6] {resume_label}")
        console.print(f"  [7] Show saved status (no AWS calls)")
        console.print(f"  [8] Test DB connections")
        console.print(f"  [Q] Quit")
        console.print()

        choice = input("Select: ").strip().upper()
        console.print()

        if choice == "1":
            action_list(config, state_manager, sessions)

        elif choice == "2":
            available_envs = list(config["aws_profiles"].keys())
            selected = select_env(available_envs)
            if selected is not None:
                action_check_targets(config, sessions, envs=selected)

        elif choice == "3":
            available_envs = list(config["aws_profiles"].keys())
            selected = select_env(available_envs)
            if selected is not None:
                action_plan(config, state_manager, sessions, envs=selected, dry_run=True)

        elif choice == "4":
            action_upgrade(config, state_manager, sessions, dry_run=False)

        elif choice == "5":
            action_upgrade(config, state_manager, sessions, dry_run=True)

        elif choice == "6":
            action_resume(config, state_manager, sessions)

        elif choice == "7":
            console.print(build_status_table(config["resources"], state_manager))

        elif choice == "8":
            action_test_connections(config, sessions)

        elif choice == "Q":
            console.print("[dim]Bye.[/dim]")
            break

        else:
            console.print("[yellow]Invalid choice.[/yellow]")

        if choice not in ("Q",):
            input("\nPress Enter to continue...")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------


def load_config() -> dict:
    """Load and validate the configuration file.

    Returns:
        Parsed configuration dict.

    Raises:
        SystemExit: If the config file is missing or malformed.
    """
    if not CONFIG_FILE.exists():
        console.print(f"[red]Config file not found: {CONFIG_FILE}[/red]")
        sys.exit(1)

    with open(CONFIG_FILE) as f:
        config = json.load(f)

    missing = {"aws_profiles", "resources"} - set(config)
    if missing:
        console.print(f"[red]Config missing required keys: {missing}[/red]")
        sys.exit(1)

    return config


def main() -> None:
    """Entry point."""
    try:
        config = load_config()
        main_menu(config)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
