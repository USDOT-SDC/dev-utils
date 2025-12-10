# AWS Network Interface Query Tool

Queries AWS EC2 network interfaces across multiple accounts and generates a detailed CSV report.

## Setup

1. **Install dependencies:**
   ```cmd
   python -m venv .venv --prompt awsq
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure your profiles:**
   Edit `config.json` to specify which AWS profiles to query:
   ```json
   {
     "profiles": ["sdc-dev", "sdc-prod"],
     "region": "us-east-1"
   }
   ```

3. **Ensure your AWS profiles are configured:**
   Your profiles should already be set up via your ADFS/zAccounts authentication flow.
   The script will use whatever credentials are in `~/.aws/credentials` for each profile.

## Usage

```cmd
python main.py
```

The script will:
1. Query network interfaces from all configured profiles
2. Gather detailed information about each interface (tags, attachments, etc.)
3. Generate a CSV file: `network-interfaces_YYYY-MM-DD.csv`

## Output

CSV columns:
- `MacAddress` - MAC address of the interface
- `PrivateIpAddress` - Private IPv4 address
- `Name` - Name tag (or generated name)
- `Project` - Project tag
- `AWS` - AWS service type (EC2, Lambda, RDS, etc.)
- `Description` - AWS-provided description
- `InterfaceType` - Type of network interface
- `NetworkInterfaceId` - ENI ID
- `AttachmentToId` - What the interface is attached to
- `RequesterManaged` - Whether AWS manages this interface
- `RequesterId` - AWS service that requested the interface

## Notes

- The script handles multiple interface types: EC2, Lambda, EFS, RDS, ELB, VPC Endpoints, WorkSpaces, etc.
- Lambda functions now properly retrieve Project/Team tags (falls back to "SDC-Platform" if no tags)
- All AWS API calls use retries for resilience
- Debug mode available by changing `debug=False` to `debug=True` in main.py
