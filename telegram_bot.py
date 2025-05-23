import os
import time
import json
import re
import logging
import traceback
from datetime import datetime
from typing import Dict, List

from dotenv import load_dotenv
from telegram import Bot
from telegram.error import RetryAfter, NetworkError

from google_sheets_handler import get_grouped_data

load_dotenv()

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_IDS_FILE = os.getenv('TELEGRAM_IDS_FILE')
MAX_RETRIES = 5
RETRY_DELAY_SECONDS = 5

bot = Bot(token=TOKEN)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def load_telegram_ids(file_path: str = TELEGRAM_IDS_FILE) -> Dict[str, int]:
    """
    Loads handler name to Telegram ID mapping from JSON file.
    """
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load telegram IDs from {file_path}: {e}")
        return {}


def escape_markdown(text: str) -> str:
    """
    Escapes Telegram MarkdownV2 special characters.
    """
    if not text:
        return ''
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


def generate_messages(grouped_data: Dict[str, List[Dict]]) -> Dict[str, List[str]]:
    """
    Creates one message per handler with bullet points.
    Bold assignment, customerName, dueDate and 'not checked'/'not handed over' if applicable.
    """
    messages = {}
    today = datetime.now().date()
    today_str = today.strftime('%Y-%m-%d')

    for handler, assignments in grouped_data.items():
        heading = f"📋 *Your Assignments as of {escape_markdown(today_str)}:*"
        lines = [heading]

        for assignment in assignments:
            assignment_name = escape_markdown(str(assignment.get('assignment', 'No Assignment')))
            customer_name = escape_markdown(str(assignment.get('customerName', 'Unknown Customer')))
            due_date = assignment.get('dueDate')

            if due_date:
                days_remaining = (due_date - today).days
                if days_remaining < 0:
                    due_str = "Past due!"
                elif days_remaining == 0:
                    due_str = "Due today"
                elif days_remaining == 1:
                    due_str = "Due in 1 day"
                else:
                    due_str = f"Due in {days_remaining} days"
            else:
                due_str = "No due date"

            due_str = escape_markdown(due_str)

            checked = assignment.get('checked', False)
            handover = assignment.get('handOver', False)

            checked_str = "checked" if checked else "not checked"
            handover_str = "handed over" if handover else "not handed over"

            line = (
                f"• *Assignment:* {assignment_name}\n"
                f"  *Customer:* {customer_name}\n"
                f"  *Status:* {checked_str} and {handover_str}\n"
                f"  *{due_str}*"
            )

            lines.append(line)

        full_message = '\n\n'.join(lines)
        messages[handler] = [full_message]

    return messages


def send_messages(telegram_ids: Dict[str, int], messages: Dict[str, List[str]]):
    """
    Sends messages to telegram users based on handler -> telegram_id mapping.
    """
    for handler, msgs in messages.items():
        telegram_id = telegram_ids.get(handler)
        if not telegram_id:
            logging.warning(f"No Telegram ID found for handler '{handler}', skipping.")
            continue

        for msg in msgs:
            if not msg.strip():
                logging.warning(f"Empty message for handler {handler}, skipping.")
                continue

            sent = False
            attempts = 0
            while not sent and attempts < MAX_RETRIES:
                try:
                    bot.send_message(chat_id=telegram_id, text=msg, parse_mode='MarkdownV2')
                    logging.info(f"Sent message to {handler} ({telegram_id})")
                    sent = True
                except RetryAfter as e:
                    logging.warning(f"Rate limited. Sleeping {e.retry_after}s")
                    time.sleep(e.retry_after)
                except NetworkError as e:
                    logging.warning(f"Network error: {e}. Retrying in {RETRY_DELAY_SECONDS}s...")
                    time.sleep(RETRY_DELAY_SECONDS)
                except Exception as e:
                    logging.error(f"Failed to send message to {handler}: {e}\n{traceback.format_exc()}")
                    break
                attempts += 1


def main():
    telegram_ids = load_telegram_ids()
    if not telegram_ids:
        logging.error("No Telegram IDs loaded, exiting.")
        return

    grouped_data = get_grouped_data()
    messages = generate_messages(grouped_data)
    send_messages(telegram_ids, messages)


if __name__ == '__main__':
    main()
