# SDC CLI
<p align="center">
    <img src="sdc-cli-logo.png" alt="logo" height="200"/>
</p>

## Overview

The SDC CLI tool is a script that does stuff. This tool is designed to streamline tasks.

## Getting Started
_Assumes you have cloned this repo to your local filesystem_

### Create a virtual environment
```
python -m venv .venv --prompt sdc
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

### Run the script
```
sdc --help
```

## Examples
```
sdc dev ec2 list
```
```
sdc dev ec2 list --states stopped stopping
```
```
sdc dev ec2 start
```
```
sdc dev ec2 stop
```
Note: <kbd>ctrl</kbd> + <kbd>c</kbd> will stop the CLI

## Support

If you encounter any issues or have questions about the AWS Network Interface Query tool, please [open an issue](https://github.com/USDOT-SDC/dev-utils/issues) on our GitHub repository.

For general AWS-related inquiries and support, please refer to the [AWS Support](https://aws.amazon.com/support/) resources.

## Acknowledgments

This project is built upon the [Boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html), an AWS SDK. We would like to acknowledge the AWS community and contributors for their valuable work.

## Author

AWS Network Interface Query is developed and maintained by [Jeff Ussing](https://github.com/JeffUssing).

---

Thank you for using the SDC CLI tool! We hope it simplifies tasks. If you have any feedback or suggestions, please don't hesitate to reach out.
