import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pathlib import Path
import sys
import yaml
import os
import json


def cls() -> None:
    """Clears the screen of any command interface"""
    os.system("cls" if os.name == "nt" else "clear")


def dd(data: any, debug: bool = False) -> None:
    """Dumps any variable data as a readable json

    Args:
        data (any): any data or object
        debug (bool, optional): Turns the function on or off. Defaults to False.
    """
    if debug:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def print_in_box(strings: list[str], line: str = "single", has_top: bool = True, has_bottom: bool = True) -> None:
    max_len = 0
    for string in strings:
        str_len = len(string) + 1
        if str_len > max_len:
            max_len = str_len
    box_draw_chars = {
        "single": {
            "se": "┘",
            "ne": "┐",
            "nw": "┌",
            "sw": "└",
            "h": "─",
            "v": "│",
        },
        "double": {
            "se": "╝",
            "ne": "╗",
            "nw": "╔",
            "sw": "╚",
            "h": "═",
            "v": "║",
        },
    }
    se = box_draw_chars.get(line).get("se")
    ne = box_draw_chars.get(line).get("ne")
    nw = box_draw_chars.get(line).get("nw")
    sw = box_draw_chars.get(line).get("sw")
    h = box_draw_chars.get(line).get("h")
    v = box_draw_chars.get(line).get("v")
    h_line = (h * max_len) + h
    if has_top:
        print(f"\n {nw}{h_line}{ne}")
    for string in strings:
        print(f" {v} {string.ljust(max_len)}{v}")
    if has_bottom:
        print(f" {sw}{h_line}{se}\n")


def get_account_id() -> str:
    """Gets the account ID from the Security Token Service

    Returns:
        string: Account ID
    """
    return boto3.client("sts").get_caller_identity().get("Account")


def get_aws_config(env: str) -> Config:
    """Get the AWS configuration

    Args:
        env (str): the environment (dev, test, stage, prod)

    Returns:
        Config: AWS Config object
    """
    config = get_config(env)
    aws_config = config.get("aws_config", None)
    aws_config = Config(
        region_name=aws_config.get("region_name", "us-east-1"),
        retries=aws_config.get("retries", {}),
    )
    return aws_config


def get_config(env: str) -> dict[str | dict[str, str]]:
    config_file_path = Path(f"token_refresh/config-{env}.yaml")
    return yaml.safe_load(config_file_path.read_text())
