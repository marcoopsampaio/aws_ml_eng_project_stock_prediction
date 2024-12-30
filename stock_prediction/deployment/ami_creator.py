import argparse
import os

import boto3
import yaml

from stock_prediction.deployment.utils import create_security_group

# AWS Configuration
REGION = "us-east-1"
INSTANCE_TYPE = "t2.micro"
AMI_ID = "ami-0e2c8caa4b6378d8c"
KEY_NAME = "capstone_project"
SECURITY_GROUP_NAME = "custom-security-group"
INFO_FILE = "info.yaml"

# Initialize Boto3 clients
ec2_client = boto3.client("ec2", region_name=REGION)
ec2_resource = boto3.resource("ec2", region_name=REGION)


def launch_instance(security_group_id):

    user_data_script = """#!/bin/bash
sudo -u root bash << "EOF" > /var/log/user-data.log 2>&1

cd ~

# Update system packages
echo "Updating system packages..."
sudo apt update -y

# Install necessary dependencies
sudo apt install -y \
make build-essential libssl-dev zlib1g-dev libbz2-dev \
libreadline-dev libsqlite3-dev wget curl llvm libncurses-dev \
xz-utils tk-dev libffi-dev liblzma-dev python3-openssl git curl unzip

# Clone the repository
git clone https://github.com/marcoopsampaio/aws_ml_eng_project_stock_prediction.git
cd aws_ml_eng_project_stock_prediction/

# Go to the relevant branch
git checkout marcoopsampaio/model_development
./scripts/setup_environment.sh

# Prepare .bashrc to source pyenv
cat << "EOL" >> /root/.bashrc
export PYENV_ROOT="/root/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
EOL

source /root/.bashrc

export PYENV_ROOT="/root/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

# Install the repo
./scripts/setup_environment.sh

# Cleanup unnecessary stuff to create a clean AMI
# Remove unnecessary packages
sudo apt-get autoremove --purge -y
sudo apt-get clean
sudo apt-get autoclean

# Clear temporary files and logs
sudo rm -rf /tmp/*
sudo rm -rf /var/tmp/*
sudo rm -rf /var/log/*.log

# Clear Bash history
history -c
sudo rm -f ~/.bash_history

echo "Instance is ready to use."
EOF
"""
    instance = ec2_client.run_instances(
        ImageId=AMI_ID,
        InstanceType=INSTANCE_TYPE,
        KeyName=KEY_NAME,
        SecurityGroupIds=[security_group_id],
        MinCount=1,
        MaxCount=1,
        UserData=user_data_script,
    )
    instance_id = instance["Instances"][0]["InstanceId"]
    print(f"Instance {instance_id} launched with user data script.")
    return instance_id


def create_image(instance_id, name="custom-ubuntu-ami"):
    response = ec2_client.create_image(
        InstanceId=instance_id,
        Name=name,
        Description="Custom Ubuntu AMI with pre-installed repo and dependencies",
        NoReboot=False,
    )
    ami_id = response["ImageId"]
    print(f"AMI {ami_id} is being created.")

    return ami_id


def terminate_instance(instance_id):
    try:
        ec2_client.terminate_instances(InstanceIds=[instance_id])
        print(f"Instance {instance_id} terminated.")
    except Exception as e:
        print(f"Error terminating instance {instance_id}: {e}")


def cleanup():
    if not os.path.exists(INFO_FILE):
        print("No info file found. Nothing to clean up.")
        return

    with open(INFO_FILE, "r") as yaml_file:
        info = yaml.safe_load(yaml_file)

    instance_id = info.get("InstanceID")
    ami_id = info.get("AMI_ID")

    # Deregister the AMI
    try:
        ec2_client.deregister_image(ImageId=ami_id)
        print(f"AMI {ami_id} deregistered.")
    except Exception as e:
        print(f"Error deregistering AMI {ami_id}: {e}")

    # Delete the snapshots associated with the AMI
    try:
        # Get the snapshot IDs associated with the AMI
        images = ec2_client.describe_images(ImageIds=[ami_id])
        for image in images["Images"]:
            for block_device in image.get("BlockDeviceMappings", []):
                snapshot_id = block_device.get("Ebs", {}).get("SnapshotId")
                if snapshot_id:
                    ec2_client.delete_snapshot(SnapshotId=snapshot_id)
                    print(f"Snapshot {snapshot_id} deleted.")
    except Exception as e:
        print(f"Error deleting snapshots for AMI {ami_id}: {e}")

    # Terminate the instance
    if instance_id:
        terminate_instance(instance_id)

    # Remove the YAML file
    os.remove(INFO_FILE)
    print("Cleanup complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Manage AWS instance and AMI creation."
    )

    # Add 3 possible values to pass: cleanup, make-ami or launch-instance (default)
    parser.add_argument(
        "option",
        choices=["cleanup", "make-ami", "launch-instance"],
        nargs="?",
        default="launch-instance",
    )

    args = parser.parse_args()

    if args.option == "cleanup":
        cleanup()
    elif args.option == "make-ami":
        if os.path.exists(INFO_FILE):
            info = yaml.safe_load(open(INFO_FILE, "r"))
            instance_id = info.get("InstanceID")
            ami_id = info.get("AMI_ID")
            if ami_id:
                print(f"AMI {ami_id} already exists. Skipping AMI creation.")
                exit(0)

            if instance_id:
                ami_id = create_image(instance_id)
                # Update the YAML file with the new AMI ID
                info["AMI_ID"] = ami_id
                with open(INFO_FILE, "w") as yaml_file:
                    yaml.dump(info, yaml_file)
            else:
                print("No instance ID found in the YAML file.")

        else:
            print(
                f"{INFO_FILE} not found. Please run with no arguments first to launch instance."
            )
    elif args.option == "launch-instance":
        if os.path.exists(INFO_FILE):
            print(
                f"Instance information already exists in {INFO_FILE}. Stopping execution."
            )
        else:
            # Ensure security group exists or create it
            security_group_id = create_security_group(
                ec2_resource, SECURITY_GROUP_NAME, "Custom security group for instances"
            )

            # Launch instance and set up environment
            instance_id = launch_instance(security_group_id)

            # Save instance ID and security group name to YAML file
            ami_info = {"InstanceID": instance_id, "SecurityGroup": SECURITY_GROUP_NAME}
            with open(INFO_FILE, "w") as yaml_file:
                yaml.dump(ami_info, yaml_file)
    else:
        print(
            "Invalid option. Please choose 'cleanup', 'make-ami' or 'launch-instance'."
        )
