# AWS Resource Cleanup
<p align="center">
    <img src="resource-cleanup-logo.png" alt="logo" height="200"/>
</p>

## Overview

The AWS Resource Cleanup tools are a scripts used to identify resources that may need attention. This tool is designed to streamline those cleanup tasks.

## Getting Started
_Assumes you have cloned this repo to your local filesystem_

### Create a virtual environment
```
python -m venv .venv --prompt rc
```

### Activate the virtual environment
```
.venv/Scripts/activate
```

### Install required packages
```
pip install -r requirements.txt
```

### Create a config file for each environment
The [`config-{env}.yaml`](token_refresh/config.sample.yaml) file will contain the following:
- `api_endpoint` is the URL where you can generate a new token for AWS access.
- `api_key` is the API key associated with the api endpoint
- `profile_name` is the name of the AWS CLI profile to be generated/used
- `aws_config` contains information used when creating the [Config object](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html) used by the Boto3 clients

```yaml
api_endpoint: "https://example.com/generate_token"
api_key: "xxxxXXXXxxxxXXXXxxxxXXXXxxxxXXXXxxxxXXXX"
profile_name: my_user-dev
aws_config:
  region_name: us-east-1
  retries:
    max_attempts: 10
    mode: "standard"
```

### Run the scripts
```
python unused_volumes.py
```

## Support

If you encounter any issues or have questions about the AWS Resource Cleanup tools, please [open an issue](https://github.com/USDOT-SDC/dev-utils/issues) on our GitHub repository.

For general AWS-related inquiries and support, please refer to the [AWS Support](https://aws.amazon.com/support/) resources.

## Acknowledgments

This project is built upon [Boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html), an AWS SDK. We would like to acknowledge the AWS community and contributors for their valuable work.

## Author

AWS Resource Cleanup tools are developed and maintained by [Jeff Ussing](https://github.com/JeffUssing).

The `unused_volumes.py` script is based on [Vyach Mayorskiy](https://github.com/vmayorskiy-ac) work on the [cleanup-worker](https://github.com/USDOT-SDC/cleanup-worker) .

---

Thank you for using the AWS Resource Cleanup tool!s We hope it simplifies your resource cleanup tasks. If you have any feedback or suggestions, please don't hesitate to reach out.