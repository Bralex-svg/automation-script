import json
import requests
from datetime import datetime
import time

def load_json_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: File '{file_path}' contains invalid JSON.")
        return None
    except Exception as e:
        print(f"Error: An unexpected error occurred while reading '{file_path}': {e}")
        return None

def fetch_json_from_api(pdf_path, endpoint, headers=None):
    try:
        with open(pdf_path, 'rb') as pdf_file:
            files = {'file': (pdf_path, pdf_file, 'application/pdf')}
            print(f"Sending PDF '{pdf_path}' to API at '{endpoint}'... (This may take 5-10 minutes)")
            start_time = time.time()

            response = requests.post(endpoint, headers=headers, files=files, timeout=600)
            response.raise_for_status() 

            elapsed_time = time.time() - start_time
            print(f"API response received after {elapsed_time:.1f} seconds.")

            return response.json()  
    except FileNotFoundError:
        print(f"Error: PDF file '{pdf_path}' not found.")
        return None
    except requests.exceptions.Timeout:
        print(f"Error: API request to '{endpoint}' timed out after 10 minutes.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error: Failed to fetch data from API at '{endpoint}': {e}")
        return None
    except ValueError:
        print(f"Error: API response from '{endpoint}' is not valid JSON.")
        return None

def compare_json(base, input_data, path="", matched=[], unmatched=[]):
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

# Configuration
BASE_JSON_FILE = "base.json"  
PDF_FILE = "input.pdf"      
API_ENDPOINT = "endpointurl" 
API_HEADERS = {
    "Accept": "application/json"
}

print(f"\nStarting process at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

print(f"Loading base JSON file '{BASE_JSON_FILE}'...")
base = load_json_file(BASE_JSON_FILE)
if base is None:
    print("Process aborted due to error loading base JSON file.")
    exit(1)

input_data = fetch_json_from_api(PDF_FILE, API_ENDPOINT, API_HEADERS)
if input_data is None:
    print("Process aborted due to error fetching input JSON from API.")
    exit(1)

print(f"\nComparing '{BASE_JSON_FILE}' with API response...")
matched_fields = []
unmatched_fields = []
compare_json(base, input_data, "", matched_fields, unmatched_fields)

print("=== Matched Fields ===")
for field in matched_fields:
    print(field)

print("\n=== Unmatched Fields ===")
for field in unmatched_fields:
    print(field)

total_fields = len(matched_fields) + len(unmatched_fields)
print("\n=== Conclusion ===")
print(f"Total fields compared: {total_fields}")
print(f"Matched fields: {len(matched_fields)} ({(len(matched_fields) / total_fields * 100) if total_fields > 0 else 0:.1f}%)")
print(f"Unmatched fields: {len(unmatched_fields)} ({(len(unmatched_fields) / total_fields * 100) if total_fields > 0 else 0:.1f}%)")

print(f"\nProcess completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")