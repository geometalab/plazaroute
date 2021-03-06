import os
import json


def get_json_file(file_name, subdirectory=''):
    """ loads a json file from the test resources directory based on the provided file name and subdirectory """
    if not file_name:
        assert False
    actual_path = os.path.dirname(__file__)
    response = os.path.join(actual_path, '../resources', subdirectory, file_name)
    with open(response) as response_data:
        json_data = json.load(response_data)
    return json_data


def get_file(file_name, subdirectory=''):
    """ loads a file as a string from the test resources directory based on the provided file name and subdirectory """
    if not file_name:
        assert False
    actual_path = os.path.dirname(__file__)
    response = os.path.join(actual_path, '../resources', subdirectory, file_name)
    with open(response) as response_data:
        text_data = response_data.read()
    return text_data
