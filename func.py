import io
import json
import logging
import oci
import re
import requests
import time
import threading
from fdk import response

# Setup logging
logging.basicConfig(level=logging.DEBUG)  # Changed to DEBUG level to capture all logs
logger = logging.getLogger(__name__)

# Setup basic variables
compartment_id = "ocid1.compartment.oc1..aaaaaaaada7sesidnelvwkurhxxqz4n3w6mna6a3df2b2kulnbdffjxxfsbq"
CONFIG_PROFILE = "DEFAULT"
config = oci.config.from_file('/home/opc/loganalyzer/config', CONFIG_PROFILE)
endpoint = "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com"
object_storage_path = 'output/'

generative_ai_inference_client = oci.generative_ai_inference.GenerativeAiInferenceClient(
    config=config,
    service_endpoint=endpoint,
    retry_strategy=oci.retry.NoneRetryStrategy(),
    timeout=(100, 240)
)

def extract_ora_error_lines(log_text):
    logger.debug("Extracting ORA error lines from log text.")
    ora_line_pattern = re.compile(r'^ORA-\d+(?!.*warning).*', re.MULTILINE | re.IGNORECASE)
    ora_error_lines = ora_line_pattern.findall(log_text)
    return ora_error_lines

def generate_response_for_error(ora_error, sequence_number, responses, output_lock, ordsbaseurl, schema, dbuser, dbpwd, input_filename):
    try:
        # Prepare request
        cohere_generate_text_request = oci.generative_ai_inference.models.CohereLlmInferenceRequest()
        cohere_generate_text_request.prompt = (
            f'Please provide ora-error solution. It should show SQL query as well. '
            f'Solution should be crisp and clear and short. Content:\n{ora_error}'
        )
        cohere_generate_text_request.is_stream = False
        cohere_generate_text_request.max_tokens = 500
        cohere_generate_text_request.temperature = 0.75
        cohere_generate_text_request.top_p = 0.7
        cohere_generate_text_request.frequency_penalty = 1.0
        
        generate_text_detail = oci.generative_ai_inference.models.GenerateTextDetails()
        generate_text_detail.serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(model_id="cohere.command")
        generate_text_detail.compartment_id = compartment_id
        generate_text_detail.inference_request = cohere_generate_text_request

        # Request generation
        logger.debug("Sending request to Generative AI Inference service.")
        generate_text_response = generative_ai_inference_client.generate_text(generate_text_detail)
        generated_texts = generate_text_response.data.inference_response.generated_texts
        probable_solution = generated_texts[0].text

    except Exception as e:
        logger.error(f"An error occurred during text generation: {e}")
        probable_solution = "An error occurred during text generation"

    with output_lock:
        response_entry = {
            "sequence_number": sequence_number,
            "ora_error": ora_error,
            "solution": probable_solution
        }
        responses.append(response_entry)

        # Write to ADW
        document = {
            "sequence_number": sequence_number,
            "ora_error": ora_error,
            "solution": probable_solution,
            "input_filename": input_filename
        }
        insert_status = soda_insert(ordsbaseurl, schema, dbuser, dbpwd, document, collection_name="errors_log")
        if "id" in insert_status.get("items", [{}])[0]:
            logger.debug(f"Successfully inserted document ID {insert_status['items'][0]['id']} into collection errors_log")
        else:
            logger.error(f"Error while inserting into collection errors_log: {str(insert_status)}")

def generate_summary(ora_errors, sequence_number, summary_lock, ordsbaseurl, schema, dbuser, dbpwd, input_filename):
    try:
        # Generate the summary using Generative AI
        cohere_generate_text_request = oci.generative_ai_inference.models.CohereLlmInferenceRequest()
        cohere_generate_text_request.prompt = (
            "Print total error count.\n"
            "Classify errors into major error categories, don't display error details. Content:\n"
            f"{' '.join(ora_errors)}"
        )
        cohere_generate_text_request.is_stream = False
        cohere_generate_text_request.max_tokens = 800
        cohere_generate_text_request.temperature = 0.75
        cohere_generate_text_request.top_p = 0.7
        cohere_generate_text_request.frequency_penalty = 1.0
        
        generate_text_detail = oci.generative_ai_inference.models.GenerateTextDetails()
        generate_text_detail.serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(model_id="cohere.command")
        generate_text_detail.compartment_id = compartment_id
        generate_text_detail.inference_request = cohere_generate_text_request

        logger.debug("Sending request to Generative AI Inference service for summary.")
        generate_text_response = generative_ai_inference_client.generate_text(generate_text_detail)
        generated_texts = generate_text_response.data.inference_response.generated_texts
        summary_text = generated_texts[0].text

    except Exception as e:
        logger.error(f"An error occurred during summary generation: {e}")
        summary_text = "An error occurred during summary generation"

    with summary_lock:
        # Write summary to ADW
        summary_document = {
            "sequence_number": sequence_number,
            "summary": summary_text,
            "input_filename": input_filename
        }
        insert_status = soda_insert(ordsbaseurl, schema, dbuser, dbpwd, summary_document, collection_name="Summary_Errors")
        if "id" in insert_status.get("items", [{}])[0]:
            logger.debug(f"Successfully inserted summary document ID {insert_status['items'][0]['id']} into collection Summary_Errors")
        else:
            logger.error(f"Error while inserting summary into collection Summary_Errors: {str(insert_status)}")

def generate_responses_for_ora_errors(ora_errors, namespace_name, bucket_name, object_storage_file_path, ordsbaseurl, schema, dbuser, dbpwd):
    threads = []
    responses = []
    summary_lock = threading.Lock()
    output_lock = threading.Lock()

    # Define input_filename here
    input_filename = object_storage_file_path.split("/")[-1].split(".")[0]  

    for sequence_number, ora_error in enumerate(set(ora_errors), start=1):
        thread = threading.Thread(target=generate_response_for_error, args=(ora_error, sequence_number, responses, output_lock, ordsbaseurl, schema, dbuser, dbpwd, input_filename))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    # Generate summary
    logger.info("Generating summary of errors.")
    generate_summary(ora_errors, len(ora_errors), summary_lock, ordsbaseurl, schema, dbuser, dbpwd, input_filename)

    output_file_content = ""
    for response in sorted(responses, key=lambda x: x['sequence_number']):
        output_file_content += f"{response['sequence_number']}. Error: {response['ora_error']}\n"
        output_file_content += f"-------------------------------------------------------------------------\n"
        output_file_content += f"Probable Solution: {response['solution']}\n"
        output_file_content += f"-------------------------------------------------------------------------\n"

    logger.debug("Uploading output file to Object Storage.")
    object_storage_client = oci.object_storage.ObjectStorageClient(config)
    object_storage_client.put_object(
        namespace_name=namespace_name,
        bucket_name=bucket_name,
        object_name=object_storage_file_path,
        put_object_body=output_file_content.encode("utf-8")
    )
    logger.debug("Output file uploaded successfully.")

    return output_file_content

def soda_insert(ordsbaseurl, schema, dbuser, dbpwd, document, collection_name="errors_log"):
    logger.debug(f"Inserting document into SODA. URL: {ordsbaseurl}/{schema}/soda/latest/{collection_name}, Document: {document}")
    try:
        auth = (dbuser, dbpwd)
        sodaurl = ordsbaseurl + '/admin' + '/soda/latest/'
        collectionurl = sodaurl + collection_name
        headers = {'Content-Type': 'application/json'}
        r = requests.post(collectionurl, auth=auth, headers=headers, data=json.dumps(document))

        # Log the raw response text for debugging
        logger.debug(f"Raw response from SODA API: {r.text}")

        if r.status_code == 200:
            try:
                r_json = r.json()  # Try to parse JSON from the response
                logger.debug(f"SODA insert response: {r_json}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON from response: {e}")
                r_json = {}  # Default to an empty dict or handle as needed
        else:
            logger.error(f"SODA API returned status code {r.status_code}")
            r_json = {}

    except Exception as e:
        logger.error(f"Error inserting document into collection {collection_name}: {e}")
        raise

    return r_json


def analyze_log(ctx, data: io.BytesIO):
    logger.debug("Starting log analysis.")
    try:
        if not data.getvalue():
            raise ValueError("Empty input data")

        req_data = json.loads(data.getvalue())
        log_object_storage_url = req_data.get('log_object_storage_url')
        ordsbaseurl = req_data.get('ords_base_url')
        schema = req_data.get('db_schema')
        dbuser = req_data.get('db_user')
        dbpwd = req_data.get('db_pwd')

        logger.debug(f"Parameters - log_object_storage_url: {log_object_storage_url}, ords_base_url: {ordsbaseurl}, db_schema: {schema}, db_user: {dbuser}")

        if not all([log_object_storage_url, ordsbaseurl, schema, dbuser, dbpwd]):
            logger.error("Missing one or more required parameters in the JSON payload.")
            return response.Response(
                ctx, response_data=json.dumps({'error': 'Missing one or more required parameters in the JSON payload'}),
                headers={"Content-Type": "application/json"}, status_code=400
            )

        logger.info(f"Downloading log file from {log_object_storage_url}")
        namespace_name = log_object_storage_url.split("/")[4]
        bucket_name = log_object_storage_url.split("/")[6]
        object_name = log_object_storage_url.split("/")[-1]

        logger.debug(f"Object Storage - Namespace: {namespace_name}, Bucket: {bucket_name}, Object: {object_name}")

        object_storage_client = oci.object_storage.ObjectStorageClient(config)
        object_content = object_storage_client.get_object(namespace_name=namespace_name, bucket_name=bucket_name, object_name=object_name).data.content

        log_text = io.BytesIO(object_content).read().decode('utf-8')

        ora_error_lines = extract_ora_error_lines(log_text)
        if not ora_error_lines:
            logger.info("No ORA errors found in the log file.")
            return response.Response(
                ctx, response_data=json.dumps({'message': 'No ORA errors found in the log file'}),
                headers={"Content-Type": "application/json"}, status_code=200
            )

        logger.info("Generating responses for ORA errors.")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        input_filename = object_name.split(".")[0]  # Extract the base filename without extension
        object_storage_file_path = f"output/{input_filename}_{timestamp}.txt"

        output_file_content = generate_responses_for_ora_errors(
            ora_errors=ora_error_lines,
            namespace_name=namespace_name,
            bucket_name=bucket_name,
            object_storage_file_path=object_storage_file_path,
            ordsbaseurl=ordsbaseurl,
            schema=schema,
            dbuser=dbuser,
            dbpwd=dbpwd
        )

        return response.Response(
            ctx, response_data=json.dumps({'message': 'Log analysis completed successfully', 'output_file_path': object_storage_file_path}),
            headers={"Content-Type": "application/json"}, status_code=200
        )

    except Exception as e:
        logger.error(f"Error during log analysis: {e}")
        return response.Response(
            ctx, response_data=json.dumps({'error': str(e)}),
            headers={"Content-Type": "application/json"}, status_code=500
        )
