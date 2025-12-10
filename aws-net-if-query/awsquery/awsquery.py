import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pathlib import Path
from typing import Any
import sys
import os
import json


def cls() -> None:
    """Clears the screen of any command interface"""
    os.system("cls" if os.name == "nt" else "clear")


def dd(data: Any, debug: bool = False) -> None:
    """Dumps any variable data as a readable json

    Args:
        data (Any): any data or object
        debug (bool, optional): Turns the function on or off. Defaults to False.
    """
    if debug:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def print_in_box(strings: list[str], line: str = "single", has_top: bool = True, has_bottom: bool = True) -> None:
    """Prints text in a fancy box with unicode borders

    Args:
        strings (list[str]): List of strings to print in the box
        line (str, optional): Border style - "single" or "double". Defaults to "single".
        has_top (bool, optional): Whether to draw top border. Defaults to True.
        has_bottom (bool, optional): Whether to draw bottom border. Defaults to True.
    """
    max_len = max(len(string) for string in strings)
    
    box_draw_chars = {
        "single": {"se": "┘", "ne": "┐", "nw": "┌", "sw": "└", "h": "─", "v": "│"},
        "double": {"se": "╝", "ne": "╗", "nw": "╔", "sw": "╚", "h": "═", "v": "║"},
    }
    
    chars = box_draw_chars[line]
    h_line = chars["h"] * (max_len + 2)
    
    if has_top:
        print(f"\n {chars['nw']}{h_line}{chars['ne']}")
    
    for string in strings:
        print(f" {chars['v']} {string.ljust(max_len)} {chars['v']}")
    
    if has_bottom:
        print(f" {chars['sw']}{h_line}{chars['se']}\n")


def get_aws_config(region: str) -> Config:
    """Get the AWS configuration

    Args:
        region (str): AWS region name

    Returns:
        Config: AWS Config object
    """
    return Config(
        region_name=region,
        retries={"max_attempts": 3, "mode": "standard"},
    )


def get_net_interfaces(profile_name: str, region: str, debug: bool = False) -> list[dict]:
    """Gets a list of network interfaces with basic information about where/why they exist

    Args:
        profile_name (str): AWS profile name to use
        region (str): AWS region name
        debug (bool, optional): Turns on debugging. Defaults to False.

    Returns:
        list[dict]: list of the network interfaces with basic information
    """
    aws_config = get_aws_config(region)
    print_in_box(
        [
            "".ljust(80),
            f"get_net_interfaces(profile_name={profile_name}, region={region}, debug={debug})",
            "",
            "running...",
            "",
        ],
        has_bottom=False,
        line="double",
    )
    
    # Setup the session
    boto3.setup_default_session(profile_name=profile_name)
    
    # Create an EC2 client
    client = boto3.client("ec2", config=aws_config)
    
    # Get an iterator for describe_network_interfaces
    response_iterator = client.get_paginator("describe_network_interfaces").paginate()
    network_interfaces = []
    
    # Iterate the pages and network interfaces
    for page in response_iterator:
        page_network_interfaces = page["NetworkInterfaces"]
        for network_interface in page_network_interfaces:
            # Only look at interfaces w/attachments
            if "Attachment" not in network_interface:
                continue
            
            dd(f"Found network interface with ID: {network_interface['NetworkInterfaceId']}", debug)
            
            interface_id = network_interface["NetworkInterfaceId"]
            interface_type = network_interface["InterfaceType"]
            requester_managed = network_interface.get("RequesterManaged")
            requester_id = network_interface.get("RequesterId", "")
            private_ip_address: str = network_interface["PrivateIpAddress"]
            mac_address = network_interface["MacAddress"]
            description = network_interface["Description"]
            instance_id = network_interface["Attachment"].get("InstanceId")
            attachment_info = {"AttachmentToId": ""}
            
            # Sort out the odd ways that AWS identifies where and why an interface exists
            # For interfaces that are automatically created/managed by an AWS service
            if requester_managed:
                # Application ELBs
                if requester_id == "amazon-elb":
                    description_split = description.split("/")
                    lb_type = description_split[0][4:7]
                    attachment_info = {"RequesterId": f"amazon-elb-{lb_type}", "AttachmentToId": description_split[1]}
                # Redshift
                elif requester_id == "amazon-redshift":
                    attachment_info = {"RequesterId": "amazon-redshift", "AttachmentToId": "amazon-redshift"}
                # Network ELBs
                elif interface_type == "network_load_balancer":
                    description_split = description.split("/")
                    attachment_info = {"RequesterId": "amazon-elb-net", "AttachmentToId": description_split[1]}
                # Gateway ELBs
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
                # Directories
                elif description.startswith("AWS created network interface for directory d-"):
                    directory_id = description[-12:]
                    attachment_info = {"RequesterId": "amazon-directory", "AttachmentToId": directory_id}
                # Cross-account
                elif interface_type == "interface" and requester_id.isdigit():
                    attachment_info = {"RequesterId": "cross-account", "AttachmentToId": requester_id}
            # For interfaces that are not created/managed by an AWS service
            else:
                # EC2 instances
                if instance_id:
                    attachment_info = {"RequesterId": "ec2", "AttachmentToId": instance_id}
                # Workspaces
                elif interface_type == "interface" and requester_id[-18:] == "WorkSpace-Creation":
                    attachment_info = {"RequesterId": "WorkSpace-Creation", "AttachmentToId": private_ip_address}
                # Lambda Functions
                elif interface_type == "lambda":
                    attachment_info = {"RequesterId": "lambda", "AttachmentToId": "Lambda"}
                # Transit Gateway Attachments
                elif interface_type == "transit_gateway":
                    start = description.find("tgw-attach-")
                    tgw_attach_id = description[start : start + 28]
                    attachment_info = {"RequesterId": "tgw", "AttachmentToId": tgw_attach_id}
            
            # Add the attachment_info to the basic network interface info
            ni_data = {
                "NetworkInterfaceId": interface_id,
                "InterfaceType": interface_type,
                "RequesterManaged": requester_managed,
                "RequesterId": requester_id,
                "MacAddress": mac_address,
                "Description": description,
            } | attachment_info
            
            # The relationship of interface to IP address can be (but usually is not) one-to-many
            # Get a list of the IP addresses and iterate them so there's an item for each IP address
            private_ip_addresses = get_private_ip_addresses(network_interface["PrivateIpAddresses"], debug)
            for private_ip_address in private_ip_addresses:
                dd(f"                   IPv4 address: {private_ip_address}", debug)
                ni_data = ni_data | {"PrivateIpAddress": private_ip_address}
                dd(ni_data, debug)
                network_interfaces.append(ni_data)
    
    print_in_box(["Done!", "".ljust(80)], has_top=False, line="double")
    return network_interfaces


def get_private_ip_addresses(private_ip_addresses: list[dict[str, str]], debug: bool) -> list[str]:
    """Gets a list of just the private IP addresses from the private_ip_addresses dictionary

    Args:
        private_ip_addresses (list[dict[str, str]]): List of dict returned by describe_network_interfaces
        debug (bool): Turns debugging on/off

    Returns:
        list[str]: List of IP address strings
    """
    return [ip["PrivateIpAddress"] for ip in private_ip_addresses]


def get_net_interface_details(
    network_interfaces: list[dict], 
    profile_name: str, 
    region: str, 
    debug: bool = False
) -> list[dict]:
    """Gets additional attachment info for the list of network interfaces

    Args:
        network_interfaces (list[dict]): List of network interfaces with basic information
        profile_name (str): AWS profile name to use
        region (str): AWS region name
        debug (bool, optional): Turns on debugging. Defaults to False.

    Returns:
        list[dict]: List of network interfaces with additional attachment info
    """
    aws_config = get_aws_config(region)
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
    
    # Setup the session
    boto3.setup_default_session(profile_name=profile_name)
    
    # Iterate the network interfaces
    for idx, network_interface in enumerate(network_interfaces):
        if debug:
            print("\n\n")
        
        interface_id: str = network_interface["NetworkInterfaceId"]
        interface_type: str = network_interface["InterfaceType"]
        requester_managed: bool = network_interface["RequesterManaged"]
        requester_id: str = network_interface["RequesterId"]
        attachment_to_id: str = network_interface["AttachmentToId"]
        mac_address: str = network_interface["MacAddress"]
        ip_address: str = network_interface["PrivateIpAddress"]
        ip_address_segments = ip_address.split(".")
        description: str = network_interface.get("Description", "")
        
        # Classify interfaces based on the odd ways that AWS identifies where and why the interface exists
        # For interfaces that are automatically created/managed by an AWS service
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
                    dd("Redshift network interface", debug=debug)
                    info = {
                        "Name": f"Redshift {ip_address_segments[2]}.{ip_address_segments[3]}",
                        "Project": "Platform",
                        "AWS": "Redshift",
                    }
                    network_interfaces[idx] = network_interface | info
                # Directories
                elif requester_id == "amazon-directory":
                    dd("Directory network interface", debug=debug)
                    info = get_directory_info(directory_id=attachment_to_id, aws_config=aws_config)
                    info["Name"] = f"{info['Name']} {ip_address_segments[2]}.{ip_address_segments[3]}"
                    network_interfaces[idx] = network_interface | info
                # Route 53 Resolver
                elif requester_id == "cross-account" and str(description).startswith("Route 53 Resolver:"):
                    dd("Route 53 Resolver interface", debug=debug)
                    info = {
                        "Name": f"Route 53 Resolver {ip_address_segments[2]}.{ip_address_segments[3]}",
                        "Project": "DOT Cloud",
                        "AWS": "Route 53",
                    }
                    network_interfaces[idx] = network_interface | info
                # Unknown interface type
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
            
            # Unknown requester_managed interface
            else:
                dd("Unknown network interface: requester_managed", True)
                dd(network_interfaces[idx], True)
                sys.exit()
        
        # For interfaces that are not created/managed by an AWS service
        else:
            dd("Not Requester Managed...", debug=debug)
            
            # EC2s
            if interface_type == "interface" and requester_id == "ec2":
                dd("EC2 network interface", debug=debug)
                info = get_instance_info(attachment_to_id, aws_config=aws_config)
                network_interfaces[idx] = network_interface | info
            
            # WorkSpaces
            elif interface_type == "interface" and requester_id == "WorkSpace-Creation":
                dd("WorkSpace network interface", debug=debug)
                info = get_workspace_info(attachment_to_id, aws_config=aws_config)
                network_interfaces[idx] = network_interface | info
            
            # Lambdas
            elif interface_type == "lambda":
                dd("Lambda network interface", debug=debug)
                info = get_lambda_info(attachment_to_id, aws_config=aws_config, region=region)
                # Most Lambdas don't have a Name tag
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
        tags (list[dict[str, str]] | dict[str, str]): The list or dict of tags from the client response

    Returns:
        dict[str, str]: Dictionary with Name and Project tags
    """
    name = ""
    project = ""
    
    if isinstance(tags, list):
        for tag in tags:
            key = tag.get("Key", "")
            value = tag.get("Value", "")
            if key == "Name":
                name = value
            elif key == "Project":
                project = value
    elif isinstance(tags, dict):
        name = tags.get("Name", "")
        project = tags.get("Project", "")
    
    return {"Name": name, "Project": project}


def get_instance_info(instance_id: str, aws_config: Config) -> dict[str, str]:
    """Gets the Name and Project tags of a given instance

    Args:
        instance_id (str): The instance identifier
        aws_config (Config): The AWS configuration

    Returns:
        dict[str, str]: The Name and Project tags
    """
    client = boto3.client("ec2", config=aws_config)
    try:
        response = client.describe_instances(InstanceIds=[instance_id])
        tags = response["Reservations"][0]["Instances"][0].get("Tags", [])
        return get_tags(tags) | {"AWS": "EC2"}
    except ClientError as e:
        return {"Name": instance_id, "Project": "", "AWS": "EC2", "Error": f"Unexpected error: {e}"}


def get_efs_info(file_system_id: str, aws_config: Config) -> dict[str, str]:
    """Gets the Name and Project tags of a given EFS Volume

    Args:
        file_system_id (str): The file system identifier
        aws_config (Config): The AWS configuration

    Returns:
        dict[str, str]: The Name and Project tags
    """
    client = boto3.client("efs", config=aws_config)
    try:
        response = client.describe_file_systems(FileSystemId=file_system_id)
        tags = response["FileSystems"][0].get("Tags", [])
        return get_tags(tags) | {"AWS": "EFS"}
    except ClientError as e:
        return {"Name": file_system_id, "Project": "", "AWS": "EFS", "Error": f"Unexpected error: {e}"}


def get_vpc_endpoint_info(vpc_endpoint_id: str, aws_config: Config) -> dict[str, str]:
    """Gets the Name and Project tags of a given VPC Endpoint

    Args:
        vpc_endpoint_id (str): The VPC identifier
        aws_config (Config): The AWS configuration

    Returns:
        dict[str, str]: The Name and Project tags
    """
    client = boto3.client("ec2", config=aws_config)
    try:
        response = client.describe_vpc_endpoints(VpcEndpointIds=[vpc_endpoint_id])
        tags = response["VpcEndpoints"][0].get("Tags", [])
        return get_tags(tags) | {"AWS": "VPCE"}
    except ClientError as e:
        return {"Name": vpc_endpoint_id, "Project": "", "AWS": "VPCE", "Error": f"Unexpected error: {e}"}


def get_lambda_info(function_name: str, aws_config: Config, region: str) -> dict[str, str]:
    """Gets the Name, Project, and Team tags of a given Lambda function

    Args:
        function_name (str): The function name
        aws_config (Config): The AWS configuration

    Returns:
        dict[str, str]: The Name, Project, and Team tags (falls back to "SDC-Platform" if no tags found)
    """
    client = boto3.client("lambda", config=aws_config)
    try:
        response = client.list_tags(Resource=f"arn:aws:lambda:{region}:*:function:{function_name}")
        tags = response.get("Tags", {})
        
        # Try to get Project or Team tag, fallback to "SDC-Platform"
        project = tags.get("Project", tags.get("Team", "SDC-Platform"))
        name = tags.get("Name", "")
        
        return {"Name": name, "Project": project, "AWS": "Lambda"}
    except ClientError as e:
        # If we can't get tags (permissions issue, etc), fallback to hardcoded value
        return {"Name": function_name, "Project": "SDC-Platform", "AWS": "Lambda"}


def get_load_balancer_info(lb_name: str, lb_type: str, aws_config: Config) -> dict[str, str]:
    """Gets the Name and Project tags of a given load balancer

    Args:
        lb_name (str): The load balancer name
        lb_type (str): The load balancer type (app, net, gwy)
        aws_config (Config): The AWS configuration

    Returns:
        dict[str, str]: The Name and Project tags
    """
    client = boto3.client("elbv2", config=aws_config)
    try:
        dlb_response = client.describe_load_balancers(Names=[lb_name])
        lb_arn = dlb_response["LoadBalancers"][0].get("LoadBalancerArn")
        dt_response = client.describe_tags(ResourceArns=[lb_arn])
        tags = dt_response["TagDescriptions"][0].get("Tags", [])
        return get_tags(tags) | {"AWS": f"ELB-{lb_type.upper()}"}
    except ClientError as e:
        return {"Name": lb_name, "Project": "", "AWS": f"ELB-{lb_type.upper()}", "Error": f"Unexpected error: {e}"}


def get_directory_info(directory_id: str, aws_config: Config) -> dict[str, str]:
    """Gets the Name and Project tags of a given directory

    Args:
        directory_id (str): The directory id
        aws_config (Config): The AWS configuration

    Returns:
        dict[str, str]: The Name and Project tags
    """
    client = boto3.client("ds", config=aws_config)
    try:
        dd_response = client.describe_directories(DirectoryIds=[directory_id])
        directory_description = dd_response.get("DirectoryDescriptions")[0]
        d_name = directory_description.get("Name", "")
        lt_response = client.list_tags_for_resource(ResourceId=directory_id)
        tags = lt_response["Tags"]
        project = get_tags(tags).get("Project", "")
        return {"Name": d_name, "Project": project, "AWS": "Directory"}
    except ClientError as e:
        return {"Name": directory_id, "Project": "", "AWS": "Directory", "Error": f"Unexpected error: {e}"}


def get_workspace_info(private_ip_address: str, aws_config: Config) -> dict[str, str]:
    """Gets the Name and Project tags of a given WorkSpace

    Args:
        private_ip_address (str): The private IP address of the WorkSpace
        aws_config (Config): The AWS configuration

    Returns:
        dict[str, str]: The Name and Project tags
    """
    try:
        client = boto3.client("workspaces", config=aws_config)
        paginator = client.get_paginator("describe_workspaces")
        response_iterator = paginator.paginate()
        
        for page in response_iterator:
            page_workspaces = page["Workspaces"]
            for workspace in page_workspaces:
                ip_address = workspace.get("IpAddress")
                if ip_address == private_ip_address:
                    ws_id = workspace.get("WorkspaceId")
                    ws_name = workspace.get("UserName")
                    directory_id = workspace.get("DirectoryId")
                    d_info = get_directory_info(directory_id, aws_config)
                    d_name = d_info.get("Name")
                    d_project = d_info.get("Project", "")
                    return {"Name": f"{ws_name}.{d_name}", "Project": d_project, "AWS": "WS", "AttachmentToId": ws_id}
        
        # If we didn't find a matching workspace
        return {"Name": f"WorkSpace: {private_ip_address}", "Project": "", "AWS": "WS"}
    except ClientError as e:
        return {"Name": f"WorkSpace: {private_ip_address}", "Project": "", "AWS": "WS", "Error": f"Unexpected error: {e}"}


def get_transit_gateway_attachment_info(transit_gateway_attachment_id: str, aws_config: Config) -> dict[str, str]:
    """Gets the Name and Project tags of a given transit gateway attachment

    Args:
        transit_gateway_attachment_id (str): The transit gateway attachment identifier
        aws_config (Config): The AWS configuration

    Returns:
        dict[str, str]: The Name and Project tags
    """
    client = boto3.client("ec2", config=aws_config)
    try:
        tgwa_response = client.describe_transit_gateway_attachments(TransitGatewayAttachmentIds=[transit_gateway_attachment_id])
        tags = tgwa_response["TransitGatewayAttachments"][0].get("Tags", [])
        return get_tags(tags) | {"AWS": "TGWA"}
    except ClientError as e:
        return {"Name": transit_gateway_attachment_id, "Project": "", "AWS": "TGWA", "Error": f"Unexpected error: {e}"}