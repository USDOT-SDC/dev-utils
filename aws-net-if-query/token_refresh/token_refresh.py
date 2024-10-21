from awsquery import awsquery as q
from pathlib import Path
from os.path import expanduser
from datetime import datetime
import sys
from typing import Any
import requests
import configparser
import json
import yaml


def refresh_token_when_needed(env: str) -> None:
    """Refreshes the token when and if needed

    Args:
        env (str): the environment to refresh
    """
    base_path: Path = Path(__file__).parents[0]
    datetime_file: Path = base_path / f"last_token_refresh_{env}.txt"
    if not datetime_file.exists():
        with open(datetime_file, "w") as f:
            now: datetime = datetime.now()
            f.write(now.astimezone().replace(microsecond=0).isoformat())
            token_refresh(env)

    datetime_format = "%Y%m%dT%H:%M:%S-%Z"
    with open(datetime_file, "r") as f:
        date_str: str = f.readline()
        then: datetime = datetime.fromisoformat(date_str)

    now = datetime.now().astimezone()
    if (now - then).total_seconds() > 2700:
        with open(datetime_file, "w") as f:
            f.write(now.astimezone().replace(microsecond=0).isoformat())
            token_refresh(env)


def token_refresh(env: str) -> None:
    """Generates a new token refresh token

    Args:
        env (str): the environment to be used (dev, test, stage, prod)
    """
    # get the token refresh config
    base_path: Path = Path(__file__).parents[0]
    config_file_path: Path = base_path / f"config-{env}.yaml"
    config: Any = yaml.safe_load(config_file_path.read_text())
    api_endpoint: str = config.get("api_endpoint", "https://www.sample.com/generate_token")
    region_name: str = config.get("aws_config", None).get("region_name", "us-east-1")

    q.print_in_box(
        [
            "".ljust(80),
            f"{config.get("profile_name", None)} profile:",
            "Requesting new access keys and session token from...",
            f"{api_endpoint.split("?")[0]}",
            f"?{api_endpoint.split("?")[1]}",
            "",
        ],
        has_bottom=False,
        line="double",
    )

    # Requests credentials from token generator api
    response: requests.Response = requests.post(
        api_endpoint,
        data=json.dumps({}),
        headers={
            "Accept": "application/json",
            "x-api-key": config["api_key"],
        },
    )
    credentials: Any = response.json()
    if credentials.get("message"):
        sys.exit(f"The API responded with '{credentials.get("message")}'")

    q.print_in_box(
        [
            "".ljust(80),
            f'AccessKeyId: {credentials["AccessKeyId"]}',
            "",
        ],
        has_top=False,
        has_bottom=False,
        line="double",
    )

    # Update ~/.aws/credentials file
    home_path = Path(expanduser("~"))
    aws_path: Path = home_path / ".aws"
    aws_path.mkdir(parents=True, exist_ok=True)
    credentials_parser = configparser.RawConfigParser()
    credentials_file: Path = aws_path / "credentials"
    credentials_parser.read(credentials_file)

    if not credentials_parser.has_section(config["profile_name"]):
        credentials_parser.add_section(config["profile_name"])

    credentials_parser.set(
        config["profile_name"],
        "aws_access_key_id",
        credentials["AccessKeyId"],
    )
    credentials_parser.set(
        config["profile_name"],
        "aws_secret_access_key",
        credentials["SecretAccessKey"],
    )
    credentials_parser.set(
        config["profile_name"],
        "aws_session_token",
        credentials["SessionToken"],
    )

    with open(credentials_file, "w+") as f:
        credentials_parser.write(f)

    # Update ~/.aws/config file
    config_parser = configparser.RawConfigParser()
    config_file: Path = aws_path / "config"
    config_parser.read(config_file)

    if not config_parser.has_section("profile " + config["profile_name"]):
        config_parser.add_section("profile " + config["profile_name"])

    config_parser.set("profile " + config["profile_name"], "output", "json")
    config_parser.set("profile " + config["profile_name"], "region", region_name)

    with open(config_file, "w+") as f:
        config_parser.write(f)

    q.print_in_box(
        [
            "".ljust(80),
            f"Note: your AWS credentials will expire at {credentials['Expiration']}".ljust(80),
            "",
        ],
        has_top=False,
        line="double",
    )
