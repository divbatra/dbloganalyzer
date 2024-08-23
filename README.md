## Introduction

This tool performs Comprehensive Log Analysis. It analyzes log files uploaded to extract ORA errors, generates responses and summaries using Oracle Cloud Infrastructure's Generative AI service, and stores the results in Oracle Autonomous Data Warehouse (ADW) via the SODA API.

## Features

- **Log Extraction**: Extracts ORA error lines from a provided log file.
- **Response Generation**: Uses Generative AI to create probable solutions for each ORA error.
- **Summary Generation**: Summarizes the ORA errors, categorizing them without exposing error details.
- **Data Storage**: Stores the generated solutions and summaries in ADW collections using the SODA API.
- **Output Management**: Uploads the generated responses to Oracle Object Storage.

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


## Deploy the function
In Cloud Shell, run the *fn deploy* command to build the function and its dependencies as a Docker image, 
push the image to OCIR, and deploy the function to Oracle Functions in your application.

![user input icon](./images/userinput.png)
```
fn -v deploy --app <app-name>
```


## Set the function configuration values
The function requires several configuration variables to be set.

![user input icon](./images/userinput.png)

Use the *fn CLI* to set the config value:
```
fn config function <app-name> <function-name> ords-base-url <ORDS Base URL>
fn config function <app-name> <function-name> db-schema <DB schema>
fn config function <app-name> <function-name> db-user <DB user name>
fn config function <app-name> <function-name> dbpwd-cipher <DB encrypted password>
fn config function <app-name> <function-name> input-bucket <input bucket name>
fn config function <app-name> <function-name> processed-bucket <processed bucket name>
```
e.g.
```
fn config function myapp oci-adb-ords-runsql-python ords-base-url "https://xxxxxx-db123456.adb.us-region.oraclecloudapps.com/ords/"
fn config function myapp oci-adb-ords-runsql-python db-schema "admin"
fn config function myapp oci-adb-ords-runsql-python db-user "admin"
fn config function myapp oci-adb-ords-runsql-python dbpwd-cipher "xxxxxxxxx"
fn config function myapp oci-adb-ords-runsql-python input-bucket "input-bucket"
fn config function myapp oci-adb-ords-runsql-python processed-bucket "processed-bucket"
```


## Create an Event rule
Let's configure a Cloud Event to trigger the function when files are dropped into your *input* bucket.

![user input icon](./images/userinput.png)

Go to the OCI console > Application Integration > Events Service. Click *Create Rule*.

![user input icon](./images/1-create_event_rule.png)

Assign a display name and a description.
In the *Rule Conditions* section,create 3 conditions:
* type = *Event Type*, Service Name = *Object Storage*, Event Type = *Object - Create*
* type = *Attribute*, Attribute Name = *compartmentName*, Attribute Value = *your compartment name*
* type = *Attribute*, Attribute Name = *bucketName*, Attribute Value = *your input bucket*
In the *Actions* section, set the *Action type* as "Functions", select your *Function Compartment*, your *Function Application*, and your *Function ID*.

![user input icon](./images/2-create_event_rule.png)


## Test
Finally, let's test the workflow.

![user input icon](./images/userinput.png)

Upload one or all CSV files from the current folder to your *input bucket*. Let's imagine those files contains sales data from different regions of the world.

On the OCI console, navigate to *Autonomous Data Warehouse* and click on your database, click on *Service Console*, navigate to Development, and click on *SQL Developer Web*. Authenticate with your ADMIN username and password.
Enter the following query in the *worksheet* of *SQL Developer Web*:
```sql
select json_serialize (JSON_DOCUMENT) from regionsnumbers;

```
You should see the data from the CSV files. To learn more about JSON in Oracle Database, refer to Chris Saxon's blog [How to Store, Query, and Create JSON Documents in Oracle Database](https://blogs.oracle.com/sql/how-to-store-query-and-create-json-documents-in-oracle-database)



## File Structure

- **analyze_log**: Main entry function for analyzing logs.
- **extract_ora_error_lines**: Extracts ORA errors from the log text.
- **generate_responses_for_ora_errors**: Generates solutions and summaries for extracted ORA errors.
- **generate_response_for_error**: Generates a response for a single ORA error.
- **generate_summary**: Generates a summary of all extracted ORA errors.
- **soda_insert**: Inserts data into an ADW SODA collection.
- **truncate_collection**: Truncates a SODA collection in ADW (commented out for safety).

## Logging

Logging is configured at the DEBUG level to capture detailed information. Logs will output to the console by default.

## Error Handling

The script includes error handling mechanisms that log issues at various stages of the process. If an error occurs during log analysis or Generative AI inference, the function will return a detailed error message.

## Contributing

Contributions are welcome! Please submit a pull request or open an issue to discuss any changes.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
