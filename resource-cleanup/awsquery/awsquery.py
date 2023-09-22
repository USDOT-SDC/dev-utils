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


def get_volumes(env: str, debug: bool) -> list[dict[str, str | bool]]:
    """Gets a list of volumes with basic information about where/why they exist

    Args:
        env (str): the environment (dev, test, stage, prod)
        debug (bool): turns on debugging

    Returns:
        list[dict[str, str | bool]]: list of the volumes with basic information
    """
    # get config
    config = get_config(env)
    profile_name = config.get("profile_name", "default")
    region_name = config.get("aws_config", None).get("region_name", "us-east-1")
    aws_config = get_aws_config(env)
    print_in_box(
        [
            "".ljust(80),
            f"get_volumes({env}, {debug})",
            "",
            "running...",
            "",
        ],
        has_bottom=False,
        line="double",
    )
    # setup the session
    boto3.setup_default_session(profile_name=profile_name)
    # create an EC2 client
    client = boto3.client("ec2", config=aws_config)
    # get an iterator for describe_volumes
    response_iterator = client.get_paginator("describe_volumes").paginate(
        Filters=[
            {
                "Name": "status",
                "Values": [
                    "creating",
                    "available",
                    # "in-use",
                    "deleting",
                    "deleted",
                    "error",
                ],
            },
        ]
    )
    volumes = []
    # Iterate through the paginated responses to get total volume count
    v_count = 0
    v_idx = 0
    for response in response_iterator:
        if "Volumes" in response:
            v_count += len(response["Volumes"])
    # iterate the pages and volumes
    for p_idx, page in enumerate(response_iterator):
        page_volumes = page.get("Volumes")
        for v_idx, volume in enumerate(page_volumes):
            tags = get_tags(volume.get("Tags"))
            print_in_box(
                [
                    "".ljust(80, "─"),
                    f"Name:{tags.get('Name')}".ljust(80),
                    f"   Project:{tags.get('Project')}".ljust(80),
                    f"  VolumeId:{volume.get('VolumeId')}".ljust(80),
                    f"     State:{volume.get('State')}".ljust(80),
                ],
                has_top=False,
                has_bottom=False,
                line="double",
            )
            volumes.append(volume)
            v_idx += 1
            if v_count == v_idx:
                print_in_box(["".ljust(80, "─")], has_top=False, has_bottom=False, line="double")
    if not volumes:
        print_in_box(
            [
                f"All volumes are in-use.".ljust(80),
            ],
            has_top=False,
            has_bottom=False,
            line="double",
        )
    print_in_box(
        [
            "",
            "Done!",
            "".ljust(80),
        ],
        has_top=False,
        line="double",
    )
    return volumes


def get_tags(tags: list[dict[str, str]] | dict[str, str]) -> dict[str, str]:
    """Gets a dictionary of the Name and Project tags from the list of tags

    Args:
        tags (list[dict[str, str]]): the list of tags from the client response

    Returns:
        dict[str, str]: the dictionary of the Name and Project tags
    """
    name = ""
    project = ""
    if type(tags) == list:
        for tag in tags:
            if tag["Key"] == "Name":
                name = tag["Value"]
            elif tag["Key"] == "Project":
                project = tag["Value"]
    elif type(tags) == dict:
        name = tags.get("Name", "")
        project = tags.get("Project", "")
    return {"Name": name, "Project": project}
