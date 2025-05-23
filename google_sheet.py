import os
import re
import logging
from datetime import datetime
from typing import List, Dict

from dotenv import load_dotenv
from dateutil.parser import parse
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

SERVICE_ACCOUNT_FILE = os.getenv('SERVICE_ACCOUNT_FILE')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SHEET_NAME = f"{datetime.now().strftime('%B').upper()} - {datetime.now().strftime('%Y')}"
RANGES = [
    f"{SHEET_NAME}!A:A",
    f"{SHEET_NAME}!B:B",
    f"{SHEET_NAME}!F:F",
    f"{SHEET_NAME}!G:G",
    f"{SHEET_NAME}!I:I",
    f"{SHEET_NAME}!L:L"
]

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def camel_case(text: str) -> str:
    text = re.sub(r'(_|-)+', ' ', text).strip().lower()
    words = text.split(' ')
    return words[0] + ''.join(word.title() for word in words[1:])


def fetch_data() -> List[Dict[str, str]]:
    """
    Fetch specified column ranges from Google Sheets
    and return list of dictionaries with camelCase keys.
    """
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)

    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()

    all_data = {}
    for range_name in RANGES:
        try:
            result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
                                        range=range_name).execute()
            values = result.get('values', [])
            all_data[range_name] = values
        except Exception as e:
            logging.error(f"Failed to fetch range {range_name}: {e}")
            all_data[range_name] = []

    headers = []
    for r in RANGES:
        header = all_data[r][0][0] if all_data[r] and len(all_data[r]) > 0 and len(all_data[r][0]) > 0 else ''
        headers.append(camel_case(header))

    data_list = []
    num_rows = len(all_data[RANGES[0]]) - 1 if all_data[RANGES[0]] else 0
    for i in range(1, num_rows + 1):
        row = {}
        for idx, r in enumerate(RANGES):
            values = all_data[r]
            if i < len(values) and len(values[i]) > 0:
                row[headers[idx]] = values[i][0]
            else:
                row[headers[idx]] = ''
        data_list.append(row)

    return data_list


def filter_not_yet(data_list: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Filters rows where checked or handOver is 'not yet' (case-insensitive)
    and dueDate is today or in the future.
    """
    filtered = []
    today = datetime.now().date()

    for row in data_list:
        checked_val = row.get('checked', '').strip().lower()
        handover_val = row.get('handOver', '').strip().lower()
        due_date_str = row.get('dueDate', '').strip()

        due_date_valid = False
        if due_date_str:
            try:
                due_date = parse(due_date_str).date()
                due_date_valid = due_date >= today
            except Exception:
                due_date_valid = False

        if (checked_val == 'not yet' or handover_val == 'not yet') and due_date_valid:
            filtered.append(row)

    return filtered


def group_by_handle_by(data_list: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    """
    Groups data by the 'handleBy' field (lowercased),
    removing 'handleBy' from each row dictionary.
    """
    grouped = {}
    for row in data_list:
        key = row.get('handleBy', '').strip().lower()
        if not key:
            continue

        row_copy = {k: v for k, v in row.items() if k != 'handleBy'}
        grouped.setdefault(key, []).append(row_copy)

    return grouped


def print_grouped_data(grouped_data: Dict[str, List[Dict[str, str]]]) -> None:
    """
    Nicely prints grouped data showing handler and assignments.
    Uses the 'assignment' field as the title and excludes it from details.
    """
    for handler, rows in grouped_data.items():
        logging.info(f"Handler: {handler}")
        for row in rows:
            assignment_name = row.get('assignment', 'No Assignment')
            logging.info(f"  Assignment: {assignment_name}")
            for key, value in row.items():
                if key != 'assignment':
                    logging.info(f"    {key}: {value}")
        print()


def main():
    data_list = fetch_data()
    filtered_data_list = filter_not_yet(data_list)
    grouped_data_list = group_by_handle_by(filtered_data_list)
    print_grouped_data(grouped_data_list)


if __name__ == '__main__':
    main()
