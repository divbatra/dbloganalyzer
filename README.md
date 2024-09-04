## Introduction

This tool performs Comprehensive Log Analysis. It analyzes log files uploaded to extract ORA errors, generates responses and summaries using Oracle Cloud Infrastructure's Generative AI service, and stores the results in Oracle Autonomous Data Warehouse (ADW) via the Simple Oracle Document Access (SODA) API.


## Features

- **Log Extraction**: Extracts ORA error lines from a provided log file.
- **Response Generation**: Uses Generative AI to create probable solutions for each ORA error.
- **Summary Generation**: Summarizes the ORA errors, categorizing them without exposing error details.
- **Data Storage**: Stores the generated solutions and summaries in ADW collections using the SODA API.
- **Output Management**: Uploads the generated responses to Oracle Object Storage.
<img width="388" alt="image" src="https://github.com/user-attachments/assets/2983fd4d-1019-46dd-a13f-4d0eba1dc389">


**Prerequisites**
Before you deploy this sample function, make sure you have run step A, B and C of the Oracle Functions Quick Start Guide for Cloud Shell at : https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsquickstartcloudshell.htm


**A - Set up your tenancy**

**B - Create application**

**C - Set up your Cloud Shell dev environment**

## List Applications 
Assuming your have successfully completed the prerequisites, you should see your 
application in the list of applications.
```
fn ls apps
```


## Create or Update your Dynamic Group
In order to use other OCI Services, your function must be part of a dynamic group. For information on how to create a dynamic group, refer to the [documentation](https://docs.cloud.oracle.com/iaas/Content/Identity/Tasks/managingdynamicgroups.htm#To).

When specifying the *Matching Rules*, we suggest matching all functions in a compartment with:
```
ALL {resource.type = 'fnfunc', resource.compartment.id = 'ocid1.compartment.oc1..aaaaaxxxxx'}
```
Please check the [Accessing Other Oracle Cloud Infrastructure Resources from Running Functions](https://docs.cloud.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsaccessingociresources.htm) for other *Matching Rules* options.


## Create Object Storage bucket.
You need one bucket in Object Storage. The bucket is the location where you will drop the log files to be analyzed

## Create or Update IAM Policies
Create a new policy that allows the dynamic group to manage objects in your two buckets. 

Also, create a policy to allow the Object Storage service in the region to manage object-family in tenancy. This policy is needed to copy/move objects from the input-bucket to the processed-bucket. If you miss this policy, you will see this error message when you run the function: `Permissions granted to the object storage service principal to this bucket are insufficient`. For more information, see [Object Storage - Service Permissions](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/copyingobjects.htm#Service).

Your policy should look something like this:
```
Allow dynamic-group <dynamic-group-name> to manage objects in compartment <compartment-name> where target.bucket.name='input-bucket'

Allow dynamic-group <dynamic-group-name> to manage objects in compartment <compartment-name> where target.bucket.name='processed-bucket'

Allow service objectstorage-<region_identifier> to manage object-family in tenancy 
e.g., Allow service objectstorage-ap-sydney-1 to manage object-family in tenancy
```
To determine the region identifier value of an Oracle Cloud Infrastructure region, see [Regions and Availability Domains](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm#top). 

For more information on how to create policies, check the [documentation](https://docs.cloud.oracle.com/iaas/Content/Identity/Concepts/policysyntax.htm).


## Create an Autonomous Data Warehouse
We are using APEX for front end, APEX is using ADW. Also, we are saving solution per error which is also parsed and saved in ADW table.
The function accesses Autonomous Database using SODA (Simple Oracle Document Access) for simplicity. Other type of access can be used by modifying the function.

Use an existing Autonomous DataWarehouse or create a new one as follows.

![image](https://github.com/user-attachments/assets/96dce1f8-041b-4b05-9fd3-7c14d36bf7ca)


On the OCI console, navigate to *Autonomous Data Warehouse* and click *Create Autonomous Database*. In the Create Autonomous Database dialog, enter the following:
- Display Name
- Compartment
- Database Name
- Infrastructure Type: Shared
- Admin password
- License type

For more information, go to https://docs.cloud.oracle.com/iaas/Content/Database/Tasks/adbcreating.htm

On the Service Console, navigate to Development and copy the ORDS Base URL, we will need it below.

From your terminal, create the collection 'Summary_Errors' and 'Errors_Log':
```bash
export ORDS_BASE_URL=<ADW-ORDS-URL>
curl -X PUT -u 'ADMIN:<DB password>' -H "Content-Type: application/json" $ORDS_BASE_URL/admin/soda/latest/Summary_Errors
```

```bash
export ORDS_BASE_URL=<ADW-ORDS-URL>
curl -X PUT -u 'ADMIN:<DB password>' -H "Content-Type: application/json" $ORDS_BASE_URL/admin/soda/latest/Errors_Log
```

List collections:
```bash
curl -u 'ADMIN:<DB-password>' -H "Content-Type: application/json" $ORDS_BASE_URL/admin/soda/latest/
```

## Review and customize the function
Review the following files in the current folder:
* the code of the function, [func.py](./func.py)
* its dependencies, [requirements.txt](./requirements.txt)
* the function metadata, [func.yaml](./func.yaml)

Please note you need to modify config file as per your tenancy, and generate key file and modify Docker file accordingly.
Please check https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm for help on how to generate a key-pair and calculate the key fingerprint.

  ## Lets drill down to understand function code:

- **analyze_log**: Main entry function for analyzing logs.
- **extract_ora_error_lines**: Extracts ORA errors from the log text.
- **generate_responses_for_ora_errors**: Generates solutions and summaries for extracted ORA errors.
- **generate_summary**: Generates a summary of all extracted ORA errors.
- **soda_insert**: Inserts data into an ADW SODA collection.



## Deploy the function
In Cloud Shell, run the *fn deploy* command to build the function and its dependencies as a Docker image, 
push the image to OCIR, and deploy the function to Oracle Functions in your application.

```
fn -v deploy --app <app-name>
```
You can find APEX Application details at : https://github.com/KritiR22/loganalyzerapp/tree/main

## Test
Flow can be tested using APEX by uploading the logfile. Once, you click on Analyze button. It will call the rest end point that we created using API gateway invoking the OCI Function explained below.

<img width="950" alt="image" src="https://github.com/user-attachments/assets/e35131ca-70a5-48c1-8aaa-029f44c5b98a">



Test can also be done using curl command and check output file created in Object storage with all solutions and also check you ADW collections to see summary and detailed log analysis.


```
echo -n '{"log_object_storage_url": "https://objectstorage.us-chicago-1.oraclecloud.com/n/****/b/**/o/MF_DP_APP1_IMPDP.log", "ords_base_url": "https://qfoidsyfqbriabt-....../ords", "db_schema": "....", "db_user": "...", "db_pwd": "..."}' | fn invoke AITests genai
```

