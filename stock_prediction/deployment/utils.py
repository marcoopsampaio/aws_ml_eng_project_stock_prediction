import json
import time

import boto3
from botocore.exceptions import ClientError

iam_client = boto3.client("iam")

S3_ACCESS_ROLE_NAME = "EC2S3AccessRole"
S3_ACCESS_POLICY_NAME = "EC2S3AccessPolicy"
BUCKET_NAME = "capstone-project-bucket-mops"
PREDICTIONS_FILE_NAME = "predictions.feather"

# Define the policy document for S3 access
S3_ACCESS_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:CreateBucket",
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:GetBucketLocation",
            ],
            "Resource": [
                f"arn:aws:s3:::{BUCKET_NAME}",  # Replace with your bucket ARN
                f"arn:aws:s3:::{BUCKET_NAME}/*",  # Replace with your bucket ARN
            ],
        }
    ],
}


def create_s3_access_iam_role(iam_client):
    try:
        # Check if the role already exists
        response = iam_client.get_role(RoleName=S3_ACCESS_ROLE_NAME)
        print(f"IAM role {S3_ACCESS_ROLE_NAME} already exists.")
        return response["Role"]["Arn"]
    except iam_client.exceptions.NoSuchEntityException:
        print(f"IAM role {S3_ACCESS_ROLE_NAME} does not exist. Creating it.")
    except Exception as e:
        print(f"Failed to create IAM role: {e}")
        raise

    # Create the IAM role
    assume_role_policy_document = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    )
    response = iam_client.create_role(
        RoleName=S3_ACCESS_ROLE_NAME,
        AssumeRolePolicyDocument=assume_role_policy_document,
    )
    role_arn = response["Role"]["Arn"]
    print(f"Created IAM role {S3_ACCESS_ROLE_NAME} with ARN {role_arn}.")

    # Attach the policy to the role
    iam_client.put_role_policy(
        RoleName=S3_ACCESS_ROLE_NAME,
        PolicyName=S3_ACCESS_POLICY_NAME,
        PolicyDocument=json.dumps(S3_ACCESS_POLICY),
    )
    print(f"Attached S3 access policy to IAM role {S3_ACCESS_ROLE_NAME}.")

    return role_arn


def get_or_create_instance_s3_access_profile(
    iam_client, profile_suffix="InstanceProfile"
):
    instance_profile_name = f"{S3_ACCESS_ROLE_NAME}{profile_suffix}"
    try:
        # Check if the instance profile exists
        iam_client.get_instance_profile(InstanceProfileName=instance_profile_name)
        print(f"Instance profile {instance_profile_name} already exists. Deleting it.")

        try:
            # detaching the role from the instance profile
            iam_client.remove_role_from_instance_profile(
                InstanceProfileName=instance_profile_name, RoleName=S3_ACCESS_ROLE_NAME
            )
        except ClientError as e:
            print(
                f"Trying to remove role from instance profile {instance_profile_name} failed: {e}"
            )
        # deleting the instance profile
        iam_client.delete_instance_profile(InstanceProfileName=instance_profile_name)
        time.sleep(2)  # Wait for deletion to complete
    except ClientError as e:
        print(f"Instance profile {instance_profile_name} error: {e}")

    # Create the instance profile again
    iam_client.create_instance_profile(InstanceProfileName=instance_profile_name)
    iam_client.add_role_to_instance_profile(
        InstanceProfileName=instance_profile_name, RoleName=S3_ACCESS_ROLE_NAME
    )

    return instance_profile_name


def resource_exists(func, *args, **kwargs):
    """
    Helper function to check if a resource exists before attempting to delete.
    """
    try:
        return func(*args, **kwargs)
    except ClientError as e:
        print(f"Resource not found: {e.response['Error']['Message']}")
        return False


def check_security_group_exists(ec2_resource, group_name):
    """
    Check if a security group exists by name.
    Returns the security group ID if it exists, otherwise None.
    """
    try:
        response = ec2_resource.meta.client.describe_security_groups(
            GroupNames=[group_name]
        )

        # If the group exists, return its ID
        if response["SecurityGroups"]:
            security_group_id = response["SecurityGroups"][0]["GroupId"]
            print(f"Security Group found with ID: {security_group_id}")
            return security_group_id
        else:
            print("Security Group not found.")
            return None
    except ec2_resource.meta.client.exceptions.ClientError as e:
        # If error occurs, it might be because the group doesn't exist
        if "InvalidGroup.NotFound" in str(e):
            print("Security Group not found.")
            return None
        else:
            # Re-raise any other exception
            raise


def create_security_group(
    ec2_resource,
    group_name,
    description,
    port8050=False,
):
    """
    Create a new security group.
    """
    # Check if the security group already exists
    security_group_id = check_security_group_exists(ec2_resource, group_name)

    if security_group_id:
        print(f"Security Group already exists with ID: {security_group_id}")
        return security_group_id

    # If it doesn't exist, create a new security group
    security_group = ec2_resource.create_security_group(
        GroupName=group_name, Description=description
    )

    # Allow inbound traffic for SSH ...
    IpPermissions = [
        {
            "IpProtocol": "tcp",
            "FromPort": 22,
            "ToPort": 22,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        }
    ]

    # ... and, optionally, for port 8050
    if port8050:
        IpPermissions.append(
            {
                "IpProtocol": "tcp",
                "FromPort": 8050,
                "ToPort": 8050,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            }
        )

    security_group.authorize_ingress(IpPermissions=IpPermissions)

    print(f"Security Group Created with ID: {security_group.id}")
    return security_group.id


def delete_security_group(ec2_resource, security_group_id):
    """
    Delete the security group by ID.
    """
    try:
        security_group = ec2_resource.SecurityGroup(security_group_id)
        security_group.delete()
        print(f"Security Group {security_group_id} deleted.")
    except ClientError as e:
        print(f"Error deleting security group {security_group_id}: {str(e)}")


def get_policy_arn(policy_name):
    try:
        # Listing policies and filtering by policy name
        response = iam_client.list_policies(
            Scope="Local"
        )  # Scope can be 'Local' or 'AWS'
        for policy in response["Policies"]:
            if policy["PolicyName"] == policy_name:
                print(f"Custom policy already exists: {policy['Arn']}")
                return policy["Arn"]
        print("Policy not found.")
        return None
    except ClientError as e:
        print(f"An error occurred: {e}")
        return None
