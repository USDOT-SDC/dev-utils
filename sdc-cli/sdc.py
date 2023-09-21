from token_refresh import token_refresh
from awsquery import awsquery as awsq
import functions as func
from log import Log
import argparse
import json

logger = Log()


# print(json.dumps(instances, ensure_ascii=False, indent=2, default=str))


def main():
    func.cls()
    parser = argparse.ArgumentParser(description="A basic CLI tool for the SDC.")

    parser.add_argument("environment", type=str, help="The environment to work in.")
    parser.add_argument("resource", type=str, help="The type of resource to act on.")
    parser.add_argument("action", type=str, help="The action to take on the resource.")
    parser.add_argument(
        "--states",
        nargs="*",
        help="Act on resources in these states. ( pending | running | shutting-down | terminated | stopping | stopped).",
    )
    parser.add_argument("--debug", action="store_true", help="Turns on debugging.")

    args = parser.parse_args()
    env = args.environment
    resource = args.resource
    action = args.action
    states = args.states
    debug = args.debug
    if debug:
        logger.setLevel("DEBUG")
        for arg in vars(args):
            logger.debug(f"{arg}:{getattr(args, arg)}")

    # refresh the token, if necessary
    token_refresh.refresh_token_when_needed(env=env)

    if resource == "ec2":
        print(f"=== resource:{resource} ===")
        if action == "list":
            print(f"=== action:{action} ===")
            instances = awsq.get_instances(env, states)
            columns_to_print = [
                "Name",
                "State",
                "InstanceId",
                "InstanceType",
                "Platform",
                "PrivateIpAddress",
            ]
            sort_by = ""
            title = "EC2 Instances"
            subtitle = f"States:{str(states)}" if states else ""
            func.print_table(instances, columns_to_print, sort_by, title, subtitle)
        if action == "start":
            print(f"=== action:{action} ===")
            instances = awsq.get_instances(env, states=["stopped"])
            columns_to_print = [
                "Name",
                "IDX",
                "InstanceType",
                "Platform",
                "PrivateIpAddress",
            ]
            sort_by = ""
            title = "Stopped EC2 Instances"
            func.print_table(instances, columns_to_print, sort_by, title)
            instance_cnt = len(instances)-1
            while True:
                try:
                    print("Select an instance to start.")
                    idx = int(input("IDX:"))
                except ValueError:
                    print("Sorry, I didn't understand that.")
                    continue
                else:
                    if 0 <= idx <= instance_cnt:
                        break
                    else:
                        print("That IDX is out of range.")
                        continue
            for instance in instances:
                if instance.get("IDX") == idx:
                    instance_id = instance.get("InstanceId")
                    name = instance.get("Name")
                    print(f"Starting: {instance_id} ({name})")
                    starting_instance = awsq.start_instance(env, instance_id)
                    print(f"Previous State: {starting_instance.get('PreviousState')}")
                    print(f"Current State: {starting_instance.get('CurrentState')}")
        if action == "stop":
            print(f"=== action:{action} ===")
            instances = awsq.get_instances(env, states=["running"])
            columns_to_print = [
                "Name",
                "IDX",
                "InstanceType",
                "Platform",
                "PrivateIpAddress",
            ]
            sort_by = ""
            title = "Running EC2 Instances"
            func.print_table(instances, columns_to_print, sort_by, title)
            instance_cnt = len(instances)-1
            while True:
                try:
                    print("Select an instance to stop.")
                    idx = int(input("IDX:"))
                except ValueError:
                    print("Sorry, I didn't understand that.")
                    continue
                else:
                    if 0 <= idx <= instance_cnt:
                        break
                    else:
                        print("That IDX is out of range.")
                        continue
            for instance in instances:
                if instance.get("IDX") == idx:
                    instance_id = instance.get("InstanceId")
                    name = instance.get("Name")
                    print(f"Stopping: {instance_id} ({name})")
                    starting_instance = awsq.stop_instance(env, instance_id)
                    print(f"Previous State: {starting_instance.get('PreviousState')}")
                    print(f"Current State: {starting_instance.get('CurrentState')}")


if __name__ == "__main__":
    main()
