import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pathlib import Path
from functions import base_functions as bf
import sys
import yaml
import os
import json


def get_instance_info(env: str, tag_data):
    # get config
    config = bf.get_config(env)
    profile_name = config.get("profile_name", "default")
    # setup the session
    boto3.setup_default_session(profile_name=profile_name)
    region_name = config.get("aws_config", None).get("region_name", "us-east-1")
    aws_config = bf.get_aws_config(env)

    # get filters
    filters = tag_data.get("filters", []) or []
    # make filters only return instances
    filters.append({"Name": "resource-type", "Values": ["instance"]})
    # get create/delete tags
    create_tags = tag_data.get("create_tags", []) or []
    delete_tags = tag_data.get("delete_tags", []) or []

    try:
        instance_ids = set()
        instance_info = {}
        client = boto3.client("ec2", config=aws_config)
        paginator = client.get_paginator("describe_tags")
        for page in paginator.paginate(Filters=filters):
            # bf.dd(page.get("Tags"), True)
            for tags in page.get("Tags"):
                instance_ids.add(tags.get("ResourceId"))
            for instance_id in instance_ids:
                response = client.describe_tags(
                    Filters=[
                        {
                            "Name": "resource-id",
                            "Values": [instance_id],
                        },
                    ],
                )
                instance_tags = response.get("Tags")
                for instance_tag in instance_tags:
                    if instance_tag.get("Key") == "Name":
                        instance_info[instance_id] = {"Name": instance_tag.get("Value")}
                        response = client.create_tags(Resources=[instance_id], Tags=create_tags)
                        create_tags_update = {}
                        for tag in create_tags:
                            create_tags_update[tag.get("Key")] = tag.get("Value")
                            instance_info[instance_id].update({"create_tags": create_tags_update})
                        if delete_tags: # if delete_tags is empty, this will delete ALL tags!!
                            response = client.delete_tags(Resources=[instance_id], Tags=delete_tags)
                            delete_tags_update = {}
                            for tag in delete_tags:
                                delete_tags_update[tag.get("Key")] = tag.get("Value")
                                instance_info[instance_id].update({"delete_tags": delete_tags_update})

        return instance_info

    except ClientError as e:
        return {"Error": "Unexpected error: %s" % e}


def print_instance_info(instance_info) -> None:
    for instance_id, instance_data in instance_info.items():
        bf.print_in_box(
            [
                "".ljust(80),
                f"Instance ID:{instance_id}   Name:{instance_data.get('Name')}",
            ],
            has_bottom=False,
        )
        if instance_data.get("create_tags"):
            bf.print_in_box(
                [
                    "".ljust(80),
                    "   Created Tags:",
                ],
                has_bottom=False,
                has_top=False,
            )
            for key, value in instance_data.get("create_tags").items():
                bf.print_in_box(
                    [
                        f"      {key}:{value}".ljust(80),
                    ],
                    has_bottom=False,
                    has_top=False,
                )
        if instance_data.get("delete_tags"):
            bf.print_in_box(
                [
                    "".ljust(80),
                    "   Deleted Tags:",
                ],
                has_bottom=False,
                has_top=False,
            )
            for key, value in instance_data.get("delete_tags").items():
                bf.print_in_box(
                    [
                        f"      {key}:{value}".ljust(80),
                    ],
                    has_bottom=False,
                    has_top=False,
                )
        bf.print_in_box(
            [
                "".ljust(80),
            ],
            has_top=False,
        )