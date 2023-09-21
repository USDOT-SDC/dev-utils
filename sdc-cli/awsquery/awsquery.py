import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pathlib import Path
import sys
import yaml
import os
import json


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


def get_instances(env: str, states: list[str]) -> list[dict[str, str]]:
    instances = []
    config = get_config(env)
    profile_name = config.get("profile_name", "default")
    boto3.setup_default_session(profile_name=profile_name)
    client = boto3.client("ec2", config=get_aws_config(env))
    if states:
        response = client.describe_instances(
            Filters=[
                {
                    "Name": "instance-state-name",
                    "Values": states,
                },
            ],
            MaxResults=1000,
        )
    else:
        response = client.describe_instances(MaxResults=1000)
    for reservation in response.get("Reservations"):
        for instance in reservation.get("Instances"):
            tags = instance.get("Tags")
            name = get_tag_value(tags, "Name")
            instance["Name"] = name
            instance["State"] = instance.get("State").get("Name")
            instances.append(instance)
    instances = sorted(instances, key=lambda k: k["Name"])
    for idx, instance in enumerate(instances):
        instances[idx]["IDX"] = idx
    return instances


def get_tag_value(tags: list[dict[str, str]], key: str) -> str:
    for tag in tags:
        if tag.get("Key") == key:
            return tag.get("Value")
    return ""


def start_instance(env: str, instance_id: str) -> dict[str, str]:
    instances = []
    config = get_config(env)
    profile_name = config.get("profile_name", "default")
    boto3.setup_default_session(profile_name=profile_name)
    client = boto3.client("ec2", config=get_aws_config(env))
    response = client.start_instances(InstanceIds=[instance_id])
    instance = response.get("StartingInstances")[0]
    instance = {
        "InstanceId": instance.get("InstanceId"),
        "CurrentState": instance.get("CurrentState").get("Name"),
        "PreviousState": instance.get("PreviousState").get("Name"),
    }
    return instance


def stop_instance(env: str, instance_id: str) -> dict[str, str]:
    instances = []
    config = get_config(env)
    profile_name = config.get("profile_name", "default")
    boto3.setup_default_session(profile_name=profile_name)
    client = boto3.client("ec2", config=get_aws_config(env))
    response = client.stop_instances(InstanceIds=[instance_id])
    instance = response.get("StoppingInstances")[0]
    instance = {
        "InstanceId": instance.get("InstanceId"),
        "CurrentState": instance.get("CurrentState").get("Name"),
        "PreviousState": instance.get("PreviousState").get("Name"),
    }
    return instance
