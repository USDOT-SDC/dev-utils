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


def get_net_interfaces(env: str, debug: bool) -> list[dict[str, str | bool]]:
    """Gets a list of network interfaces with basic information about where/why they exist

    Args:
        env (str): the environment (dev, test, stage, prod)
        debug (bool): turns on debugging

    Returns:
        list[dict[str, str | bool]]: list of the network interfaces with basic information
    """
    # get config
    config = get_config(env)
    profile_name = config.get("profile_name", "default")
    region_name = config.get("aws_config", None).get("region_name", "us-east-1")
    aws_config = get_aws_config(env)
    print_in_box(
        [
            "".ljust(80),
            f"get_net_interfaces(profile_name={profile_name}, debug={debug})",
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
    # get an iterator for describe_network_interfaces
    response_iterator = client.get_paginator("describe_network_interfaces").paginate()
    network_interfaces = []
    # iterate the pages and network interfaces
    for page in response_iterator:
        page_network_interfaces = page["NetworkInterfaces"]
        for idx, network_interface in enumerate(page_network_interfaces):
            # only look at interfaces w/attachments
            if "Attachment" in network_interface:
                dd(f"Found network interface with ID: {network_interface['NetworkInterfaceId']}", debug)
                interface_id = network_interface["NetworkInterfaceId"]
                interface_type = network_interface["InterfaceType"]
                requester_managed = network_interface.get("RequesterManaged")
                requester_id = network_interface.get("RequesterId", "")
                mac_address = network_interface["MacAddress"]
                description = network_interface["Description"]
                instance_id = network_interface["Attachment"].get("InstanceId")
                attachment_info = {"AttachmentToId": ""}
                # this if/else statement sorts out the odd ways that AWS identifies the where and why of an interface
                # for interfaces that are automatically created/managed by an AWS service
                if requester_managed:
                    # application ELBs
                    if requester_id == "amazon-elb":
                        description_split = description.split("/")
                        lb_type = description_split[0][4:7]
                        attachment_info = {"RequesterId": f"amazon-elb-{lb_type}", "AttachmentToId": description_split[1]}
                    # Redshift
                    elif requester_id == "amazon-redshift":
                        attachment_info = {"RequesterId": "amazon-redshift", "AttachmentToId": "amazon-redshift"}
                    # network ELBs
                    elif interface_type == "network_load_balancer":
                        description_split = description.split("/")
                        attachment_info = {"RequesterId": "amazon-elb-net", "AttachmentToId": description_split[1]}
                    # gateway ELBs (we don't use these)
                    elif interface_type == "gateway_load_balancer":
                        description_split = description.split("/")
                        attachment_info = {"RequesterId": "amazon-elb-gwy", "AttachmentToId": description_split[1]}
                    # VPC Endpoints
                    elif interface_type == "vpc_endpoint":
                        start = description.find("vpce-")
                        vpc_endpoint_id = description[start : start + 22]
                        attachment_info = {"RequesterId": "amazon-vpce", "AttachmentToId": vpc_endpoint_id}
                    # Relational Database Service (RDS)
                    elif description == "RDSNetworkInterface":
                        attachment_info = {"RequesterId": "amazon-rds", "AttachmentToId": "amazon-rds"}
                    # EFS Volumes
                    elif description.startswith("EFS mount target for"):
                        start = description.find("fs-")
                        file_system_id = description[start : start + 20]
                        attachment_info = {"RequesterId": "amazon-efs", "AttachmentToId": file_system_id}
                # for interfaces that are not created/managed by an AWS service
                else:
                    # EC2 instances
                    if instance_id:
                        attachment_info = {"RequesterId": "ec2", "AttachmentToId": instance_id}
                    # Lambda Functions
                    elif interface_type == "lambda":
                        function_name = description[19:-37]
                        attachment_info = {"RequesterId": "lambda", "AttachmentToId": function_name}
                    # Transit Gateway Attachments
                    elif interface_type == "transit_gateway":
                        start = description.find("tgw-attach-")
                        tgw_attach_id = description[start : start + 28]
                        attachment_info = {"RequesterId": "tgw", "AttachmentToId": tgw_attach_id}
                # add the attachment_info to the basic network interface info
                ni_data = {
                    "NetworkInterfaceId": interface_id,
                    "InterfaceType": interface_type,
                    "RequesterManaged": requester_managed,
                    "RequesterId": requester_id,
                    "MacAddress": mac_address,
                    "Description": description,
                } | attachment_info
                # the relationship of interface to IP address can be, but usually is not, a one-to-many
                # so we get a list of the IP addresses and iterate them so there's an item for each IP address
                private_ip_addresses = get_private_ip_addresses(network_interface["PrivateIpAddresses"], debug)
                for private_ip_address in private_ip_addresses:
                    dd(f"                   IPv4 address: {private_ip_address}", debug)
                    ni_data = ni_data | {"PrivateIpAddress": private_ip_address}
                    dd(ni_data, debug)
                    network_interfaces.append(ni_data)
    print_in_box(
        [
            "Done!",
            "".ljust(80),
        ],
        has_top=False,
        line="double",
    )
    return network_interfaces


def get_private_ip_addresses(private_ip_addresses: list[dict[str, str]], debug: bool) -> list[str]:
    """Gets a list of just the private IP addresses from the private_ip_addresses dictionary

    Args:
        private_ip_addresses (list[dict[str, str]]): the list of dict returned by the describe_network_interfaces response_iterator
        debug (bool): turns debugging on/off

    Returns:
        list[str]: a list of strings representing the IP addresses of the network interface
    """
    just_private_ip_address = []
    for private_ip_address in private_ip_addresses:
        just_private_ip_address.append(private_ip_address.get("PrivateIpAddress"))
    return just_private_ip_address


def get_net_interface_details(network_interfaces: list[dict[str, str | bool]], env: str, debug: bool) -> list[dict[str, str | bool]]:
    """Gets additional attachment info for the list of network interfaces

    Args:
        network_interfaces (list[dict[str, str  |  bool]]): list of the network interfaces with basic information
        env (str): the environment (dev, test, stage, prod)
        debug (bool): turns on debugging

    Returns:
        list[dict[str, str | bool]]: list of the network interfaces with additional attachment info
    """
    # get config
    config = get_config(env)
    profile_name = config.get("profile_name", "default")
    region_name = config.get("aws_config", None).get("region_name", "us-east-1")
    aws_config = get_aws_config(env)
    print_in_box(
        [
            "".ljust(80),
            f"get_net_interface_details(network_interfaces, profile_name={profile_name}, debug={debug})",
            "",
            "running...",
            "",
        ],
        line="double",
    )
    # setup the session
    boto3.setup_default_session(profile_name=profile_name)
    # iterate the network interfaces
    for idx, network_interface in enumerate(network_interfaces):
        if debug:
            print("\n\n")
        # dd(network_interface, debug)
        interface_id = network_interface["NetworkInterfaceId"]
        interface_type = network_interface["InterfaceType"]
        requester_managed = network_interface["RequesterManaged"]
        requester_id = network_interface["RequesterId"]
        attachment_to_id = network_interface["AttachmentToId"]
        mac_address = network_interface["MacAddress"]
        ip_address = network_interface["PrivateIpAddress"]
        ip_address_segments = ip_address.split(".")
        description = network_interface["Description"]
        # this if/else classifies interfaces based on the odd ways that AWS identifies the where and why of the interface
        # for interfaces that are automatically created/managed by an AWS service
        # this section uses several similar functions, get_{service}_info(attachment_to_id)
        # each of these functions use a different boto3 client, and handle parameters/returns with slight differences
        if requester_managed:
            dd("Requester Managed...", debug=debug)
            # EFS Volumes
            if interface_type == "efs" or (interface_type == "interface" and requester_id == "amazon-efs"):
                dd("EFS network interface", debug=debug)
                info = get_efs_info(attachment_to_id, aws_config=aws_config)
                info["Name"] = f"{info['Name']} {ip_address_segments[2]}.{ip_address_segments[3]}"
                network_interfaces[idx] = network_interface | info
            # interface of type=interface
            elif interface_type == "interface":
                # Gateway and Application ELBs
                if requester_id.startswith("amazon-elb-"):
                    dd(f"ELB-{requester_id[-3:]} network interface", debug=debug)
                    info = get_load_balancer_info(attachment_to_id, requester_id[-3:], aws_config=aws_config)
                    info["Name"] = f"{info['Name']} {ip_address_segments[2]}.{ip_address_segments[3]}"
                    network_interfaces[idx] = network_interface | info
                # Relational Database Service (RDS)
                elif requester_id == "amazon-rds":
                    dd("RDS network interface", debug=debug)
                    info = {
                        "Name": f"RDS {ip_address_segments[2]}.{ip_address_segments[3]}",
                        "Project": "Platform",
                        "AWS": "RDS",
                    }
                    network_interfaces[idx] = network_interface | info
                # Redshift
                elif requester_id == "amazon-redshift":
                    dd("RDS network interface", debug=debug)
                    info = {
                        "Name": f"Redshift {ip_address_segments[2]}.{ip_address_segments[3]}",
                        "Project": "Platform",
                        "AWS": "Redshift",
                    }
                    network_interfaces[idx] = network_interface | info
                # for an unknown interface type we didn't find in testing
                else:
                    dd("Unknown network interface: interface_type == 'interface'", True)
                    dd(network_interfaces[idx], True)
                    sys.exit()
            # Network ELBs
            elif interface_type == "network_load_balancer":
                dd(f"ELB-{requester_id[-3:]} network interface", debug=debug)
                info = get_load_balancer_info(attachment_to_id, requester_id[-3:], aws_config=aws_config)
                info["Name"] = f"{info['Name']} {ip_address_segments[2]}.{ip_address_segments[3]}"
                network_interfaces[idx] = network_interface | info
            # VPC Endpoints
            elif interface_type == "vpc_endpoint":
                dd("VPC Endpoint network interface", debug=debug)
                info = get_vpc_endpoint_info(attachment_to_id, aws_config=aws_config)
                info["Name"] = f"{info['Name']} {ip_address_segments[2]}.{ip_address_segments[3]}"
                network_interfaces[idx] = network_interface | info
            # for an unknown requester_managed interface we didn't find in testing
            else:
                dd("Unknown network interface: requester_managed", True)
                dd(network_interfaces[idx], True)
                sys.exit()
        # for interfaces that are not created/managed by an AWS service
        else:
            dd("Not Requester Managed...", debug=debug)
            # EC2s
            if interface_type == "interface" and requester_id == "ec2":
                dd("EC2 network interface", debug=debug)
                info = get_instance_info(attachment_to_id, aws_config=aws_config)
                network_interfaces[idx] = network_interface | info
            # Lambdas
            elif interface_type == "lambda":
                dd("Lambda network interface", debug=debug)
                info = get_lambda_info(attachment_to_id, aws_config=aws_config)
                # most Lambda's don't have a Name tag
                if not info["Name"]:
                    info["Name"] = f"{attachment_to_id}"
                info["Name"] = f"{info['Name']} {ip_address_segments[2]}.{ip_address_segments[3]}"
                network_interfaces[idx] = network_interface | info
            # VPC Endpoints
            elif interface_type == "vpc_endpoint":
                dd("VPC Endpoint network interface", debug=debug)
                info = get_vpc_endpoint_info(attachment_to_id, aws_config=aws_config)
                info["Name"] = f"{info['Name']} {ip_address_segments[2]}.{ip_address_segments[3]}"
                network_interfaces[idx] = network_interface | info
            # Transit Gateway Attachments
            elif interface_type == "transit_gateway":
                dd("Transit Gateway network interface", debug=debug)
                info = get_transit_gateway_attachment_info(attachment_to_id, aws_config=aws_config)
                info["Name"] = f"{info['Name']} {ip_address_segments[2]}.{ip_address_segments[3]}"
                network_interfaces[idx] = network_interface | info
            else:
                dd("Unknown network interface: !requester_managed", True)
                dd(network_interfaces[idx], True)
                sys.exit()
        dd(network_interfaces[idx], debug)
        if not network_interfaces[idx].get("AWS", False):
            dd(network_interfaces[idx], True)
            sys.exit()
        ljust_num = 80
        print_in_box(
            [
                f"         ID: {interface_id}".ljust(ljust_num),
                f"MAC Address: {mac_address}".ljust(ljust_num),
                f" IP Address: {ip_address}".ljust(ljust_num),
                f"        AWS: {network_interfaces[idx]['AWS']}".ljust(ljust_num),
                f"       Name: {network_interfaces[idx]['Name']}".ljust(ljust_num),
            ]
        )
    print_in_box(
        [
            "".ljust(80),
            f"get_net_interface_details(network_interfaces, profile_name={profile_name}, debug={debug})",
            "",
            "Done!",
            "",
        ],
        line="double",
    )
    return network_interfaces


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


def get_instance_info(instance_id: str, aws_config: Config) -> dict[str, str]:
    """Gets the Name and Project tags of a given instance

    Args:
        instance_id (str): the instance identifier
        aws_config (Config): the aws configuration

    Returns:
        dict[str, str]: the Name and Project tags of a given instance
    """
    # print(f"get_instance_info({instance_id})")
    client = boto3.client("ec2", config=aws_config)
    try:
        response = client.describe_instances(InstanceIds=[instance_id])
        tags = response["Reservations"][0]["Instances"][0].get("Tags", [])
        return get_tags(tags) | {"AWS": "EC2"}
    except ClientError as e:
        return {"Name": instance_id, "Error": "Unexpected error: %s" % e}


def get_efs_info(file_system_id: str, aws_config: Config) -> dict[str, str]:
    """Gets the Name and Project tags of a given EFS Volume

    Args:
        file_system_id (str): the file system identifier
        aws_config (Config): the aws configuration

    Returns:
        dict[str, str]: the Name and Project tags of a given EFS Volume
    """
    # print(f"get_efs_info({file_system_id})")
    client = boto3.client("efs", config=aws_config)
    try:
        response = client.describe_file_systems(FileSystemId=file_system_id)
        tags = response["FileSystems"][0].get("Tags", [])
        return get_tags(tags) | {"AWS": "EFS"}
    except ClientError as e:
        return {"Name": file_system_id, "Error": "Unexpected error: %s" % e}


def get_vpc_endpoint_info(vpc_endpoint_id: str, aws_config: Config) -> dict[str, str]:
    """Gets the Name and Project tags of a given VPC Endpoint

    Args:
        vpc_endpoint_id (str): the VPC identifier
        aws_config (Config): the aws configuration

    Returns:
        dict[str, str]: the Name and Project tags of a given VPC Endpoint
    """
    # print(f"get_vpc_endpoint_info({vpc_endpoint_id})")
    client = boto3.client("ec2", config=aws_config)
    try:
        response = client.describe_vpc_endpoints(VpcEndpointIds=[vpc_endpoint_id])
        tags = response["VpcEndpoints"][0].get("Tags", [])
        return get_tags(tags) | {"AWS": "VPCE"}
    except ClientError as e:
        return {"Name": vpc_endpoint_id, "Error": "Unexpected error: %s" % e}


def get_lambda_info(function_name: str, aws_config: Config) -> dict[str, str]:
    """Gets the Name and Project tags of a given Lambda function

    Args:
        function_name (str): the function name
        aws_config (Config): the aws configuration

    Returns:
        dict[str, str]: the Name and Project tags of a given Lambda function
    """
    # print(f"get_lambda_info({function_name})")
    client = boto3.client("lambda", config=aws_config)
    try:
        response = client.get_function(FunctionName=function_name)
        tags = response.get("Tags", [])
        return get_tags(tags) | {"AWS": "Lambda"}
    except ClientError as e:
        return {"Name": function_name, "Error": "Unexpected error: %s" % e}


def get_load_balancer_info(lb_name: str, lb_type: str, aws_config: Config) -> dict[str, str]:
    """Gets the Name and Project tags of a given load balancer

    Args:
        lb_name (str): the load balancer name
        lb_type (str): the load balancer type (app, net, gwy)
        aws_config (Config): the aws configuration

    Returns:
        dict[str, str]: the Name and Project tags of a given load balancer
    """
    # print(f"get_load_balancer_info({lb_name}, {lb_type})")
    client = boto3.client("elbv2", config=aws_config)
    try:
        dlb_response = client.describe_load_balancers(Names=[lb_name])
        lb_arn = dlb_response["LoadBalancers"][0].get("LoadBalancerArn")
        dt_response = client.describe_tags(ResourceArns=[lb_arn])
        tags = dt_response["TagDescriptions"][0].get("Tags", [])
        return get_tags(tags) | {"AWS": f"ELB-{lb_type.upper()}"}
    except ClientError as e:
        return {"Name": lb_name, "Error": "Unexpected error: %s" % e}


def get_transit_gateway_attachment_info(transit_gateway_attachment_id: str, aws_config: Config) -> dict[str, str]:
    """Gets the Name and Project tags of a given transit gateway attachment

    Args:
        transit_gateway_attachment_id (str): the transit gateway attachment identifier
        aws_config (Config): the aws configuration

    Returns:
        dict[str, str]: the Name and Project tags of a given transit gateway attachment
    """
    # print(f"get_transit_gateway_attachment_info({transit_gateway_attachment_id})")
    client = boto3.client("ec2", config=aws_config)
    try:
        tgwa_response = client.describe_transit_gateway_attachments(TransitGatewayAttachmentIds=[transit_gateway_attachment_id])
        tags = tgwa_response["TransitGatewayAttachments"][0].get("Tags", [])
        return get_tags(tags) | {"AWS": "TGWA"}
    except ClientError as e:
        return {"Name": function_name, "Error": "Unexpected error: %s" % e}
