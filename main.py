import os
import sqlite3
import telebot
import requests
from telebot import types
N8N_WEBHOOK_URL = "https://shehzar.app.n8n.cloud/webhook/914209ca-ad18-4de0-a42d-9587d76d85c6"


Api_token = os.getenv('API_TOKEN')

if not Api_token:
    raise ValueError('API_TOKEN environment variable is not set')

bot = telebot.TeleBot(token=Api_token)

os.makedirs("data", exist_ok=True)

DB_FILE = os.path.join(
    os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "data"),
    "user.db"
)


def tables():
    connection = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = connection.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS user(
        chat_id TEXT,
        memory_key TEXT,
        memory_value TEXT,
        PRIMARY KEY(memory_key, chat_id)
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS bot_state(
        chat_id TEXT PRIMARY KEY,
        current_state TEXT
    )''')

    connection.commit()
    connection.close()


tables()


def get_user_state(chat_id):
    connection = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = connection.cursor()

    cursor.execute(
        'SELECT current_state FROM bot_state WHERE chat_id=?',
        (str(chat_id),)
    )

    row = cursor.fetchone()
    connection.close()

    if row and row[0]:
        return row[0]

    return "Menu"


def update_user_state(chat_id, step):
    connection = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = connection.cursor()

    cursor.execute(
        'INSERT OR REPLACE INTO bot_state(chat_id, current_state) VALUES(?,?)',
        (str(chat_id), str(step))
    )

    connection.commit()
    connection.close()


def recall_fact(chat_id, key):
    key = key.replace(' ', '_').strip().lower()

    connection = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = connection.cursor()

    cursor.execute(
        'SELECT memory_value FROM user WHERE chat_id=? AND memory_key=?',
        (str(chat_id), str(key))
    )

    row = cursor.fetchone()
    connection.close()

    if row and row[0]:
        return row[0]

    return None


def recall_all_fact(chat_id):
    connection = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = connection.cursor()

    cursor.execute(
        'SELECT memory_key, memory_value FROM user WHERE chat_id=?',
        (str(chat_id),)
    )

    rows = cursor.fetchall()
    connection.close()

    return rows


def remembered_fact(chat_id, key, value):
    key = key.replace(' ', '_').strip().lower()
    value = value.strip()

    connection = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = connection.cursor()

    cursor.execute(
        'INSERT OR REPLACE INTO user(chat_id, memory_key, memory_value) VALUES(?,?,?)',
        (str(chat_id), key, value)
    )

    connection.commit()
    connection.close()


def recall_profile(chat_id, key_list):
    connection = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = connection.cursor()

    profile = []

    for key in key_list:
        key = key.replace(' ', '_').lower().strip()

        cursor.execute(
            '''SELECT memory_value
               FROM user
               WHERE chat_id=? AND memory_key=?''',
            (str(chat_id), str(key))
        )

        row = cursor.fetchone()

        if row and row[0]:
            profile.append(row[0])
        else:
            profile.append('not provided')

    connection.close()

    return profile
def send_to_n8n(chat_id, message):
    try:
        # Get all saved memories for this user
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT memory_key, memory_value FROM user WHERE chat_id=?",
            (str(chat_id),)
        )

        rows = cursor.fetchall()
        conn.close()

        # Convert memories into simple text
        memory_text = "\n".join(
            f"{key}: {value}" for key, value in rows
        )

        response = requests.post(
            N8N_WEBHOOK_URL,
            json={
                "chat_id": chat_id,
                "message": message,
                "memory": memory_text
            },
            timeout=15
        )

        response.raise_for_status()

        return response.json()

    except Exception as e:
        print("n8n error:", e)
        return None

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id

    saved_name = recall_fact(chat_id, 'name')

    if saved_name:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=False
        )

        markup.add(
            'View Profile',
            'Add More Info',
            'Fetch Data',
            'Fetch All Data'
        )

        bot.send_message(
            chat_id,
            f'Hello {saved_name}!,welcome back',
            reply_markup=markup
        )

        update_user_state(chat_id, 'Menu')

    else:
        bot.send_message(
            chat_id,
            'Hi there welcome to the bot\n'
            'before we proceed I want to know your name first for your profile',
            reply_markup=types.ReplyKeyboardRemove()
        )

        update_user_state(chat_id, 'ASK_NAME')


@bot.message_handler(func=lambda message: not message.text.startswith('/'))
def conversational(message):

    chat_id = message.chat.id
    User_text = message.text
    current_state = get_user_state(chat_id)

    if current_state == 'ASK_NAME':

        remembered_fact(chat_id, 'name', User_text)

        bot.send_message(
            chat_id,
            'What is your address ?'
        )

        update_user_state(chat_id, 'ASK_ADDRESS')

        return

    elif current_state == 'ASK_ADDRESS':

        remembered_fact(chat_id, 'Address', User_text)

        bot.send_message(
            chat_id,
            'What is your phone number ?'
        )

        update_user_state(chat_id, 'ASK_PHONE')

        return

    elif current_state == 'ASK_PHONE':

        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=False
        )

        markup.add(
            'View Profile',
            'Add More Info',
            'Fetch Data',
            'Fetch All Data'
        )

        remembered_fact(chat_id, 'Phone', User_text)

        bot.send_message(
            chat_id,
            'Your profile is ready\n'
            'Click on View Profile button to check your profile',
            reply_markup=markup
        )

        update_user_state(chat_id, 'Menu')

        return

    elif current_state == 'Menu':

        if User_text == 'View Profile':

            key_list = ['name', 'address', 'phone']

            profile1 = recall_profile(chat_id, key_list)

            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True,
                one_time_keyboard=False
            )

            markup.add(
                'View Profile',
                'Add More Info',
                'Fetch Data',
                'Fetch All Data'
            )

            if profile1:

                name, address, phone = profile1

                bot.send_message(
                    chat_id,
                    f'Your Profile\n'
                    f'Name:{name}\n'
                    f'Address:{address}\n'
                    f'Phone:{phone}',
                    reply_markup=markup
                )

                return

            else:

                bot.send_message(
                    chat_id,
                    'No profile',
                    reply_markup=markup
                )

                return

        elif User_text == 'Add More Info':

            bot.send_message(
                chat_id,
                'What else would you like to save here as info '
                'for eg(hobby,)?',
                reply_markup=types.ReplyKeyboardRemove()
            )

            update_user_state(chat_id, 'CHOOSE_KEY')

            return

        elif User_text == 'Fetch Data':

            bot.send_message(
                chat_id,
                'What type of data do you want to recall?',
                reply_markup=types.ReplyKeyboardRemove()
            )

            update_user_state(chat_id, 'ASK_TYPE')

            return

        elif User_text == 'Fetch All Data':

            Data = recall_all_fact(chat_id)

            og_data = []

            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True,
                one_time_keyboard=False
            )

            markup.add(
                'View Profile',
                'Add More Info',
                'Fetch Data',
                'Fetch All Data'
            )

            for k, v in Data:

                if k != 'temp_key':
                    og_data.append((k, v))

            if og_data:

                profile_text = str()

                for key, val in og_data:

                    profile_text += (
                        f"\n• {key.replace('_', ' ').title()}: {val}"
                    )

                bot.send_message(
                    chat_id,
                    profile_text,
                    reply_markup=markup
                )

        else:
            result = send_to_n8n(chat_id, User_text)

            if result:
        # Save any new memories returned by n8n
                memories = result.get("memories", [])

                for memory in memories:
                    key = memory.get("key")
                    value = memory.get("value")

                    if key and value:
                        remembered_fact(chat_id, key, value)

        # Send AI response to Telegram
                ai_response = result.get("reply")

                if ai_response:
                    bot.send_message(chat_id, ai_response)

    elif current_state == 'ASK_TYPE':

        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=False
        )

        markup.add(
            'View Profile',
            'Add More Info',
            'Fetch Data',
            'Fetch All Data'
        )

        data = recall_fact(chat_id, User_text)

        if data:

            bot.send_message(
                chat_id,
                f'{data}',
                reply_markup=markup
            )

            update_user_state(chat_id, 'Menu')

        else:

            bot.send_message(
                chat_id,
                'No value found',
                reply_markup=markup
            )

            update_user_state(chat_id, 'Menu')

            return

    elif current_state == 'CHOOSE_KEY':

        remembered_fact(
            chat_id,
            'temp_key',
            User_text
        )

        bot.send_message(
            chat_id,
            f'what value {User_text} holds?',
            reply_markup=types.ReplyKeyboardRemove()
        )

        update_user_state(
            chat_id,
            'CHOOSE_VALUE'
        )

        return

    elif current_state == 'CHOOSE_VALUE':

        key = recall_fact(
            chat_id,
            'temp_key'
        )

        remembered_fact(
            chat_id,
            key,
            User_text
        )

        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=False
        )

        markup.add(
            'View Profile',
            'Add More Info',
            'Fetch Data',
            'Fetch All Data'
        )

        bot.send_message(
            chat_id,
            f'Your custom information under "{key}" has been saved!',
            reply_markup=markup
        )

        update_user_state(
            chat_id,
            'Menu'
        )

        return


print("Starting Telegram bot...")

try:
    bot.infinity_polling()

except Exception as e:

    print(f"BOT ERROR: {e}")

    raise

