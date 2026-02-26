# RDS Upgrade Manager

A CLI tool for managing AWS RDS and Aurora version upgrades across multiple
environments. Features automatic upgrade-path calculation, crash-resilient
progress tracking, connection testing, and a menu-driven interface.

## Prerequisites

- Python 3.13+
- AWS CLI configured with named profiles (e.g. `sdc-dev`, `sdc-prod`)
- Network access to the RDS instances (required for connection tests only)
- SSM Parameter Store read access (required for connection tests only)

## Setup

```cmd
cd rds-utils
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```cmd
.venv\Scripts\activate
python rds_upgrade.py
```

## Configuration

All resource definitions live in `config.json`.

### Top-level structure

```json
{
    "aws_profiles": {
        "<env>": "<named-profile>"
    },
    "resources": [ ... ]
}
```

`aws_profiles` maps environment names to AWS CLI named profiles. The tool
creates a fresh `boto3.Session` per API call using the named profile, so
externally refreshed credentials (e.g. from an SSO helper) are always
picked up automatically.

### Resource definition

Each entry in `resources` describes one RDS cluster or instance:

```json
{
    "name":           "human-readable label",
    "env":            "dev | prod",
    "engine":         "aurora-postgresql | mariadb",
    "type":           "cluster | instance",
    "arn":            "arn:aws:rds:<region>:<account>:<type>:<id>",
    "target_version": "X.Y.Z",
    "connection_details": {
        "host":     "hostname.rds.amazonaws.com",
        "port":     5432,
        "username": "db_user",
        "database": "db_name",
        "password": {
            "type": "ssm",
            "name": "/path/to/ssm/parameter"
        }
    }
}
```

| Field | Required | Notes |
|---|---|---|
| `name` | Yes | Display label only — does not need to match the AWS identifier |
| `env` | Yes | Must match a key in `aws_profiles` |
| `engine` | Yes | `aurora-postgresql` or `mariadb` |
| `type` | Yes | `cluster` (Aurora) or `instance` (single RDS) |
| `arn` | Yes | Full ARN — region and account ID are derived from this |
| `target_version` | Yes | The final version you want the resource on |
| `connection_details` | No | Required only if you want to use the connection test |

`connection_details.password.type` currently supports `ssm` only. The named
parameter must be a `SecureString` readable by the profile's IAM role.

## Menu Reference

```text
[1] List resources               Fetch live engine versions from AWS and
                                 display a status table.

[2] Check valid upgrade targets  Query AWS ValidUpgradeTarget for each
                                 resource. Shows direct targets and whether
                                 the configured target_version is reachable
                                 (direct, N hops, or no path found).
                                 Run this before upgrading to verify your
                                 target versions are valid.

[3] Plan upgrades                Calculate upgrade paths without making any
                                 changes. Uses BFS over the AWS upgrade graph
                                 to find the fewest-hop path.

[4] Run upgrades                 Select environment → show plan → confirm →
                                 trigger upgrades → poll until complete.

[5] Dry run                      Same as Run, but no AWS modify calls are made.

[6] Resume pending upgrades      Reload saved state and continue monitoring
                                 any in-progress or pending upgrades. Use this
                                 after a crash or a Ctrl+C to pick up where
                                 you left off. Upgrades continue in AWS even
                                 if the script is not running.

[7] Show saved status            Display the current upgrade_state.json
                                 without calling AWS.

[8] Test DB connections          Select one or all databases, fetch passwords
                                 from SSM, and attempt a live connection.
                                 Reports the server version string on success.

[Q] Quit
```

## Upgrade Path Logic

AWS does not always allow jumping directly to a target version. The tool
uses a **breadth-first search** over the `ValidUpgradeTarget` graph returned
by `describe_db_engine_versions` to find the shortest hop path automatically.

Example: `13.20 → 17.7` might be a direct jump (AWS allows it) or require
intermediate stops like `13.x → 15.x → 17.7`. The plan step will show the
full path before asking for confirmation.

**Always run option `[2] Check valid upgrade targets` first** to confirm your
`target_version` is reachable before running upgrades.

## Progress Tracking

Upgrade state is persisted to `upgrade_state.json` after every step. If the
script crashes or is interrupted, the state file records exactly which
resources are in progress and which step they were on. Use `[6] Resume` to
continue.

The state file is plain JSON and can be hand-edited if needed (e.g. to reset
a `failed` resource back to `pending`). The script reloads the file from disk
at the top of every menu loop, so edits take effect immediately without
restarting.

### Resource statuses

| Status | Meaning |
|---|---|
| `not started` | Not yet planned |
| `pending` | Path calculated, waiting to kick off |
| `in_progress` | Upgrade triggered, polling for completion |
| `completed` | Reached target version |
| `skipped` | Already at target version |
| `failed` | AWS API error or no valid path found |

To retry a failed resource, set its `status` back to `pending` in
`upgrade_state.json` (ensure `upgrade_path` and `step_idx` are correct),
then use `[6] Resume`.

## AWS Credentials

The tool uses AWS named profiles configured in `~/.aws/credentials` or via
SSO. Credentials that rotate every 60 minutes are handled automatically —
a fresh `boto3.Session` is created on each API call, so the latest credentials
are always used without restarting the script.

If you see an auth error during polling, the tool logs it and retries on the
next poll cycle (every 60 seconds), giving the external credential refresher
time to rotate the token.

## Adding a New Resource

1. Add an entry to the `resources` array in `config.json`.
2. Run `[2] Check valid upgrade targets` to confirm the target version is reachable.
3. Run `[4] Run upgrades` and select the appropriate environment.

No other changes are needed. The tool derives the AWS region from the ARN
and the profile from the `env` → `aws_profiles` mapping.

## Troubleshooting

### `no path found` for a target version

The target version is not available for your engine in the region. Check the
AWS RDS console or run `[2] Check valid upgrade targets` to see what versions
are actually offered. Update `target_version` in `config.json` accordingly.

### `The AllowMajorVersionUpgrade flag must be present`

This was a known bug that has been fixed. If you see it, ensure you are
running the current version of `rds_upgrade.py`.

### `Connections using insecure transport are prohibited`

MariaDB 11.x enables `require_secure_transport=ON` by default. Either
configure the application to connect over SSL, or disable the requirement
via the RDS parameter group:

```cmd
aws rds modify-db-parameter-group ^
    --db-parameter-group-name <group-name> ^
    --parameters "ParameterName=require_secure_transport,ParameterValue=OFF,ApplyMethod=immediate" ^
    --profile <profile>
```

Find the parameter group name with:

```cmd
aws rds describe-db-instances ^
    --db-instance-identifier <instance-id> ^
    --profile <profile> ^
    --query "DBInstances[0].DBParameterGroups"
```

### Auth errors during polling

Expected during credential rotation. The tool retries automatically on the
next poll cycle. No action needed unless the error persists beyond 2–3 minutes.

### Resume picks up zero resources

The script reloads `upgrade_state.json` from disk at each menu prompt. If you
edited the state file while the script was running, it will be picked up the
next time you return to the main menu — no restart required.
