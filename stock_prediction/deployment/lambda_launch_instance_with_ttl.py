import time
from datetime import datetime, timedelta

import boto3
from dateutil import tz
from utils import (
    BUCKET_NAME,
    create_s3_access_iam_role,
    get_or_create_instance_s3_access_profile,
)

REGION = "us-east-1"
# read ami id from info.yaml konwing that the first line has
# this format AMI_ID: <ami_id> to avoid having to send the
# yaml library package to lambda
with open("info.yaml", "r") as yaml_file:
    info = yaml_file.readlines()
    AMI_ID = info[0].split(":")[1].strip()
INSTANCE_TYPE = "t2.micro"
KEY_NAME = "capstone_project"
# SECURITY_GROUP = "your-security-group-id"
# TTL_DURATION = 3600
SECURITY_GROUP_NAME = "custom-security-group"
SECURITY_GROUP_DESCRIPTION = (
    "Security group for SSH access to capstone project instances"
)
TTL_DURATION = 3 * 60

USER_DATA_SCRIPT = (
    f"""#!/bin/bash
exec > /var/log/user-data.log 2>&1
cd ~
# Load environment variables
source /root/.bashrc
export PYENV_ROOT="/root/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

# Navigate to the project directory
cd /root/aws_ml_eng_project_stock_prediction
git pull
git checkout marcoopsampaio/model_development

# run retraining script
poetry run python ./stock_prediction/modeling/train.py

cat << EOF > /root/temp_script.py
import boto3
import os

# Specify the bucket name
region = "us-east-1"  # Specify your preferred AWS region

# Initialize S3 client
s3 = boto3.client("s3")

# Create bucket if it does not exist
try:
    if region == "us-east-1":
        s3.create_bucket(Bucket="{BUCKET_NAME}")
    else:
        s3.create_bucket(
            Bucket="{BUCKET_NAME}",
            CreateBucketConfiguration="""
    """{"LocationConstraint": region}
        )
except Exception as e:
    print(f"Error creating bucket: {e}")"""
    f"""

# Dummy file content
dummy_content = "This is a dummy file for testing S3 operations."
dummy_filename = "dummy_file.txt"

# Write content to a local file
with open(dummy_filename, "w") as file:
    file.write(dummy_content)

# Upload the file to the S3 bucket
try:
    #s3.upload_file(dummy_filename, "{BUCKET_NAME}", dummy_filename)
    s3.upload_file("predictions.feather", "{BUCKET_NAME}", "predictions.feather")
    print(f"File """
    """{dummy_filename} uploaded to bucket """
    f"""{BUCKET_NAME}.")"""
    """
except Exception as e:
    print(f"Error uploading file: {e}")

# Clean up the local dummy file
os.remove(dummy_filename)
EOF

# Run the Python script inside the Poetry environment
poetry run python /root/temp_script.py
#sleep 60
#sudo shutdown -h now
"""
)


def get_or_create_security_group(ec2_client):
    try:
        # Check if the security group exists
        response = ec2_client.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [SECURITY_GROUP_NAME]}]
        )
        if response["SecurityGroups"]:
            print(f"Security group {SECURITY_GROUP_NAME} already exists.")
            return response["SecurityGroups"][0]["GroupId"]
    except ec2_client.exceptions.ClientError as e:
        print(f"Error checking security group: {e}")

    # Create the security group if it doesn't exist
    try:
        response = ec2_client.create_security_group(
            GroupName=SECURITY_GROUP_NAME,
            Description=SECURITY_GROUP_DESCRIPTION,
            VpcId=ec2_client.describe_vpcs()["Vpcs"][0]["VpcId"],
        )
        security_group_id = response["GroupId"]
        print(
            f"Created security group {SECURITY_GROUP_NAME} with ID {security_group_id}."
        )

        # Add inbound rule for SSH access
        ec2_client.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH access"}],
                }
            ],
        )
        print(f"Inbound SSH rule added to security group {SECURITY_GROUP_NAME}.")

        return security_group_id
    except ec2_client.exceptions.ClientError as e:
        print(f"Error creating security group: {e}")
        raise


def lambda_handler(event, context):
    # Create a boto3 client for EC2 and IAM
    ec2_client = boto3.client("ec2", region_name=REGION)
    iam_client = boto3.client("iam", region_name=REGION)

    # Create or retrieve IAM role and instance profile
    _ = create_s3_access_iam_role(iam_client)
    instance_profile_name = get_or_create_instance_s3_access_profile(iam_client)

    # Ensure the security group exists
    security_group_id = get_or_create_security_group(ec2_client)

    time.sleep(30)

    # Launch the EC2 instance
    instance = ec2_client.run_instances(
        ImageId=AMI_ID,
        InstanceType=INSTANCE_TYPE,
        KeyName=KEY_NAME,
        MinCount=1,
        MaxCount=1,
        SecurityGroupIds=[security_group_id],
        UserData=USER_DATA_SCRIPT,
        IamInstanceProfile={"Name": instance_profile_name},
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
