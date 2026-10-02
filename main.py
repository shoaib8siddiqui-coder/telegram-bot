import os
import sqlite3
import telebot
import requests
from telebot import types


# =========================================================
# CONFIGURATION
# =========================================================

N8N_WEBHOOK_URL = "https://shez.app.n8n.cloud/webhook/8e84fc40-1c90-415e-9553-e300f9c0acf9"

Api_token = os.getenv("API_TOKEN")

if not Api_token:
    raise ValueError("API_TOKEN environment variable is not set")

bot = telebot.TeleBot(token=Api_token)


# =========================================================
# DATABASE
# =========================================================

os.makedirs("data", exist_ok=True)

DB_FILE = os.path.join(
    os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "data"),
    "user.db"
)


def tables():

    connection = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user(
            chat_id TEXT,
            memory_key TEXT,
            memory_value TEXT,
            PRIMARY KEY(memory_key, chat_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_state(
            chat_id TEXT PRIMARY KEY,
            current_state TEXT
        )
    """)

    connection.commit()
    connection.close()


tables()


# =========================================================
# STATE FUNCTIONS
# =========================================================

def get_user_state(chat_id):

    connection = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    cursor = connection.cursor()

    cursor.execute(
        "SELECT current_state FROM bot_state WHERE chat_id=?",
        (str(chat_id),)
    )

    row = cursor.fetchone()

    connection.close()

    if row and row[0]:
        return row[0]

    return "Menu"


def update_user_state(chat_id, step):

    connection = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO bot_state(chat_id, current_state)
        VALUES(?, ?)
        """,
        (str(chat_id), str(step))
    )

    connection.commit()
    connection.close()


# =========================================================
# MEMORY FUNCTIONS
# =========================================================

def recall_fact(chat_id, key):

    key = key.replace(" ", "_").strip().lower()

    connection = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT memory_value
        FROM user
        WHERE chat_id=? AND memory_key=?
        """,
        (str(chat_id), str(key))
    )

    row = cursor.fetchone()

    connection.close()

    if row and row[0]:
        return row[0]

    return None


def recall_all_fact(chat_id):

    connection = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT memory_key, memory_value
        FROM user
        WHERE chat_id=?
        """,
        (str(chat_id),)
    )

    rows = cursor.fetchall()

    connection.close()

    return rows


def remembered_fact(chat_id, key, value):

    key = key.replace(" ", "_").strip().lower()
    value = value.strip()

    connection = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO user(
            chat_id,
            memory_key,
            memory_value
        )
        VALUES(?, ?, ?)
        """,
        (str(chat_id), key, value)
    )

    connection.commit()
    connection.close()


def recall_profile(chat_id, key_list):

    connection = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    cursor = connection.cursor()

    profile = []

    for key in key_list:

        key = key.replace(" ", "_").lower().strip()

        cursor.execute(
            """
            SELECT memory_value
            FROM user
            WHERE chat_id=? AND memory_key=?
            """,
            (str(chat_id), str(key))
        )

        row = cursor.fetchone()

        if row and row[0]:
            profile.append(row[0])
        else:
            profile.append("not provided")

    connection.close()

    return profile


# =========================================================
# SEND MESSAGE TO N8N
# =========================================================

def send_to_n8n(chat_id, message):

    try:

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT memory_key, memory_value
            FROM user
            WHERE chat_id=?
            """,
            (str(chat_id),)
        )

        memories = cursor.fetchall()

        conn.close()

        memory_text = "\n".join(
            f"{key}: {value}"
            for key, value in memories
            if key != "temp_key"
        )

        payload = {
            "chat_id": str(chat_id),
            "message": message,
            "memory": memory_text
        }

        print("===================================")
        print("SENDING MESSAGE TO N8N")
        print("Chat ID:", chat_id)
        print("Message:", message)
        print("Memory:", memory_text)
        print("===================================")

        response = requests.post(
            N8N_WEBHOOK_URL,
            json=payload,
            timeout=15
        )

        print("N8N STATUS CODE:", response.status_code)
        print("N8N RESPONSE:", response.text)

        response.raise_for_status()

        print("Message successfully sent to n8n.")

        return response

    except requests.exceptions.Timeout:

        print("ERROR: n8n request timed out.")

    except requests.exceptions.HTTPError as e:

        print("ERROR: n8n returned an HTTP error:", e)

    except requests.exceptions.RequestException as e:

        print("ERROR: Could not connect to n8n:", e)

    except Exception as e:

        print("ERROR in send_to_n8n:", e)

    return None


# =========================================================
# START COMMAND
# =========================================================

@bot.message_handler(commands=["start"])
def start(message):

    chat_id = message.chat.id

    saved_name = recall_fact(
        chat_id,
        "name"
    )

    if saved_name:

        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=False
        )

        markup.add(
            "View Profile",
            "Add More Info",
            "Fetch Data",
            "Fetch All Data"
        )

        bot.send_message(
            chat_id,
            f"Hello {saved_name}!, welcome back",
            reply_markup=markup
        )

        update_user_state(
            chat_id,
            "Menu"
        )

    else:

        bot.send_message(
            chat_id,
            "Hi there welcome to the bot\n"
            "before we proceed I want to know your name first for your profile",
            reply_markup=types.ReplyKeyboardRemove()
        )

        update_user_state(
            chat_id,
            "ASK_NAME"
        )


# =========================================================
# NORMAL CONVERSATION
# =========================================================

@bot.message_handler(
    func=lambda message: message.text and not message.text.startswith("/")
)
def conversational(message):

    chat_id = message.chat.id
    User_text = message.text
    current_state = get_user_state(chat_id)


    # =====================================================
    # ASK NAME
    # =====================================================

    if current_state == "ASK_NAME":

        remembered_fact(
            chat_id,
            "name",
            User_text
        )

        bot.send_message(
            chat_id,
            "What is your address?"
        )

        update_user_state(
            chat_id,
            "ASK_ADDRESS"
        )

        return


    # =====================================================
    # ASK ADDRESS
    # =====================================================

    elif current_state == "ASK_ADDRESS":

        remembered_fact(
            chat_id,
            "address",
            User_text
        )

        bot.send_message(
            chat_id,
            "What is your phone number?"
        )

        update_user_state(
            chat_id,
            "ASK_PHONE"
        )

        return


    # =====================================================
    # ASK PHONE
    # =====================================================

    elif current_state == "ASK_PHONE":

        remembered_fact(
            chat_id,
            "phone",
            User_text
        )

        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=False
        )

        markup.add(
            "View Profile",
            "Add More Info",
            "Fetch Data",
            "Fetch All Data"
        )

        bot.send_message(
            chat_id,
            "Your profile is ready\n"
            "Click on View Profile button to check your profile",
            reply_markup=markup
        )

        update_user_state(
            chat_id,
            "Menu"
        )

        return


    # =====================================================
    # MENU
    # =====================================================

    elif current_state == "Menu":


        # -------------------------------------------------
        # VIEW PROFILE
        # -------------------------------------------------

        if User_text == "View Profile":

            key_list = [
                "name",
                "address",
                "phone"
            ]

            profile1 = recall_profile(
                chat_id,
                key_list
            )

            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True,
                one_time_keyboard=False
            )

            markup.add(
                "View Profile",
                "Add More Info",
                "Fetch Data",
                "Fetch All Data"
            )

            if profile1:

                name, address, phone = profile1

                bot.send_message(
                    chat_id,
                    f"Your Profile\n"
                    f"Name: {name}\n"
                    f"Address: {address}\n"
                    f"Phone: {phone}",
                    reply_markup=markup
                )

                return

            else:

                bot.send_message(
                    chat_id,
                    "No profile",
                    reply_markup=markup
                )

                return


        # -------------------------------------------------
        # ADD MORE INFO
        # -------------------------------------------------

        elif User_text == "Add More Info":

            bot.send_message(
                chat_id,
                "What else would you like to save here as info?\n\n"
                "You can enter multiple keys separated by commas.\n"
                "For example:\n"
                "hobby, colour, country",
                reply_markup=types.ReplyKeyboardRemove()
            )

            update_user_state(
                chat_id,
                "CHOOSE_KEY"
            )

            return


        # -------------------------------------------------
        # FETCH DATA
        # -------------------------------------------------

        elif User_text == "Fetch Data":

            bot.send_message(
                chat_id,
                "What type of data do you want to recall?",
                reply_markup=types.ReplyKeyboardRemove()
            )

            update_user_state(
                chat_id,
                "ASK_TYPE"
            )

            return


        # -------------------------------------------------
        # FETCH ALL DATA
        # -------------------------------------------------

        elif User_text == "Fetch All Data":

            Data = recall_all_fact(chat_id)

            og_data = []

            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True,
                one_time_keyboard=False
            )

            markup.add(
                "View Profile",
                "Add More Info",
                "Fetch Data",
                "Fetch All Data"
            )

            for k, v in Data:

                if k != "temp_key":

                    og_data.append(
                        (k, v)
                    )

            if og_data:

                profile_text = ""

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

                bot.send_message(
                    chat_id,
                    "No saved data found.",
                    reply_markup=markup
                )

            return


        # -------------------------------------------------
        # NORMAL AI MESSAGE
        # -------------------------------------------------

        else:

            print(
                "User sent normal AI message:",
                User_text
            )

            send_to_n8n(
                chat_id,
                User_text
            )

            return


    # =====================================================
    # ASK TYPE
    # =====================================================

    elif current_state == "ASK_TYPE":

        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=False
        )

        markup.add(
            "View Profile",
            "Add More Info",
            "Fetch Data",
            "Fetch All Data"
        )

        data = recall_fact(
            chat_id,
            User_text
        )

        if data:

            bot.send_message(
                chat_id,
                f"{data}",
                reply_markup=markup
            )

            update_user_state(
                chat_id,
                "Menu"
            )

        else:

            bot.send_message(
                chat_id,
                "No value found",
                reply_markup=markup
            )

            update_user_state(
                chat_id,
                "Menu"
            )

        return


    # =====================================================
    # CHOOSE KEY
    # =====================================================

    elif current_state == "CHOOSE_KEY":

        # Example:
        #
        # name, colour, country
        #
        # becomes:
        #
        # ['name', 'colour', 'country']

        temp_key = [
            key.strip()
            for key in User_text.split(',')
        ]

        # Store the temporary keys
        # as one string in SQLite

        with sqlite3.connect(DB_FILE) as connection:

            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO user(
                    chat_id,
                    memory_key,
                    memory_value
                )
                VALUES(?, ?, ?)
                """,
                (
                    str(chat_id),
                    "temp_key",
                    ",".join(temp_key)
                )
            )

        keys = ""

        for key in temp_key:

            keys += f"{key}\n"

        bot.send_message(
            chat_id,
            f"Enter the values in the same order:\n\n{keys}",
            reply_markup=types.ReplyKeyboardRemove()
        )

        update_user_state(
            chat_id,
            "CHOOSE_VALUE"
        )

        return


    # =====================================================
    # CHOOSE VALUE
    # =====================================================

    elif current_state == "CHOOSE_VALUE":

        # Example:
        #
        # Shehzar, gray, India
        #
        # becomes:
        #
        # ['Shehzar', 'gray', 'India']

        values = [
            value.strip()
            for value in User_text.split(',')
        ]


        # -----------------------------------------------
        # Get temporary keys from database
        # -----------------------------------------------

        with sqlite3.connect(DB_FILE) as connection:

            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT memory_value
                FROM user
                WHERE chat_id=? AND memory_key=?
                """,
                (
                    str(chat_id),
                    "temp_key"
                )
            )

            result = cursor.fetchone()


        # -----------------------------------------------
        # Check if temporary keys exist
        # -----------------------------------------------

        if result is None:

            bot.send_message(
                chat_id,
                "Something went wrong. "
                "Please try Add More Info again."
            )

            update_user_state(
                chat_id,
                "Menu"
            )

            return


        # -----------------------------------------------
        # Convert stored string back into a list
        # -----------------------------------------------

        temp_key = [
            key.strip()
            for key in result[0].split(',')
        ]


        # -----------------------------------------------
        # Check number of keys and values
        # -----------------------------------------------

        if len(temp_key) != len(values):

            bot.send_message(
                chat_id,
                f"You entered {len(temp_key)} keys "
                f"but {len(values)} values.\n\n"
                "Please enter the same number of "
                "values separated by commas."
            )

            return


        # -----------------------------------------------
        # Save key-value pairs
        # -----------------------------------------------

        with sqlite3.connect(DB_FILE) as connection:

            cursor = connection.cursor()

            for key, value in zip(temp_key, values):

                remembered_fact(
                    chat_id,
                    key,
                    value
                )


            # Delete temporary keys

            cursor.execute(
                """
                DELETE FROM user
                WHERE chat_id=? AND memory_key=?
                """,
                (
                    str(chat_id),
                    "temp_key"
                )
            )


        # -----------------------------------------------
        # Create normal menu
        # -----------------------------------------------

        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=False
        )

        markup.add(
            "View Profile",
            "Add More Info",
            "Fetch Data",
            "Fetch All Data"
        )


        bot.send_message(
            chat_id,
            "Saved ✅",
            reply_markup=markup
        )

        update_user_state(
            chat_id,
            "Menu"
        )

        return


# =========================================================
# START BOT
# =========================================================

print("Starting Telegram bot...")

try:

    bot.infinity_polling(
        skip_pending=True
    )

except Exception as e:

    print(f"BOT ERROR: {e}")

    raise
