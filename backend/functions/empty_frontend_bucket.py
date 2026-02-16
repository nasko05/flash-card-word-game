import json
import traceback
import urllib.error
import urllib.request

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")


def send_cfn_response(event: dict, context, status: str, data: dict | None = None, reason: str | None = None):
    response_body = {
        "Status": status,
        "Reason": reason or f"See CloudWatch Log Stream: {context.log_stream_name}",
        "PhysicalResourceId": event.get("PhysicalResourceId", context.log_stream_name),
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "NoEcho": False,
        "Data": data or {},
    }

    body_bytes = json.dumps(response_body).encode("utf-8")
    request = urllib.request.Request(
        event["ResponseURL"],
        data=body_bytes,
        method="PUT",
        headers={
            "content-type": "",
            "content-length": str(len(body_bytes)),
        },
    )

    try:
        with urllib.request.urlopen(request):
            pass
    except urllib.error.URLError as err:
        print(f"Failed to send CloudFormation response: {err}")


def delete_in_batches(bucket_name: str, objects: list[dict]):
    for i in range(0, len(objects), 1000):
        batch = objects[i : i + 1000]
        s3.delete_objects(
            Bucket=bucket_name,
            Delete={"Objects": batch, "Quiet": True},
        )


def empty_bucket(bucket_name: str):
    try:
        version_paginator = s3.get_paginator("list_object_versions")
        for page in version_paginator.paginate(Bucket=bucket_name):
            objects_to_delete: list[dict] = []

            for version in page.get("Versions", []):
                objects_to_delete.append(
                    {
                        "Key": version["Key"],
                        "VersionId": version["VersionId"],
                    }
                )

            for marker in page.get("DeleteMarkers", []):
                objects_to_delete.append(
                    {
                        "Key": marker["Key"],
                        "VersionId": marker["VersionId"],
                    }
                )

            if objects_to_delete:
                delete_in_batches(bucket_name, objects_to_delete)
    except ClientError as error:
        error_code = error.response.get("Error", {}).get("Code", "")
        if error_code != "NoSuchBucket":
            raise
        return

    object_paginator = s3.get_paginator("list_objects_v2")
    for page in object_paginator.paginate(Bucket=bucket_name):
        objects_to_delete = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if objects_to_delete:
            delete_in_batches(bucket_name, objects_to_delete)


def lambda_handler(event, context):
    print("Received event:", json.dumps(event))
    request_type = event.get("RequestType")
    bucket_name = event.get("ResourceProperties", {}).get("BucketName")

    try:
        if request_type == "Delete" and bucket_name:
            empty_bucket(bucket_name)

        send_cfn_response(
            event,
            context,
            "SUCCESS",
            data={"BucketName": bucket_name or ""},
        )
    except Exception as error:
        print("Bucket cleanup failed:", traceback.format_exc())
        send_cfn_response(
            event,
            context,
            "FAILED",
            data={"BucketName": bucket_name or ""},
            reason=str(error),
        )
