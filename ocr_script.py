import json
import requests
import random
import string
import logging
from datetime import datetime
import time
import sys
from typing import Dict, Any, Optional, Union, List, Tuple

# Configure logging with both file and terminal output
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
log_filename = f"ocr_comparison_{timestamp}.log"
results_filename = f"comparison_results_{timestamp}.txt"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Terminal output
        logging.FileHandler(log_filename)   # File output
    ]
)
logger = logging.getLogger("ocr_script")

def generate_random_id(length=6, numeric_only=False):
    """Generate a random ID: numeric if specified, otherwise alphanumeric."""
    if numeric_only:
        min_val = 10 ** (length - 1)
        max_val = (10 ** length) - 1
        return str(random.randint(min_val, max_val))
    else:
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))

def safe_get(obj: Dict[str, Any], *keys, default=None) -> Any:
    """Safely access nested dictionary keys without raising KeyError."""
    current = obj
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is None:
            return default
    return current

def load_json_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        logger.error(f"Error: File '{file_path}' not found.")
        return None
    except json.JSONDecodeError:
        logger.error(f"Error: File '{file_path}' contains invalid JSON.")
        return None
    except Exception as e:
        logger.error(f"Error: An unexpected error occurred while reading '{file_path}': {e}")
        return None

def fetch_json_from_api(pdf_path, process_endpoint, status_endpoint, headers=None, language="en", user_id=None, job_id=None, webhook_url=None, max_retries=3):
    try:
        user_id = user_id or generate_random_id(numeric_only=True)
        job_id = job_id or generate_random_id()
        
        with open(pdf_path, 'rb') as pdf_file:
            files = {'file': (f"{job_id}.pdf", pdf_file, 'application/pdf')}
            data = {'language': language or "en", 'user_id': user_id, 'test_id': job_id}
            
            logger.info(f"Sending PDF '{pdf_path}' to API at '{process_endpoint}'...")
            logger.info(f"Using job ID: {job_id}, user ID: {user_id}")
            logger.info(f"This process may take 5-25 minutes to complete.")
            start_time = time.time()

            retry_count = 0
            backoff_time = 5
            while retry_count < max_retries:
                try:
                    response = requests.post(
                        process_endpoint, 
                        headers=headers, 
                        files=files, 
                        data=data, 
                        timeout=600
                    )
                    response.raise_for_status()
                    break
                except requests.exceptions.RequestException as e:
                    retry_count += 1
                    if hasattr(e.response, 'text'):
                        logger.warning(f"API error response: {e.response.text[:1000]}")
                    if retry_count >= max_retries:
                        raise
                    logger.warning(f"API submission attempt {retry_count} failed: {str(e)}")
                    logger.warning(f"Retrying in {backoff_time} seconds...")
                    time.sleep(backoff_time)
                    backoff_time *= 2
                    pdf_file.seek(0)
            
            logger.info("API submission successful with status code 200")
            logger.info(f"PDF submitted successfully. Job ID: {job_id}")
            logger.info(f"Initial submission took {time.time() - start_time:.1f} seconds.")
            
            logger.info(f"Polling status endpoint for job {job_id}...")
            max_attempts = 10
            poll_interval = 180
            consecutive_errors = 0
            max_consecutive_errors = 3
            
            for attempt in range(1, max_attempts + 1):
                try:
                    status_url = f"{status_endpoint}/{job_id}"
                    elapsed_minutes = (time.time() - start_time) / 60
                    logger.info(f"Polling attempt {attempt}/{max_attempts}: {status_url} (Elapsed time: {elapsed_minutes:.1f} minutes)")
                    
                    status_retry_count = 0
                    status_backoff_time = 5
                    status_max_retries = 3
                    
                    while status_retry_count < status_max_retries:
                        try:
                            status_response = requests.get(status_url, timeout=30)
                            status_response.raise_for_status()
                            break
                        except requests.exceptions.RequestException as e:
                            status_retry_count += 1
                            if status_retry_count >= status_max_retries:
                                raise
                            logger.warning(f"Status check retry {status_retry_count}: {str(e)}")
                            time.sleep(status_backoff_time)
                            status_backoff_time *= 2
                    
                    status_data = status_response.json()
                    lab_reports = safe_get(status_data, 'lab_reports', default={})
                    
                    is_complete = False
                    has_valid_data = False
                    
                    if isinstance(lab_reports, dict):
                        progress = safe_get(lab_reports, 'progress')
                        status = safe_get(lab_reports, 'status')
                        is_complete = (progress == 100 and status == "complete")
                        data = safe_get(lab_reports, 'data')
                        has_valid_data = (data is not None and isinstance(data, list) and len(data) > 0)
                    
                    if is_complete:
                        logger.info(f"Processing marked as complete after {elapsed_minutes:.1f} minutes.")
                        if has_valid_data:
                            logger.info(f"Valid data found in response.")
                            return status_data
                        else:
                            logger.error(f"OCR completed but no valid data was extracted. Response: {json.dumps(status_data, indent=2)[:1000]}...")
                            raise ValueError("OCR completed but no valid data")
                    
                    progress_value = safe_get(lab_reports, 'progress', default=0)
                    if not isinstance(progress_value, (int, float)):
                        progress_value = 0
                    logger.info(f"Processing progress: {progress_value}%. Elapsed time: {elapsed_minutes:.1f} minutes.")
                    logger.info(f"Waiting {poll_interval/60:.1f} minutes before next check...")
                    consecutive_errors = 0
                    time.sleep(poll_interval)
                    
                except (requests.exceptions.RequestException, ValueError) as e:
                    consecutive_errors += 1
                    logger.error(f"Error during polling attempt {attempt}: {str(e)}")
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"Too many consecutive errors ({consecutive_errors}). Aborting.")
                        raise ValueError(f"Polling failed after {consecutive_errors} errors: {str(e)}")
                    error_wait = min(poll_interval, 60)
                    logger.info(f"Waiting {error_wait} seconds before retry...")
                    time.sleep(error_wait)
            
            elapsed_minutes = (time.time() - start_time) / 60
            logger.error(f"Processing timed out after {elapsed_minutes:.1f} minutes ({max_attempts} attempts)")
            raise TimeoutError(f"Processing timed out after {elapsed_minutes:.1f} minutes")
            
    except FileNotFoundError:
        logger.error(f"Error: PDF file '{pdf_path}' not found.")
        return None
    except requests.exceptions.Timeout:
        logger.error(f"Error: API request to '{process_endpoint}' timed out after 10 minutes.")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error: Failed to fetch data from API at '{process_endpoint}': {e}")
        return None
    except ValueError as e:
        logger.error(f"Error: {str(e)}")
        return None
    except TimeoutError as e:
        logger.error(f"Error: {str(e)}")
        return None

def compare_json(base, input_data, path="", matched=None, unmatched=None):
    if matched is None:
        matched = []
    if unmatched is None:
        unmatched = []
    
    if base is None and input_data is None:
        matched.append(f"{path}: Both null")
        return matched, unmatched
    
    if base is None:
        unmatched.append(f"{path}: base=null, input={input_data}")
        return matched, unmatched
    
    if input_data is None:
        unmatched.append(f"{path}: base={base}, input=null")
        return matched, unmatched
    
    if isinstance(base, dict) and isinstance(input_data, dict):
        for key in base:
            new_path = f"{path}.{key}" if path else key
            if key in input_data:
                compare_json(base[key], input_data[key], new_path, matched, unmatched)
            else:
                unmatched.append(f"{new_path}: Missing in input")
        for key in input_data:
            if key not in base:
                unmatched.append(f"{path}.{key}: Missing in base")
    elif isinstance(base, list) and isinstance(input_data, list):
        if len(base) != len(input_data):
            unmatched.append(f"List length mismatch at {path} (base: {len(base)}, input: {len(input_data)})")
        for i in range(min(len(base), len(input_data))):
            compare_json(base[i], input_data[i], f"{path}[{i}]", matched, unmatched)
    else:
        if base == input_data:
            matched.append(f"{path}: {base}")
        else:
            unmatched.append(f"{path}: base={base}, input={input_data}")
    
    return matched, unmatched

def write_results_to_file(matched_fields, unmatched_fields, filename):
    """Write comparison results to a separate file."""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("=== Matched Fields ===\n")
        for field in matched_fields:
            f.write(f"{field}\n")
        f.write("\n=== Unmatched Fields ===\n")
        for field in unmatched_fields:
            f.write(f"{field}\n")
        total = len(matched_fields) + len(unmatched_fields)
        f.write("\n=== Conclusion ===\n")
        f.write(f"Total fields compared: {total}\n")
        f.write(f"Matched fields: {len(matched_fields)} ({(len(matched_fields) / total * 100) if total > 0 else 0:.1f}%)\n")
        f.write(f"Unmatched fields: {len(unmatched_fields)} ({(len(unmatched_fields) / total * 100) if total > 0 else 0:.1f}%)\n")

def main():
    BASE_JSON_FILE = "base.json"
    PDF_FILE = "input.pdf"
    PROCESS_ENDPOINT = "http://ec2-3-75-220-58.eu-central-1.compute.amazonaws.com/ocr/process"
    STATUS_ENDPOINT = "http://ec2-3-75-220-58.eu-central-1.compute.amazonaws.com/ocr/ocr/status"
    API_HEADERS = {
        "Accept": "application/json"
    }

    USER_ID = generate_random_id(numeric_only=True)
    JOB_ID = generate_random_id()

    logger.info(f"\nStarting process at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Logging results to file: {log_filename}")
    logger.info(f"Comparison results will be saved to: {results_filename}")
    logger.info(f"Loading base JSON file '{BASE_JSON_FILE}'...")
    base = load_json_file(BASE_JSON_FILE)
    if base is None:
        logger.error("Process aborted due to error loading base JSON file.")
        return 1

    logger.info(f"Using User ID: {USER_ID}")
    logger.info(f"Using Job ID: {JOB_ID}")

    input_data = fetch_json_from_api(
        PDF_FILE, 
        PROCESS_ENDPOINT, 
        STATUS_ENDPOINT, 
        API_HEADERS,
        language="en",
        user_id=USER_ID,
        job_id=JOB_ID
    )
    if input_data is None:
        logger.error("Process aborted due to error fetching input JSON from API.")
        return 1

    logger.info(f"\nComparing '{BASE_JSON_FILE}' with API response...")
    matched_fields, unmatched_fields = compare_json(base, input_data)

    logger.info("=== Matched Fields ===")
    for field in matched_fields:
        logger.info(field)

    logger.info("\n=== Unmatched Fields ===")
    for field in unmatched_fields:
        logger.info(field)

    total_fields = len(matched_fields) + len(unmatched_fields)
    logger.info("\n=== Conclusion ===")
    logger.info(f"Total fields compared: {total_fields}")
    logger.info(f"Matched fields: {len(matched_fields)} ({(len(matched_fields) / total_fields * 100) if total_fields > 0 else 0:.1f}%)")
    logger.info(f"Unmatched fields: {len(unmatched_fields)} ({(len(unmatched_fields) / total_fields * 100) if total_fields > 0 else 0:.1f}%)")

    # Write comparison results to a separate file
    write_results_to_file(matched_fields, unmatched_fields, results_filename)
    logger.info(f"\nComparison results saved to {results_filename}")

    logger.info(f"\nProcess completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")
    return 0

if __name__ == "__main__":
    sys.exit(main())