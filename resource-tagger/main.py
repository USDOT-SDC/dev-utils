from token_refresh import token_refresh
from functions import base_functions as bf
from functions import tag_functions as tf
from pathlib import Path
from datetime import datetime
import csv
import yaml

debug = True

bf.cls()

# get the tag data
tag_data_path = Path(f"tag-data.yaml")
tag_data = yaml.safe_load(tag_data_path.read_text())


# dev
bf.print_in_box(
    [
        "".ljust(80),
        "Instances: Dev",
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

# get instance info
instance_info = tf.get_instance_info(env, tag_data)
tf.print_instance_info(instance_info)


# prod
bf.print_in_box(
    [
        "".ljust(80),
        "Instances: Prod",
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

# get instance info
instance_info = tf.get_instance_info(env, tag_data)
tf.print_instance_info(instance_info)

