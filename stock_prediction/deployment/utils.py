from botocore.exceptions import ClientError


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
