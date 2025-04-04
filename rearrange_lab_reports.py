import json

# Load the JSON data from the file
with open("base.json", "r") as file:
    data = json.load(file)

# Access the lab_reports data
lab_reports = data["lab_reports"]["data"]

# Rearrange the lab_reports based on the index of test_params
lab_reports_sorted = sorted(lab_reports, key=lambda x: x["test_params"]["index"])

# Update the lab_reports data with the sorted list
data["lab_reports"]["data"] = lab_reports_sorted

# Save the updated JSON data back to the file
with open("base_lower_case.json", "w") as file:
    json.dump(json.loads(json.dumps(data).lower()), file, indent=4)

print("Lab reports have been rearranged based on the index of test_params.")