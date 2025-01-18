# How to use the deployment scripts

In this directory we provide scripts to perform a full deployment of the dashboard. The process involves the following steps:
1. Create a custom AMI containing all dependencies including this repo installed, to be used for all instances we launch for different purposes.
2. Create resources for automated model retraining. This includes setting up triggers to launch an instance for retraining using, managing the associated IAM and a trigger to delete shutdown instances. This is achieved by using EventBridge rules and AWS Lambda functions.
3. Deploy the dashboard for serving using an Auto scaling group to launch more or less instances according to the load of requests.

After the dashboard is live, to shut everything down and eliminate all resources, please follow the "cleanup" instructions in the following section in reversed order (i.e., make sure that all resources of each step are properly deleted before deleting the previous step).


## `ami_creator.py`

1. Run the script with default argument to launch an instance and install all dependencies:
 ```
 python ami_creator.py
```
Connect to the machine and look at the tail of the following file to see when the instance is ready

```
$ tail -n 100 -f /var/log/user-data.log
```

2. Run the script with the `make-ami` argument

```
python ami_creator.py make-ami
```

Then manually delete the instance launched to create the AMI after it is ready

3. After checking the AMI is ready in the AWS EC2 console, terminate the instance.

NOTE: To repeat the ami creation, please run the cleanup command first and be sure to delete any remaining snaphshots in the EC2 console.

```
python ami_creator.py cleanup
```

## `daily_retraining_pipeline.py`

After the AMI is ready, you will need to launch a script to ensure the daily retraining pipeline runs periodically.

An event bridge event launches a lambda function every 24 hours to launch an instance with a Time To Live (TTL) of one hour, based on the AMI, and run the `stock_prediction/modeling/train.py` script. This downloads all the latest data, retrains the model and produces a `predictions.feather` file containing all the historical data and the next 20 day forecasts for all indices. The file is uploaded to an s3 bucket so that the dashboard can access it.

Note that, though the retraining instance self shutsdown it does not delete itself. Thus, we also have an eventbridge event to launch a lambda that looks for all instances with the "ShutdownBy" tag and deletes them if their TTL expired. All of this is controlled automatically by this script.

To deploy the retraining pipeline run
```bash
python daily_retraining_pipeline_deployer.py
```

If you wish to cleanup all resources you will need to run the following command (possibly several times after some waiting for all dependent resources to disappear!)

```bash
python daily_retraining_pipeline_deployer.py --cleanup
```

## Deploy the dashboard with `dashboard.py`

The last step consists of running a script that launches a group of instances to serve the dashboard. This group has autoscaling rules configured to either launch new instances to serve the dashboard in periods of high demand, or delete instances in periods of low demand.

To deploy the dashboard run:

```bash
python dashboard_deployer.py
```

This will also print the URL where the dashboard will be made available.

If you wish to kill the dashboard and cleanup all resources you will need to run the following command (possibly several times after some waiting for all dependent resources to disappear!)

```bash
python dashboard_deployer.py --cleanup
```
