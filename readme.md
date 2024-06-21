# Transportation Public Works Socrata Reporting

This repo stores scripts for publishing metadata about public and private datasets owned by the Austin Transportation and Public Works Department stored on the [open data portal](https://data.austintexas.gov/). This metadata is stored in a separate [dataset](https://data.austintexas.gov/Transportation-and-Mobility/Data-and-Technology-Services-Datasets/28ys-ieqv/about_data).

Inspired by the City of Chattanooga's [data inventory dataset](https://www.chattadata.org/Government/City-of-Chattanooga-Data-Inventory/wuph-stbt/about_data).

## Metadata publishing

`socrata_metadata_pub.py` publishes metadata of the assets published on the city's open data portal for items which are owned by the Transportation Public Works account or those in the "Transportation and Mobility" category.

`$ python etl/socrata_metadata_pub.py`

Running this above command will fully replace the metadata dataset with the latest metadata. There are no arguments accepted by the script.

## Docker

This repo can be used with a docker container. You can either build it yourself with:

`$ docker build . -t dts-socrata-reporting:production`

or pull from our dockerhub account:

`$ docker pull atddocker/dts-socrata-reporting:production`

Then, provide the environment variables described in env_template to the docker image:

`$ docker run -it --env-file env_file dts-socrata-reporting:production /bin/bash` 

Then, provide the command you would like to run.