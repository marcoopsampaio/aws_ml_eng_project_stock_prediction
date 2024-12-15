import boto3

USER_DATA_SCRIPT = """#!/bin/bash
echo "User data script started" > /var/log/user-data.log

# Update and install necessary packages
sudo apt-get update -y >> /var/log/user-data.log 2>&1
sudo apt-get install python3 python3-pip python3-venv -y >> /var/log/user-data.log 2>&1

# Create a virtual environment in the /home/ubuntu directory
python3 -m venv /home/ubuntu/dash_env >> /var/log/user-data.log 2>&1

# Activate the virtual environment and install Dash
source /home/ubuntu/dash_env/bin/activate >> /var/log/user-data.log 2>&1
pip install dash >> /var/log/user-data.log 2>&1

# Create a simple Dash app
echo "from dash import Dash\napp = Dash(__name__)\nimport dash.html as html\napp.layout = html.Div('Hello, Dash!')\napp.run(host='0.0.0.0', port=8050)" > /home/ubuntu/dashboard.py

# Run the Dash app in the background
nohup /home/ubuntu/dash_env/bin/python /home/ubuntu/dashboard.py >> /var/log/user-data.log 2>&1 &

echo "User data script completed" >> /var/log/user-data.log
    """
DEFAULT_AMI_ID = "ami-0e2c8caa4b6378d8c"
DEFAULT_INSTANCE_TYPE = "t2.micro"


def check_security_group_exists(ec2_resource, group_name="dashboard-sg"):
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
    group_name="dashboard-sg",
    description="Security group for Dash dashboard",
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

    # Allow inbound traffic for SSH and Dash port (8050)
    security_group.authorize_ingress(
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            },
            {
                "IpProtocol": "tcp",
                "FromPort": 8050,
                "ToPort": 8050,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            },
        ]
    )

    print(f"Security Group Created with ID: {security_group.id}")
    return security_group.id


def delete_security_group_if_exists(ec2_resource, group_name="dashboard-sg"):
    """
    Delete the security group if it exists.
    """
    # Check if the security group exists
    security_group_id = check_security_group_exists(ec2_resource, group_name)

    if security_group_id:
        print(f"Deleting existing security group with ID: {security_group_id}")
        ec2_resource.meta.client.delete_security_group(GroupId=security_group_id)
        print("Security Group deleted.")
    else:
        print("No security group to delete.")


def launch_ec2_instance(ec2_resource, security_group_id, key_name):
    # Define the user data script
    user_data_script = USER_DATA_SCRIPT

    # Launch an EC2 instance
    instances = ec2_resource.create_instances(
        ImageId=DEFAULT_AMI_ID,  # Replace with a valid AMI ID
        InstanceType=DEFAULT_INSTANCE_TYPE,
        KeyName=key_name,
        SecurityGroupIds=[security_group_id],
        MinCount=1,
        MaxCount=1,
        UserData=user_data_script,
    )

    instance = instances[0]
    print(f"EC2 Instance launched with ID: {instance.id}")

    # Wait until the instance is running
    instance.wait_until_running()
    instance.load()

    print(f"EC2 Instance {instance.id} is now running.")
    return instance.id


def create_auto_scaling_group(
    autoscaling_client, elb_client, security_group_id, subnet_ids
):
    ec2_client = boto3.client("ec2")
    import base64

    # TODO: this is not working yet but almost there
    # TODO: check if other groups and stuff created below should be checked if they exist
    # Base64 encode the UserData script
    user_data_base64 = base64.b64encode(USER_DATA_SCRIPT.encode("utf-8")).decode(
        "utf-8"
    )

    # TODO: check if template exists and delete if
    # Create a Launch Template
    launch_template = ec2_client.create_launch_template(
        LaunchTemplateName="dashboard-launch-template",
        LaunchTemplateData={
            "ImageId": DEFAULT_AMI_ID,  # Replace with your AMI ID
            "InstanceType": DEFAULT_INSTANCE_TYPE,
            "SecurityGroupIds": [security_group_id],
            "UserData": user_data_base64,
        },
    )

    launch_template_id = launch_template["LaunchTemplate"]["LaunchTemplateId"]
    print(f"Launch Template created with ID: {launch_template_id}")

    # Describe the subnet to get its VPC ID
    response = ec2_client.describe_subnets(SubnetIds=subnet_ids)
    vpc_id = response["Subnets"][0]["VpcId"]
    print(f"VPC ID extracted from subnet {subnet_ids[0]}: {vpc_id}")

    # Create a Target Group for the Load Balancer
    target_group_response = elb_client.create_target_group(
        Name="dashboard-tg",
        Protocol="HTTP",
        Port=8050,
        VpcId=vpc_id,
        TargetType="instance",
    )
    target_group_arn = target_group_response["TargetGroups"][0]["TargetGroupArn"]
    print(f"Target Group created with ARN: {target_group_arn}")

    # Create a Load Balancer
    load_balancer_response = elb_client.create_load_balancer(
        Name="dashboard-lb",
        Subnets=subnet_ids,
        SecurityGroups=[security_group_id],
        Scheme="internet-facing",
        Type="application",
    )
    load_balancer_arn = load_balancer_response["LoadBalancers"][0]["LoadBalancerArn"]
    print(f"Load Balancer created with ARN: {load_balancer_arn}")

    # Attach the Target Group to the Load Balancer
    elb_client.create_listener(
        LoadBalancerArn=load_balancer_arn,
        Protocol="HTTP",
        Port=8050,
        DefaultActions=[{"Type": "forward", "TargetGroupArn": target_group_arn}],
    )
    print("Listener created and attached to Load Balancer")

    # Create Auto Scaling Group
    autoscaling_client.create_auto_scaling_group(
        AutoScalingGroupName="dashboard-asg",
        LaunchTemplate={
            "LaunchTemplateId": launch_template_id,
        },
        MinSize=1,
        MaxSize=3,
        DesiredCapacity=1,
        TargetGroupARNs=[target_group_arn],
        VPCZoneIdentifier=",".join(subnet_ids),
    )
    print("Auto Scaling Group created")

    # Create ScaleUp policy based on CPU utilization
    scale_up_policy = autoscaling_client.put_scaling_policy(
        AutoScalingGroupName="dashboard-asg",
        PolicyName="ScaleUpPolicy",
        AdjustmentType="ChangeInCapacity",
        ScalingAdjustment=1,  # Number of instances to add
        Cooldown=300,  # Cooldown period (in seconds)
        MetricAggregationType="Average",
        EstimatedInstanceWarmup=300,  # Time to wait after instance launch before considering the metric
    )
    print("ScaleUp policy created")

    # Create ScaleDown policy based on CPU utilization
    scale_down_policy = autoscaling_client.put_scaling_policy(
        AutoScalingGroupName="dashboard-asg",
        PolicyName="ScaleDownPolicy",
        AdjustmentType="ChangeInCapacity",
        ScalingAdjustment=-1,  # Number of instances to remove
        Cooldown=300,  # Cooldown period (in seconds)
        MetricAggregationType="Average",
        EstimatedInstanceWarmup=300,  # Time to wait after instance launch before considering the metric
    )
    print("ScaleDown policy created")

    cloudwatch_client = boto3.client("cloudwatch")

    # Create CloudWatch Alarm for ScaleUp (CPU > 70%)
    cloudwatch_client.put_metric_alarm(
        AlarmName="ScaleUpAlarm",
        MetricName="CPUUtilization",
        Namespace="AWS/EC2",
        Statistic="Average",
        Period=300,  # 5 minutes
        Threshold=1.0,
        ComparisonOperator="GreaterThanThreshold",
        Dimensions=[{"Name": "AutoScalingGroupName", "Value": "dashboard-asg"}],
        EvaluationPeriods=1,
        AlarmActions=[scale_up_policy["PolicyARN"]],
        OKActions=[scale_up_policy["PolicyARN"]],
        InsufficientDataActions=[scale_up_policy["PolicyARN"]],
    )
    print("ScaleUp CloudWatch alarm created")

    # Create CloudWatch Alarm for ScaleDown (CPU < 20%)
    cloudwatch_client.put_metric_alarm(
        AlarmName="ScaleDownAlarm",
        MetricName="CPUUtilization",
        Namespace="AWS/EC2",
        Statistic="Average",
        Period=300,  # 5 minutes
        Threshold=0.0,
        ComparisonOperator="LessThanThreshold",
        Dimensions=[{"Name": "AutoScalingGroupName", "Value": "dashboard-asg"}],
        EvaluationPeriods=1,
        AlarmActions=[scale_down_policy["PolicyARN"]],
        OKActions=[scale_down_policy["PolicyARN"]],
        InsufficientDataActions=[scale_down_policy["PolicyARN"]],
    )
    print("ScaleDown CloudWatch alarm created")


def get_public_subnets(ec2_resource):
    """
    Function to return a list of public subnets in the AWS account.

    A public subnet is defined as one that has a route to an Internet Gateway (IGW).

    :param ec2_resource: Boto3 EC2 resource object
    :return: List of subnet IDs that are public
    """
    # Describe all subnets
    subnets = ec2_resource.subnets.all()

    # Initialize an empty list to store public subnets
    public_subnet_ids = []

    # Iterate through subnets and check their route tables
    for subnet in subnets:
        subnet_id = subnet.id

        # Get the route tables associated with the subnet
        route_tables = ec2_resource.route_tables.filter(
            Filters=[{"Name": "vpc-id", "Values": [subnet.vpc_id]}]
        )

        # Check if any route in the route table points to an internet gateway
        is_public = False

        for route_table in route_tables:
            for route in route_table.routes:
                if route.gateway_id and route.gateway_id.startswith("igw-"):
                    is_public = True
                    break

        # If the subnet has a route to an Internet Gateway, it's public
        if is_public:
            public_subnet_ids.append(subnet_id)

    return public_subnet_ids


def main():
    # Initialize resources and clients
    ec2_resource = boto3.resource("ec2")
    autoscaling_client = boto3.client("autoscaling")
    elb_client = boto3.client("elbv2")

    # Replace these placeholders with actual values
    key_name = "capstone_project"  # Ensure you have created this key pair

    # Create a Security Group
    security_group_id = create_security_group(ec2_resource)

    # Launch an EC2 Instance
    _ = launch_ec2_instance(ec2_resource, security_group_id, key_name)

    # Create Auto Scaling Group and Load Balancer
    # get_public_subnets
    subnet_ids = get_public_subnets(ec2_resource)
    create_auto_scaling_group(
        autoscaling_client, elb_client, security_group_id, subnet_ids
    )


if __name__ == "__main__":
    main()
