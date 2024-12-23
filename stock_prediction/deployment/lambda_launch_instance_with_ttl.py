from datetime import datetime, timedelta

import boto3
from dateutil import tz

REGION = "us-east-1"
AMI_ID = "ami-0e2c8caa4b6378d8c"
INSTANCE_TYPE = "t2.micro"
KEY_NAME = "capstone_project"
# SECURITY_GROUP = "your-security-group-id" # TODO: create security group
TTL_DURATION = 3600

USER_DATA_SCRIPT = """#!/bin/bash
# Your simple command to run on EC2 instance
echo 'Running the ML task'
# Add any other commands as needed
sudo shutdown -h now
"""


def lambda_handler(event, context):
    ec2_client = boto3.client("ec2", region_name=REGION)

    # Launch EC2 instance with a TTL tag
    instance = ec2_client.run_instances(
        ImageId=AMI_ID,
        InstanceType=INSTANCE_TYPE,
        KeyName=KEY_NAME,
        # SecurityGroupIds=[SECURITY_GROUP],
        MinCount=1,
        MaxCount=1,
        UserData=USER_DATA_SCRIPT,  # Specify the script to run
    )

    instance_id = instance["Instances"][0]["InstanceId"]
    print(f"Instance {instance_id} launched.")

    # Set a TTL tag on the instance
    shutdown_time = (
        datetime.now(tz.tzutc()) + timedelta(seconds=TTL_DURATION)
    ).isoformat()
    ec2_client.create_tags(
        Resources=[instance_id],
        Tags=[{"Key": "ShutdownBy", "Value": shutdown_time}],
    )
    print(f"TTL for instance {instance_id} set to {shutdown_time}")
