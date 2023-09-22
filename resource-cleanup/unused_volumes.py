from token_refresh import token_refresh
from awsquery import awsquery as q
from pathlib import Path
import yaml


debug = False
q.cls()

env = "dev"
# get the token refresh config
config_file_path = Path(f"token_refresh/config-{env}.yaml")
config = yaml.safe_load(config_file_path.read_text())
# refresh the token, if necessary
token_refresh.refresh_token_when_needed(env=env)
q.get_volumes(env, debug)

env = "prod"
# get the token refresh config
config_file_path = Path(f"token_refresh/config-{env}.yaml")
config = yaml.safe_load(config_file_path.read_text())
# refresh the token, if necessary
token_refresh.refresh_token_when_needed(env=env)
q.get_volumes(env, debug)
