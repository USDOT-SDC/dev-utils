from token_refresh import token_refresh
from awsquery import awsquery as q
from pathlib import Path
from datetime import datetime
import csv
import yaml


q.cls()

# query dev
q.print_in_box(
    [
        "".ljust(80),
        "Network Interfaces: Dev",
        "",
    ],
    line="double",
)
env = "dev"
# get the token refresh config
config_file_path = Path(f"token_refresh/config-{env}.yaml")
config = yaml.safe_load(config_file_path.read_text())
# refresh the token, if necessary
token_refresh.refresh_token_when_needed(env=env)
# get list of network interfaces w/basic info
ni_dev = q.get_net_interfaces(env=env, debug=False)
# get the attachment info for the network interface
ni_dev = q.get_net_interface_details(network_interfaces=ni_dev, env=env, debug=False)

# query prod
q.print_in_box(
    [
        "".ljust(80),
        "Network Interfaces: Prod",
        "",
    ],
    line="double",
)
env = "prod"
# get the token refresh config
config_file_path = Path(f"token_refresh/config-{env}.yaml")
config = yaml.safe_load(config_file_path.read_text())
# refresh the token, if necessary
token_refresh.refresh_token_when_needed(env=env)
# get list of network interfaces w/basic info
ni_prod = q.get_net_interfaces(env=env, debug=False)
# get the attachment info for the network interface
ni_prod = q.get_net_interface_details(network_interfaces=ni_prod, env=env, debug=False)

# add prod to dev
network_interfaces = ni_dev + ni_prod

# look for errors
for network_interface in network_interfaces:
    if network_interface.get("Error", False):
        print("Warning: An error was found.")
        q.dd(network_interface, debug=True)
    if not network_interface.get("Name", False):
        print("Warning: No Name was found.")
        q.dd(network_interface, debug=True)

# set the column order
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
for idx, network_interface in enumerate(network_interfaces):
    network_interfaces[idx] = {k : network_interface[k] for k in keys}

# save the data to file
today_str = datetime.today().strftime("%Y-%m-%d")
file_name = "network-interfaces_" + today_str + ".csv"
# keys = network_interfaces[0].keys()
with open(file_name, "w", newline="") as output_file:
    dict_writer = csv.DictWriter(output_file, keys)
    dict_writer.writeheader()
    dict_writer.writerows(network_interfaces)
