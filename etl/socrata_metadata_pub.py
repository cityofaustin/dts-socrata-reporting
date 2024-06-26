"""
Extract metadata about datasets owned and maintained by DTS
and publishes the data in another dataset.
"""
import asyncio
import aiohttp
from aiohttp import BasicAuth, ClientTimeout
from datetime import datetime
import json
import logging
import os
import pytz
import requests
from requests.auth import HTTPBasicAuth

from sodapy import Socrata

import utils

# Socrata creds
SO_WEB = os.getenv("SO_WEB")
SO_TOKEN = os.getenv("SO_TOKEN")
SO_USER = os.getenv("SO_KEY")
SO_PASS = os.getenv("SO_SECRET")
RESOURCE_ID = "28ys-ieqv"

# Unique ID for the data publishing account
ATD_USER_ID = "8t3r-wq64"

BASE_URL = "https://data.austintexas.gov/d/"
EDP_URL = "https://datahub.austintexas.gov/d/"

OUT_FIELDS = [
    "id",
    "name",
    "description",
    "attribution",
    "type",
    "updatedAt",
    "createdAt",
    "metadata_updated_at",
    "data_updated_at",
    "download_count",
    "publication_date",
    "page_views_last_week",
    "page_views_last_month",
    "page_views_total",
]


def extract():
    logger.info("Extracting data")
    basic = HTTPBasicAuth(username=SO_USER, password=SO_PASS)

    # first, get public assets
    res = requests.get(
        f"https://api.us.socrata.com/api/catalog/v1?domains=datahub.austintexas.gov&limit=10000",
    )
    odp_data = json.loads(res.text)

    # then get datahub assets
    res = requests.get(
        f"https://api.us.socrata.com/api/catalog/v1?domains=datahub.austintexas.gov&limit=10000",
        auth=basic,
    )
    edp_data = json.loads(res.text)

    odp_ids = [a["resource"]["id"] for a in odp_data["results"]]

    # Determining if the asset is public or private requires us comparing the two responses
    data = []
    for resource in edp_data["results"]:
        if resource["resource"]["id"] in odp_ids:
            resource["is_public"] = True
        else:
            resource["is_public"] = False

        # Filtering to only DTS account's assets or those with the "Transportation and Mobility" category
        if "domain_category" not in resource["classification"]:
            resource["classification"]["domain_category"] = ""
        if (
            resource["owner"]["id"] == ATD_USER_ID
            or resource["classification"]["domain_category"]
            == "Transportation and Mobility"
        ):
            # Filter to not include draft assets
            if ":" not in resource["resource"]["id"]:
                data.append(resource)
    return data


def convert_tz(date_str):
    if not date_str:
        return None

    # Get UTC timestamp as datetime object
    utc_datetime = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    utc_timezone = pytz.timezone("UTC")
    utc_datetime = utc_timezone.localize(utc_datetime)

    # Convert to central time
    central_timezone = pytz.timezone("US/Central")
    central_datetime = utc_datetime.astimezone(central_timezone)

    # To socrata format
    central_timestamp_string = central_datetime.strftime("%Y-%m-%dT%H:%M:%S")

    return central_timestamp_string


def transform(data):
    logger.info("Transforming data")

    # metadata fields to pull
    fields = {
        "Publishing-Information_Automation-Method": "automation_method",
        "Publishing-Information_Automation-Method-(if-Other)": "automation_method_other",
        "Publishing-Information_Update-Frequency": "update_frequency",
        "Publishing-Information_Spatial-Information": "spatial_information",
        "Ownership_Department-name": "department_name",
        "Ownership_Program-Name": "program_name",
        "Strategic-Area_Strategic-Direction-Outcome": "strategic_area",
    }

    output_data = []
    for row in data:
        row["resource"]["page_views_last_week"] = row["resource"]["page_views"][
            "page_views_last_week"
        ]
        row["resource"]["page_views_last_month"] = row["resource"]["page_views"][
            "page_views_last_month"
        ]
        row["resource"]["page_views_total"] = row["resource"]["page_views"][
            "page_views_total"
        ]
        filtered_data = {key: row["resource"][key] for key in OUT_FIELDS}

        # URL to dataset is based on if it is public or not
        if row["is_public"]:
            filtered_data["dataset_url"] = BASE_URL + filtered_data["id"]
            filtered_data["is_public"] = True
        else:
            filtered_data["dataset_url"] = EDP_URL + filtered_data["id"]
            filtered_data["is_public"] = False

        # Convert UTC time to local time
        filtered_data["updatedAt"] = convert_tz(filtered_data["updatedAt"])
        filtered_data["createdAt"] = convert_tz(filtered_data["createdAt"])
        filtered_data["metadata_updated_at"] = convert_tz(
            filtered_data["metadata_updated_at"]
        )
        filtered_data["data_updated_at"] = convert_tz(filtered_data["data_updated_at"])
        filtered_data["publication_date"] = convert_tz(
            filtered_data["publication_date"]
        )

        filtered_data["owner_display_name"] = row["owner"]["display_name"]

        if "domain_tags" in row["classification"]:
            filtered_data["tags"] = ", ".join(
                str(x) for x in row["classification"]["domain_tags"]
            )
        else:
            filtered_data["tags"] = ""

        # flattens the domain_private_metadata and domain_metadata into one dict, metadata
        metadata = {}
        if "domain_private_metadata" in row["classification"]:
            for item in row["classification"]["domain_private_metadata"]:
                metadata[item["key"]] = item["value"]
        for item in row["classification"]["domain_metadata"]:
            metadata[item["key"]] = item["value"]

        # getting metadata, but checking if it is present first
        for field in fields:
            if field in metadata:
                filtered_data[fields[field]] = metadata[field]
            else:
                filtered_data[fields[field]] = ""

        output_data.append(filtered_data)

    return output_data


async def fetch(session, resource_id, auth):
    """
    Task for fetching the number of rows a dataset using a SoQL query.
    """
    url = f"https://datahub.austintexas.gov/resource/{resource_id}.json?$select=count(*) as count"
    async with session.get(url, auth=auth, headers={"X-App-Token": SO_TOKEN}) as response:
        res = await response.json()
        return {"id": resource_id, "row_count": res[0]["count"]}


async def get_row_counts(data):
    """
    Get the number of rows in each dataset async.
    """
    basic = BasicAuth(SO_USER, SO_PASS)
    timeout = ClientTimeout(total=20*60)  # Setting a cap timeout to 20 minutes

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = []
        for row in data:
            if row["type"] == "dataset":
                tasks.append(fetch(session, row["id"], basic))

        results = await asyncio.gather(*tasks)

    for result in results:
        for row in data:
            if row["id"] == result["id"]:
                row["row_count"] = result["row_count"]

    return data


def load(soda, data):
    logger.info("Publishing data to Socrata")
    res = soda.replace(RESOURCE_ID, data)
    logger.info(res)


def main():
    client = Socrata(SO_WEB, SO_TOKEN, username=SO_USER, password=SO_PASS, timeout=240)
    data = extract()
    data = transform(data)
    data = asyncio.run(get_row_counts(data))
    load(client, data)


if __name__ == "__main__":
    logger = utils.get_logger(__file__, level=logging.DEBUG)
    main()
