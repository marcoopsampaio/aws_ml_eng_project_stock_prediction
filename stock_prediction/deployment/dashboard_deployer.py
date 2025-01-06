import argparse
import base64
import time

import boto3
import yaml
from botocore.exceptions import ClientError

from stock_prediction.deployment.utils import (
    DEFAULT_REGION,
    check_security_group_exists,
    create_s3_access_iam_role,
    create_security_group,
    delete_security_group,
    get_or_create_instance_s3_access_profile,
)
from stock_prediction.helpers.logging.log_config import get_logger

logger = get_logger()

USER_DATA_SCRIPT = """#!/bin/bash
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

poetry run python ./stock_prediction/dashboard/dashboard.py
"""

# get DEFAULT_AMI_ID from info.yaml
with open("info.yaml", "r") as yaml_file:
    info = yaml.safe_load(yaml_file)
    DEFAULT_AMI_ID = info.get("AMI_ID")
DEFAULT_INSTANCE_TYPE = "t2.micro"
DEFAULT_KEY_NAME = "capstone_project"

DEFAULT_SECURITY_GROUP_NAME = "dashboard-sg"
DEFAULT_LAUNCH_TEMPLATE_NAME = "dashboard-launch-template"
DEFAULT_TARGET_GROUP_NAME = "dashboard-tg"
DEFAULT_LOAD_BALANCER_NAME = "dashboard-lb"
DEFAULT_AUTO_SCALING_GROUP_NAME = "dashboard-asg"

DEFAULT_SCALE_UP_POLICY_NAME = "ScaleUpPolicy"
DEFAULT_SCALE_DOWN_POLICY_NAME = "ScaleDownPolicy"


def make_launch_template(
    ec2_client,
    launch_template_name,
    security_group_id,
    user_data_script,
    key_name,
    instance_profile_arn,
):
    user_data_base64 = base64.b64encode(user_data_script.encode("utf-8")).decode(
        "utf-8"
    )
    try:
        response = ec2_client.describe_launch_templates(
            LaunchTemplateNames=[launch_template_name]
        )
        if response["LaunchTemplates"]:
            logger.info(
                f"Launch Template {launch_template_name} already exists. Reusing."
            )
            return response["LaunchTemplates"][0]["LaunchTemplateId"]
    except ClientError as e:
        if "InvalidLaunchTemplateName.NotFoundException" in str(e):
            logger.info(
                f"Launch Template {launch_template_name} does not exist. Creating."
            )
            response = ec2_client.create_launch_template(
                LaunchTemplateName=launch_template_name,
                LaunchTemplateData={
                    "ImageId": DEFAULT_AMI_ID,
                    "InstanceType": DEFAULT_INSTANCE_TYPE,
                    "SecurityGroupIds": [security_group_id],
                    "UserData": user_data_base64,
                    "KeyName": key_name,
                    "IamInstanceProfile": {
                        "Arn": instance_profile_arn  # Attach IAM role to instance
                    },
                },
            )
            return response["LaunchTemplate"]["LaunchTemplateId"]
        else:
            raise


def make_target_group(elb_client, target_group_name, vpc_id):
    try:
        response = elb_client.describe_target_groups(Names=[target_group_name])
        if response["TargetGroups"]:
            logger.info(f"Target Group {target_group_name} already exists. Reusing.")
            return response["TargetGroups"][0]["TargetGroupArn"]
    except ClientError as e:
        if "TargetGroupNotFound" in str(e):
            logger.info(f"Target Group {target_group_name} does not exist. Creating.")
            response = elb_client.create_target_group(
                Name=target_group_name,
                Protocol="HTTP",
                Port=8050,  # Dash app port
                VpcId=vpc_id,
                TargetType="instance",
            )
            return response["TargetGroups"][0]["TargetGroupArn"]
        else:
            raise


def make_load_balancer(elb_client, load_balancer_name, subnet_ids, security_group_id):
    try:
        response = elb_client.describe_load_balancers(Names=[load_balancer_name])
        if response["LoadBalancers"]:
            logger.info(f"Load Balancer {load_balancer_name} already exists. Reusing.")
            return response["LoadBalancers"][0]["LoadBalancerArn"]
    except ClientError as e:
        if "LoadBalancerNotFound" in str(e):
            logger.info(f"Load Balancer {load_balancer_name} does not exist. Creating.")
            response = elb_client.create_load_balancer(
                Name=load_balancer_name,
                Subnets=subnet_ids,
                SecurityGroups=[security_group_id],
                Scheme="internet-facing",
                Type="application",
            )
            return response["LoadBalancers"][0]["LoadBalancerArn"]
        else:
            raise


def make_auto_scaling_group(
    autoscaling_client,
    autoscaling_group_name,
    launch_template_id,
    target_group_arn,
    subnet_ids,
):
    try:
        response = autoscaling_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[autoscaling_group_name]
        )
        if response["AutoScalingGroups"]:
            logger.info(
                f"Auto Scaling Group {autoscaling_group_name} already exists. Reusing."
            )
            return
    except ClientError as e:
        if "AutoScalingGroupNotFound" not in str(e):
            raise

    print(f"Creating Auto Scaling Group {autoscaling_group_name}.")
    autoscaling_client.create_auto_scaling_group(
        AutoScalingGroupName=autoscaling_group_name,
        LaunchTemplate={"LaunchTemplateId": launch_template_id},
        MinSize=1,
        MaxSize=3,
        DesiredCapacity=1,
        TargetGroupARNs=[target_group_arn],
        VPCZoneIdentifier=",".join(subnet_ids),
    )


def get_load_balancer_url(elb_client, load_balancer_name):
    """
    Extract the URL of the load balancer.

    :param elb_client: Boto3 ELB client
    :param load_balancer_name: Name of the load balancer
    :return: The DNS name of the load balancer (URL to access)
    """
    try:
        response = elb_client.describe_load_balancers(Names=[load_balancer_name])
        if response["LoadBalancers"]:
            load_balancer_dns_name = response["LoadBalancers"][0]["DNSName"]
            load_balancer_url = f"http://{load_balancer_dns_name}:8050"  # Dash app port
            return load_balancer_url
        else:
            logger.info(f"Load Balancer {load_balancer_name} not found.")
            return None
    except ClientError as e:
        logger.error(f"Error getting Load Balancer URL: {str(e)}")
        return None


def deploy_with_autoscaling(
    autoscaling_client,
    elb_client,
    security_group_id,
    subnet_ids,
    user_data_script=USER_DATA_SCRIPT,
    key_name=DEFAULT_KEY_NAME,
    launch_template_name=DEFAULT_LAUNCH_TEMPLATE_NAME,
    target_group_name=DEFAULT_TARGET_GROUP_NAME,
    load_balancer_name=DEFAULT_LOAD_BALANCER_NAME,
    scale_up_policy_name=DEFAULT_SCALE_UP_POLICY_NAME,
    scale_down_policy_name=DEFAULT_SCALE_DOWN_POLICY_NAME,
):
    ec2_client = boto3.client("ec2", region_name=DEFAULT_REGION)
    iam_client = boto3.client("iam", region_name=DEFAULT_REGION)

    _ = create_s3_access_iam_role(iam_client)  # Create IAM role with S3 permissions
    instance_profile_name = get_or_create_instance_s3_access_profile(
        iam_client, profile_suffix="DashboardInstanceProfile"
    )  # Create Instance Profile

    # get instance profile arn from instance profile name
    response = iam_client.get_instance_profile(
        InstanceProfileName=instance_profile_name
    )
    instance_profile_arn = response["InstanceProfile"]["Arn"]
    logger.info(f"Instance Profile ARN: {instance_profile_arn}")
    time.sleep(30)

    # create launch template
    launch_template_id = make_launch_template(
        ec2_client=ec2_client,
        launch_template_name=launch_template_name,
        security_group_id=security_group_id,
        user_data_script=user_data_script,
        key_name=key_name,
        instance_profile_arn=instance_profile_arn,
    )

    response = ec2_client.describe_subnets(SubnetIds=subnet_ids)
    vpc_id = response["Subnets"][0]["VpcId"]
    logger.info(f"VPC ID extracted from subnet {subnet_ids[0]}: {vpc_id}")

    target_group_arn = make_target_group(
        elb_client=elb_client,
        target_group_name=target_group_name,
        vpc_id=vpc_id,
    )

    load_balancer_arn = make_load_balancer(
        elb_client=elb_client,
        load_balancer_name=load_balancer_name,
        subnet_ids=subnet_ids,
        security_group_id=security_group_id,
    )

    logger.info(f"Load Balancer ARN: {load_balancer_arn}")
    logger.info(
        "To access the dashboard after creation, use the URL: "
        f"{get_load_balancer_url(elb_client, load_balancer_name)}"
    )

    logger.info("Creating Listener for Load Balancer")
    elb_client.create_listener(
        LoadBalancerArn=load_balancer_arn,
        Protocol="HTTP",
        Port=8050,
        DefaultActions=[{"Type": "forward", "TargetGroupArn": target_group_arn}],
    )
    logger.info("Listener created and attached to Load Balancer")

    autoscaling_group_name = "dashboard-asg"
    make_auto_scaling_group(
        autoscaling_client=autoscaling_client,
        autoscaling_group_name=autoscaling_group_name,
        launch_template_id=launch_template_id,
        target_group_arn=target_group_arn,
        subnet_ids=subnet_ids,
    )

    # Create ScaleUp policy
    logger.info("Creating ScaleUp policy")
    scale_up_policy = autoscaling_client.put_scaling_policy(
        AutoScalingGroupName=autoscaling_group_name,
        PolicyName=scale_up_policy_name,
        AdjustmentType="ChangeInCapacity",
        ScalingAdjustment=1,
        Cooldown=300,
    )
    scale_up_policy_arn = scale_up_policy["PolicyARN"]

    # Create ScaleDown policy
    logger.info("Creating ScaleDown policy")
    scale_down_policy = autoscaling_client.put_scaling_policy(
        AutoScalingGroupName=autoscaling_group_name,
        PolicyName=scale_down_policy_name,
        AdjustmentType="ChangeInCapacity",
        ScalingAdjustment=-1,
        Cooldown=300,
    )
    scale_down_policy_arn = scale_down_policy["PolicyARN"]

    # Create CloudWatch alarms
    logger.info("Creating CloudWatch alarms")
    cloudwatch_client = boto3.client("cloudwatch", region_name=DEFAULT_REGION)
    cloudwatch_client.put_metric_alarm(
        AlarmName="ScaleUpAlarm",
        MetricName="CPUUtilization",
        Namespace="AWS/EC2",
        Statistic="Average",
        Period=300,
        Threshold=70.0,
        ComparisonOperator="GreaterThanThreshold",
        Dimensions=[{"Name": "AutoScalingGroupName", "Value": autoscaling_group_name}],
        EvaluationPeriods=1,
        AlarmActions=[scale_up_policy_arn],
    )
    cloudwatch_client.put_metric_alarm(
        AlarmName="ScaleDownAlarm",
        MetricName="CPUUtilization",
        Namespace="AWS/EC2",
        Statistic="Average",
        Period=300,
        Threshold=20.0,
        ComparisonOperator="LessThanThreshold",
        Dimensions=[{"Name": "AutoScalingGroupName", "Value": autoscaling_group_name}],
        EvaluationPeriods=1,
        AlarmActions=[scale_down_policy_arn],
    )


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


def delete_auto_scaling_group(autoscaling_client, group_name):
    """
    Delete the Auto Scaling Group by name.
    """
    try:
        response = autoscaling_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[group_name]
        )
        if response["AutoScalingGroups"]:
            autoscaling_client.delete_auto_scaling_group(
                AutoScalingGroupName=group_name, ForceDelete=True
            )
            logger.info(f"Auto Scaling Group {group_name} deleted.")
    except ClientError as e:
        logger.info(f"Error deleting Auto Scaling Group {group_name}: {str(e)}")


def delete_load_balancer(elb_client, load_balancer_name):
    """
    Delete the Load Balancer by name.
    """
    try:
        response = elb_client.describe_load_balancers(Names=[load_balancer_name])
        if response["LoadBalancers"]:
            load_balancer_arn = response["LoadBalancers"][0]["LoadBalancerArn"]
            elb_client.delete_load_balancer(LoadBalancerArn=load_balancer_arn)
            logger.info(f"Load Balancer {load_balancer_name} deleted.")
    except ClientError as e:
        logger.info(f"Error deleting Load Balancer {load_balancer_name}: {str(e)}")


def delete_target_group(elb_client, target_group_name):
    """
    Delete the Target Group by name.
    """
    try:
        response = elb_client.describe_target_groups(Names=[target_group_name])
        if response["TargetGroups"]:
            target_group_arn = response["TargetGroups"][0]["TargetGroupArn"]
            elb_client.delete_target_group(TargetGroupArn=target_group_arn)
            logger.info(f"Target Group {target_group_name} deleted.")
    except ClientError as e:
        logger.info(f"Error deleting Target Group {target_group_name}: {str(e)}")


def delete_launch_template(ec2_client, launch_template_name):
    """
    Delete the Launch Template by name.
    """
    try:
        response = ec2_client.describe_launch_templates(
            LaunchTemplateNames=[launch_template_name]
        )
        if response["LaunchTemplates"]:
            launch_template_id = response["LaunchTemplates"][0]["LaunchTemplateId"]
            ec2_client.delete_launch_template(LaunchTemplateId=launch_template_id)
            logger.info(f"Launch Template {launch_template_name} deleted.")
    except ClientError as e:
        logger.info(f"Error deleting Launch Template {launch_template_name}: {str(e)}")


def delete_resources(ec2_resource, autoscaling_client, elb_client):

    # Delete Auto Scaling Group
    delete_auto_scaling_group(autoscaling_client, DEFAULT_AUTO_SCALING_GROUP_NAME)

    # Delete Load Balancer
    delete_load_balancer(elb_client, DEFAULT_LOAD_BALANCER_NAME)

    # Delete Launch Template
    ec2_client = boto3.client("ec2", region_name=DEFAULT_REGION)
    delete_launch_template(ec2_client, DEFAULT_LAUNCH_TEMPLATE_NAME)

    # Delete Target Group
    delete_target_group(elb_client, DEFAULT_TARGET_GROUP_NAME)

    # Delete Security Group
    security_group_id = check_security_group_exists(
        ec2_resource, DEFAULT_SECURITY_GROUP_NAME
    )
    if security_group_id:
        delete_security_group(ec2_resource, security_group_id)


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Deploy or clean up the deployment.")
    parser.add_argument(
        "--cleanup", action="store_true", help="Cleanup the deployment resources"
    )
    args = parser.parse_args()

    # Initialize resources and clients
    ec2_resource = boto3.resource("ec2", region_name=DEFAULT_REGION)
    autoscaling_client = boto3.client("autoscaling", region_name=DEFAULT_REGION)
    elb_client = boto3.client("elbv2", region_name=DEFAULT_REGION)

    if args.cleanup:
        delete_resources(ec2_resource, autoscaling_client, elb_client)
    else:
        # Create a Security Group
        security_group_id = create_security_group(
            ec2_resource=ec2_resource,
            group_name=DEFAULT_SECURITY_GROUP_NAME,
            description="Security group for Dash dashboard",
            port8050=True,
        )
        # Get_public_subnets
        subnet_ids = get_public_subnets(ec2_resource)
        # Create Auto Scaling Group and Load Balancer
        deploy_with_autoscaling(
            autoscaling_client, elb_client, security_group_id, subnet_ids
        )


if __name__ == "__main__":
    main()
