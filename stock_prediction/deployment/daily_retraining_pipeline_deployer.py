import argparse
import json
import os
import time
import zipfile

import boto3

from stock_prediction.deployment.utils import DEFAULT_REGION, resource_exists

# AWS Configuration
LAMBDA_ROLE_NAME = "LambdaExecutionRoleForEC2"
TTL_DURATION = 6 * 3600  # TTL in seconds (e.g., 6 hour)

# Initialize clients
iam_client = boto3.client("iam", region_name=DEFAULT_REGION)
lambda_client = boto3.client("lambda", region_name=DEFAULT_REGION)
ec2_client = boto3.client("ec2", region_name=DEFAULT_REGION)
events_client = boto3.client("events", region_name=DEFAULT_REGION)


def create_lambda_execution_role():

    assume_role_policy_document = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    )

    exists = resource_exists(iam_client.get_role, RoleName=LAMBDA_ROLE_NAME)
    if exists:
        print("Lambda execution role already exists.")
        return exists["Role"]["Arn"]

    # Create IAM role for Lambda execution if it doesn't exist
    response = iam_client.create_role(
        RoleName=LAMBDA_ROLE_NAME,
        AssumeRolePolicyDocument=assume_role_policy_document,
        Description="Role for Lambda function to interact with EC2, CloudWatch, and EventBridge",
    )
    role_arn = response["Role"]["Arn"]
    print(f"Created Lambda execution role: {role_arn}")

    # Attach the necessary policies
    for policy in [
        "AWSLambda_FullAccess",
        "AmazonEC2FullAccess",
        "CloudWatchLogsFullAccess",
        "AmazonEventBridgeFullAccess",
        "IAMFullAccess",
    ]:
        iam_client.attach_role_policy(
            RoleName=LAMBDA_ROLE_NAME,
            PolicyArn=f"arn:aws:iam::aws:policy/{policy}",
        )

    print("Attached necessary policies to Lambda execution role.")

    print("Waiting for Lambda execution role to become assumable...")
    waiter = iam_client.get_waiter("role_exists")
    waiter.wait(RoleName=LAMBDA_ROLE_NAME)
    time.sleep(10)

    return role_arn


def create_lambda_function(function_name, file_name, handler_name, role_arn):

    exists = resource_exists(lambda_client.get_function, FunctionName=function_name)
    if exists:
        print(f"Lambda function {function_name} already exists.")
        return exists["Configuration"]["FunctionArn"]

    # Create a ZIP file with the Lambda function code and utils.py
    zip_file = f"{function_name}.zip"
    with zipfile.ZipFile(zip_file, "w") as zf:
        # Add the main Lambda handler file
        zf.write(file_name, os.path.basename(file_name))

        # Add utils.py and info.yaml to the ZIP file
        for file in ["utils.py", "info.yaml"]:
            if os.path.exists(file):
                zf.write(file, os.path.basename(file))
            else:
                print(
                    f"Warning: {file} not found and will not be included in the package."
                )

    # Upload Lambda function code
    with open(zip_file, "rb") as f:
        response = lambda_client.create_function(
            FunctionName=function_name,
            Runtime="python3.9",
            Role=role_arn,
            Handler=handler_name,
            Code={"ZipFile": f.read()},
            Timeout=300,  # Timeout in seconds
        )
    os.remove(zip_file)
    print(f"Lambda function {function_name} created.")
    return response["FunctionArn"]


def create_eventbridge_rule(lambda_arn):
    exists = resource_exists(events_client.describe_rule, Name="DailyEC2LaunchRule")
    if exists:
        print("EventBridge rule already exists.")
        return exists["RuleArn"]

    response = events_client.put_rule(
        Name="DailyEC2LaunchRule",
        # ScheduleExpression="cron(0 * * * ? *)",  # Daily at midnight UTC
        ScheduleExpression="cron(* * * * ? *)",  # Every minute
        State="ENABLED",
    )
    rule_arn = response["RuleArn"]
    print("EventBridge rule created.")

    events_client.put_targets(
        Rule="DailyEC2LaunchRule",
        Targets=[
            {
                "Id": "1",
                "Arn": lambda_arn,
            }
        ],
    )

    lambda_client.add_permission(
        FunctionName="LaunchEC2WithTTL",
        StatementId="AllowEventBridgeInvoke",
        Action="lambda:InvokeFunction",
        Principal="events.amazonaws.com",
        SourceArn=rule_arn,
    )
    print("EventBridge rule linked to Lambda function.")

    # Manually invoke the Lambda function once after the rule is created
    print("Manually triggering Lambda function for initial execution.")
    lambda_client.invoke(
        FunctionName="LaunchEC2WithTTL",
        InvocationType="Event",  # Asynchronous invocation
    )
    print("Lambda function invoked for initial execution.")


def create_cloudwatch_rule(lambda_arn):

    exists = resource_exists(events_client.describe_rule, Name="EC2ExpirationCheckRule")
    if exists:
        print("CloudWatch rule already exists.")
        return exists["RuleArn"]

    response = events_client.put_rule(
        Name="EC2ExpirationCheckRule",
        # ScheduleExpression="cron(0 * * * ? *)",  # Every hour at the top of the hour
        # Every minute
        ScheduleExpression="cron(*/10 * * * ? *)",
        State="ENABLED",
    )
    rule_arn = response["RuleArn"]
    print("CloudWatch rule created for termination.")

    events_client.put_targets(
        Rule="EC2ExpirationCheckRule",
        Targets=[
            {
                "Id": "1",
                "Arn": lambda_arn,
            }
        ],
    )

    lambda_client.add_permission(
        FunctionName="TerminateExpiredInstances",
        StatementId="AllowCloudWatchInvoke",
        Action="lambda:InvokeFunction",
        Principal="events.amazonaws.com",
        SourceArn=rule_arn,
    )
    print("CloudWatch rule linked to termination Lambda function.")


def terminate_ec2_instances():

    # List all running EC2 instances with the "ShutdownBy" tag
    instances = ec2_client.describe_instances(
        Filters=[
            {"Name": "tag:ShutdownBy", "Values": ["*"]},
        ]
    )

    # Iterate through instances and terminate the ones that have the "ShutdownBy" tag
    for reservation in instances["Reservations"]:
        for instance in reservation["Instances"]:
            shutdown = next(
                (
                    True
                    for tag in instance.get("Tags", [])
                    if tag["Key"] == "ShutdownBy"
                ),
                False,
            )
            if shutdown:
                ec2_client.terminate_instances(InstanceIds=[instance["InstanceId"]])
                print(
                    f"Terminated instance {instance['InstanceId']} with the 'ShutdownBy' tag."
                )


def cleanup_resources():
    # Delete Lambda functions if they exist
    for function_name in ["LaunchEC2WithTTL", "TerminateExpiredInstances"]:
        if resource_exists(lambda_client.delete_function, FunctionName=function_name):
            print(f"Deleted {function_name} function.")
        else:
            print(f"{function_name} function does not exist. Skipping deletion.")

    print("Lambda functions deletion check complete.")

    # Delete EventBridge rules if they exist
    for rule_name in ["DailyEC2LaunchRule", "EC2ExpirationCheckRule"]:
        if resource_exists(events_client.remove_targets, Rule=rule_name, Ids=["1"]):
            print(f"Removed target for {rule_name}.")
        else:
            print(f"Target for {rule_name} does not exist. Skipping deletion.")

        if resource_exists(events_client.delete_rule, Name=rule_name):
            print(f"Deleted {rule_name} rule.")
        else:
            print(f"{rule_name} rule does not exist. Skipping deletion.")

    print("EventBridge rules deletion check complete.")

    # Delete IAM role if it exists
    for rolename, policy in [
        (LAMBDA_ROLE_NAME, "arn:aws:iam::aws:policy/AWSLambda_FullAccess"),
        (LAMBDA_ROLE_NAME, "arn:aws:iam::aws:policy/AmazonEC2FullAccess"),
        (LAMBDA_ROLE_NAME, "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"),
        (LAMBDA_ROLE_NAME, "arn:aws:iam::aws:policy/AmazonEventBridgeFullAccess"),
        (LAMBDA_ROLE_NAME, "arn:aws:iam::aws:policy/IAMFullAccess"),
    ]:
        if resource_exists(
            iam_client.detach_role_policy, RoleName=rolename, PolicyArn=policy
        ):
            print(f"Detached {policy} policy from {rolename} role.")

    if resource_exists(iam_client.delete_role, RoleName=LAMBDA_ROLE_NAME):
        print(f"Deleted IAM role {rolename}.")

    print("IAM role deletion check complete.")

    print("Instance profile deletion check complete.")

    # Delete CloudWatch rule if it exists
    if resource_exists(events_client.delete_rule, Name="EC2ExpirationCheckRule"):
        print("Deleted CloudWatch rule EC2ExpirationCheckRule.")

    # Clean up expired EC2 instances
    terminate_ec2_instances()


def main():
    parser = argparse.ArgumentParser(description="Deploy or clean up the deployment.")
    parser.add_argument(
        "--cleanup", action="store_true", help="Cleanup the deployment resources"
    )
    args = parser.parse_args()

    if args.cleanup:
        cleanup_resources()
    else:
        role_arn = create_lambda_execution_role()
        lambda_arn = create_lambda_function(
            function_name="LaunchEC2WithTTL",
            file_name="lambda_launch_instance_with_ttl.py",
            handler_name="lambda_launch_instance_with_ttl.lambda_handler",
            role_arn=role_arn,
        )
        create_eventbridge_rule(lambda_arn)
        terminate_lambda_arn = create_lambda_function(
            function_name="TerminateExpiredInstances",
            file_name="lambda_terminate_by_ttl.py",
            handler_name="lambda_terminate_by_ttl.lambda_handler",
            role_arn=role_arn,
        )
        create_cloudwatch_rule(terminate_lambda_arn)


if __name__ == "__main__":
    main()
