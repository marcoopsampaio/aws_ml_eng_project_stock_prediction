from datetime import datetime, timedelta

import boto3
from dateutil import tz

REGION = "us-east-1"
AMI_ID = "ami-0e2c8caa4b6378d8c"
INSTANCE_TYPE = "t2.micro"
KEY_NAME = "capstone_project"
# SECURITY_GROUP = "your-security-group-id"
# TTL_DURATION = 3600
TTL_DURATION = 3 * 60

USER_DATA_SCRIPT = """#!/bin/bash
# Your simple command to run on EC2 instance
echo 'Running the ML task'
# Add any other commands as needed
sleep 60
sudo shutdown -h now
"""

# USER_DATA_SCRIPT = """#!/bin/bash
# # Install necessary dependencies
# sudo apt update
# sudo apt install -y python3-pip

# # Install AWS CLI and boto3 for Python
# pip3 install boto3

# # Python script to create an S3 bucket and write a dummy file
# cat <<EOF > /home/ubuntu/s3_script.py
# import boto3
# import sys

# bucket_name = "test_bucket_capstone"
# region = "us-east-1"

# try:
#     s3_client = boto3.client("s3", region_name=region)

#     # Create bucket if it doesn't exist
#     if not any(bucket["Name"] == bucket_name for bucket in s3_client.list_buckets()["Buckets"]):
#         s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={"LocationConstraint": region})
#         print(f"Bucket '{bucket_name}' created.")
#     else:
#         print(f"Bucket '{bucket_name}' already exists.")

#     # Write a dummy file to the bucket
#     s3_client.put_object(Bucket=bucket_name, Key="dummy.txt", Body="This is a dummy file.")
#     print(f"Dummy file written to bucket '{bucket_name}'.")
# except Exception as e:
#     print(f"An error occurred: {e}")
#     sys.exit(1)
# EOF

# # Run the Python script
# python3 /home/ubuntu/s3_script.py
# sleep 60

# # Shutdown the instance after completion
# sudo shutdown -h now
# """


def lambda_handler(event, context):
    # Create a boto3 client for EC2 and IAM
    ec2_client = boto3.client("ec2", region_name=REGION)

    # Launch EC2 instance with the IAM role and user data script
    instance = ec2_client.run_instances(
        ImageId=AMI_ID,
        InstanceType=INSTANCE_TYPE,
        KeyName=KEY_NAME,
        MinCount=1,
        MaxCount=1,
        UserData=USER_DATA_SCRIPT,  # Specify the script to run
    )

    instance_id = instance["Instances"][0]["InstanceId"]
    print(f"Instance {instance_id} launched.")

    # Wait until the instance is running
    ec2_client.get_waiter("instance_running").wait(InstanceIds=[instance_id])
    print(f"Instance {instance_id} is now running.")

    # Set a TTL tag on the instance
    shutdown_time = (
        datetime.now(tz.tzutc()) + timedelta(seconds=TTL_DURATION)
    ).isoformat()
    ec2_client.create_tags(
        Resources=[instance_id],
        Tags=[{"Key": "ShutdownBy", "Value": shutdown_time}],
    )
    print(f"TTL for instance {instance_id} set to {shutdown_time}")
