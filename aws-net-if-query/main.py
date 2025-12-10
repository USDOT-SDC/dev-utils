from awsquery import awsquery as q
from pathlib import Path
from datetime import datetime
import csv
import json


def main() -> None:
    """Main entry point for AWS network interface query tool"""
    q.cls()

    # Load config
    config_path = Path("config.json")
    if not config_path.exists():
        print("ERROR: config.json not found!")
        print("Create a config.json file with your profiles and region:")
        print('{\n  "profiles": ["sdc-dev", "sdc-prod"],\n  "region": "us-east-1"\n}')
        return

    with open(config_path) as f:
        config = json.load(f)

    profiles = config.get("profiles", [])
    region = config.get("region", "us-east-1")

    if not profiles:
        print("ERROR: No profiles configured in config.json")
        return

    # Collect network interfaces from all profiles
    all_network_interfaces = []

    for profile in profiles:
        q.print_in_box(
            [
                "".ljust(80),
                f"Network Interfaces: {profile}",
                "",
            ],
            line="double",
        )

        # Get list of network interfaces with basic info
        ni = q.get_net_interfaces(profile_name=profile, region=region, debug=False)
        
        # Get the attachment info for the network interfaces
        ni = q.get_net_interface_details(network_interfaces=ni, profile_name=profile, region=region, debug=False)
        
        all_network_interfaces.extend(ni)

    # Look for errors or missing names
    for network_interface in all_network_interfaces:
        if network_interface.get("Error", False):
            print("Warning: An error was found.")
            q.dd(network_interface, debug=True)
        if not network_interface.get("Name", False):
            print("Warning: No Name was found.")
            q.dd(network_interface, debug=True)

    # Set the column order
    keys = [
        "MacAddress",
        "PrivateIpAddress",
        "Name",
        "Project",
        "AWS",
        "Description",
        "InterfaceType",
        "NetworkInterfaceId",
        "AttachmentToId",
        "RequesterManaged",
        "RequesterId",
    ]
    
    # Reorder dict keys to match desired output
    all_network_interfaces = [{k: ni[k] for k in keys} for ni in all_network_interfaces]

    # Save the data to file
    today_str = datetime.today().strftime("%Y-%m-%d")
    file_name = f"network-interfaces_{today_str}.csv"
    
    with open(file_name, "w", newline="") as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(all_network_interfaces)

    print(f"\nResults saved to: {file_name}")
    print(f"Total network interfaces found: {len(all_network_interfaces)}")


if __name__ == "__main__":
    main()
