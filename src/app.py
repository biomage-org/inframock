import boto3
import requests
import backoff
import logging
import sys
import json
import os
from cfn_tools import load_yaml

logger = logging.getLogger("inframock")
out_hdlr = logging.StreamHandler(sys.stdout)
out_hdlr.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
out_hdlr.setLevel(logging.DEBUG)
logger.addHandler(out_hdlr)
logger.setLevel(logging.DEBUG)

populate_mock = os.getenv("POPULATE_MOCK")
mock_data_path = os.getenv("MOCK_EXPERIMENT_DATA_PATH")

environment = "development"

@backoff.on_exception(backoff.expo, Exception, max_time=20)
def wait_for_localstack():
    requests.get("http://localstack:4566")


def provision_biomage_stack():
    RESOURCES = ("dynamo", "s3", "sns")

    cf = boto3.resource("cloudformation", endpoint_url="http://localstack:4566")

    for resource in RESOURCES:
        path = f"https://raw.githubusercontent.com/biomage-ltd/iac/master/cf/{resource}.yaml"

        r = requests.get(path)
        stack_template = r.text

        stack = cf.create_stack(
            StackName=f"biomage-{resource}-development",
            TemplateBody=stack_template,
            Parameters=[
                {
                    "ParameterKey": "Environment",
                    "ParameterValue": "development",
                },
            ],
        )

    sns = boto3.client("sns", endpoint_url="http://localstack:4566")

    logger.warning(sns.list_topics())

    logger.info("Stack created.")
    return stack

def populate_mock_dynamo():
    with open('mock_experiment.json') as json_file:
        experiment_data = json.load(json_file)

    experiment_data["matrixPath"] = "biomage-source-{}/{}.h5ad".format(environment, experiment_data["experimentId"])

    dynamo = boto3.resource('dynamodb', endpoint_url="http://localstack:4566")
    table = dynamo.Table("experiments-{}".format(environment))
    table.put_item(
        Item=experiment_data
    )

    logger.info("Mocked experiment loaded into local DynamoDB.")

    return experiment_data


def find_biomage_source_bucket_name():
    return "biomage-source-development"


def populate_mock_s3(experiment_id):
    logger.debug(
        "Downloading data file to upload to mock S3 "
        f"for experiment id {experiment_id} ..."
    )

    # download test file and save locally
    r = requests.get(mock_data_path, allow_redirects=True)
    with open(f"{experiment_id}.h5ad", "wb") as f:
        f.write(r.content)

    logger.debug("Downloaded. Now uploading to S3...")
    # upload to s3
    s3 = boto3.client("s3", endpoint_url="http://localstack:4566")
    s3.upload_file(
        Filename=f"{experiment_id}.h5ad",
        Bucket=find_biomage_source_bucket_name(),
        Key=f"{experiment_id}/python.h5ad",
    )
    logger.info("Mocked experiment data successfully uploaded to S3.")


def main():
    logger.info(
        "InfraMock local service started. Waiting for LocalStack to be brought up..."
    )
    wait_for_localstack()

    logger.info("LocalStack is up. Provisioning Biomage stack...")
    provision_biomage_stack()

    if populate_mock == "true":
        logger.info("Going to populate mock S3/DynamoDB with experiment data.")
        mock_experiment = populate_mock_dynamo()

        logger.info("Going to upload mocked experiment data to S3.")
        populate_mock_s3(experiment_id=mock_experiment["experimentId"])

    region = os.getenv("AWS_DEFAULT_REGION")
    logger.info("*" * 80)
    logger.info(f"InfraMock is RUNNING in mocked region {region}")
    logger.info("Check `docker-compose.yaml` for ports to acces services.")
    logger.info("Any other questions? Read the README, or ask on #engineering.")
    logger.info("*" * 80)


main()