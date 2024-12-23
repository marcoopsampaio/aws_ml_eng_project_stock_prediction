from datetime import datetime, timezone

import boto3

REGION = "us-east-1"

ec2_client = boto3.client("ec2", region_name=REGION)


def lambda_handler(event, context):
    now = datetime.now(timezone.utc)

    # List all running EC2 instances with the "ShutdownBy" tag
    instances = ec2_client.describe_instances(
        Filters=[
            {"Name": "instance-state-name", "Values": ["running", "stopped"]},
            {"Name": "tag:ShutdownBy", "Values": ["*"]},
        ]
    )

    for reservation in instances["Reservations"]:
        for instance in reservation["Instances"]:
            # If the instance is stopped, terminate it immediately
            if instance["State"]["Name"] == "stopped":
                ec2_client.terminate_instances(InstanceIds=[instance["InstanceId"]])
                print(f"Terminated stopped instance {instance['InstanceId']}")
                continue

            # Check the other case when the instance is running
            shutdown_by = next(
                (
                    tag["Value"]
                    for tag in instance.get("Tags", [])
                    if tag["Key"] == "ShutdownBy"
                ),
                None,
            )

            if shutdown_by and datetime.fromisoformat(shutdown_by) < now:
                ec2_client.terminate_instances(InstanceIds=[instance["InstanceId"]])
                print(f"Terminated instance {instance['InstanceId']}")
