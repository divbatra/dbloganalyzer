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
logging.basicConfig(level=logging.DEBUG)  # Set logging level to DEBUG to capture all logs
logger = logging.getLogger(__name__)

# Setup basic variables
compartment_id = "ocid1.compartment.oc1..aaa********************************fsbq"
CONFIG_PROFILE = "DEFAULT"
config = oci.config.from_file('/home/opc/loganalyzer/config', CONFIG_PROFILE)
endpoint = "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com"
object_storage_path = 'output/'

# Initialize Generative AI Inference client
generative_ai_inference_client = oci.generative_ai_inference.GenerativeAiInferenceClient(
    config=config,
    service_endpoint=endpoint,
    retry_strategy=oci.retry.NoneRetryStrategy(),
    timeout=(100, 240)
)

def extract_ora_error_lines(log_text):
    """
    Extracts lines containing ORA errors from the log text.
    """
    logger.debug("Extracting ORA error lines from log text.")
    ora_line_pattern = re.compile(r'^ORA-\d+(?!.*warning).*', re.MULTILINE | re.IGNORECASE)
    ora_error_lines = ora_line_pattern.findall(log_text)
    return ora_error_lines

def soda_insert(ordsbaseurl, schema, dbuser, dbpwd, document, collection_name="errors_log"):
    """
    Inserts a document in Autonomous Database (ADB).
    """
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

def generate_response_for_error(ora_error, sequence_number, responses, output_lock, ordsbaseurl, schema, dbuser, dbpwd, input_filename):
    """
    Generates a response (probable solution) for a given ORA error using Generative AI.
    """
    try:
        # Prepare request for Generative AI
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

        # Write to ADW (Autonomous Database)
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
    """
    Generates a summary for the list of ORA errors using Generative AI.
    """
    try:
        # Prepare request for Generative AI
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
        generate_text_detail.serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(model_id="ocid1.generativeaimodel.oc1.us-chicago-1.amaaaaaask7dceyafhwal37hxwylnpbcncidimbwteff4xha77n5xz4m7p6a")
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
            logger.error(f"Error while inserting into collection Summary_Errors: {str(insert_status)}")

def generate_responses_for_ora_errors(input_file_name, namespace_name, bucket_name, object_storage_file_path, ordsbaseurl, schema, dbuser, dbpwd):
    """
    Orchestrates the generation of responses and summaries for ORA errors and write output back to object storage.
    """
    logger.debug("Initializing OCI Object Storage client.")
    object_storage_client = oci.object_storage.ObjectStorageClient(config=config)

    try:
        # Read the log file from Object Storage
        logger.debug(f"Fetching log file {object_storage_file_path} from bucket {bucket_name}.")
        log_object = object_storage_client.get_object(
            namespace_name=namespace_name, 
            bucket_name=bucket_name, 
            object_name=object_storage_file_path
        )
        log_text = log_object.data.text
        logger.debug(f"Log file fetched. Size: {len(log_text)} characters.")

        # Extract ORA errors from the log
        ora_error_lines = extract_ora_error_lines(log_text)
        logger.debug(f"Extracted {len(ora_error_lines)} ORA error lines.")

        if not ora_error_lines:
            logger.warning("No ORA errors found in the log file.")
            return

        responses = []
        output_lock = threading.Lock()
        threads = []

        # Generate responses for each ORA error line
        for i, ora_error in enumerate(ora_error_lines, start=1):
            thread = threading.Thread(
                target=generate_response_for_error, 
                args=(ora_error, i, responses, output_lock, ordsbaseurl, schema, dbuser, dbpwd, input_file_name)
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads to finish
        for thread in threads:
            thread.join()

        logger.debug(f"Generated responses for {len(responses)} ORA errors.")

        # Generate summary for the ORA errors
        summary_lock = threading.Lock()
        summary_thread = threading.Thread(
            target=generate_summary, 
            args=(ora_error_lines, len(ora_error_lines), summary_lock, ordsbaseurl, schema, dbuser, dbpwd, input_file_name)
        )
        summary_thread.start()
        summary_thread.join()

        logger.debug("Completed response and summary generation process.")

    except oci.exceptions.ServiceError as e:
        logger.error(f"An OCI service error occurred: {e}")
        raise

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise

def handler(ctx, data: io.BytesIO = None):
    """
    Oracle Functions handler for processing log files to extract ORA errors, generate responses, and summaries.
    """
    try:
        body = json.loads(data.getvalue())
        logger.debug(f"Received request body: {body}")

        # Extract necessary parameters
        input_file_name = body['input_file_name']
        namespace_name = body['namespace_name']
        bucket_name = body['bucket_name']
        object_storage_file_path = body['object_storage_file_path']
        ordsbaseurl = body['ordsbaseurl']
        schema = body['schema']
        dbuser = body['dbuser']
        dbpwd = body['dbpwd']

        # Start the processing
        logger.debug("Starting the ORA error processing pipeline.")
        generate_responses_for_ora_errors(input_file_name, namespace_name, bucket_name, object_storage_file_path, ordsbaseurl, schema, dbuser, dbpwd)

        # Return a success response
        return response.Response(
            ctx, 
            response_data=json.dumps({"status": "success"}),
            headers={"Content-Type": "application/json"}
        )

    except Exception as e:
        logger.error(f"An error occurred during the function handler execution: {e}")
        return response.Response(
            ctx, 
            response_data=json.dumps({"status": "error", "message": str(e)}),
            headers={"Content-Type": "application/json"}
        )
