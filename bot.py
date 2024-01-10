from telegram import Bot, ReplyKeyboardMarkup, Update, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
import requests
from dotenv import load_dotenv
import os
import logging
import openai
import sqlite3
import json, time

AUTHORIZED = "authorized"
ENTER_SECRET_WORD = "ENTER_SECRET_WORD"
SECRET_WORD = ['diashov', 'dias', '2shov', 'диашов', 'диаш']


# Функция для создания или подключения к базе данных
def connect_to_database():
    conn = sqlite3.connect('gpt_dalle_bot.db')  # Замените 'your_database.db' на имя вашей базы данных
    cursor = conn.cursor()
    # Создайте таблицу, если она еще не существует
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            chat_id INTEGER,
            user_id INTEGER,
            username TEXT,
            messages TEXT
        )
    ''')
    # cursor.execute('DELETE FROM chat_history')
    conn.execute("PRAGMA encoding = 'UTF-8'")
    cursor.execute("SELECT * FROM chat_history")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
    conn.commit()
    return conn, cursor


# Функция для сохранения сообщения в базе данных
def save_message(chat_id, user_id, username, message, role):
    conn, cursor = connect_to_database()
    # Получаем текущий список сообщений для данного чата и пользователя
    conn.execute("PRAGMA encoding = 'UTF-8'")
    cursor.execute("SELECT messages FROM chat_history WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    result = cursor.fetchone()
    if result[0]:
        messages = json.loads(result[0])
    else:
        conn.commit()
        messages = []

    # Создаем новое сообщение
    new_message = {"role": role, "content": message}
    messages.append(new_message)

    # Обновляем базу данных с новыми сообщениями
    cursor.execute("UPDATE chat_history SET messages = ? WHERE chat_id = ? AND user_id = ?",
                   (json.dumps(messages), chat_id, user_id))
    conn.commit()
    conn.close()


def delete_history(update, context):
    chat_id = update.effective_chat.id
    user_id = update.message.from_user.id
    conn, cursor = connect_to_database()
    cursor.execute("UPDATE chat_history SET messages = ? WHERE chat_id = ? AND user_id = ?",
                   (json.dumps([]), chat_id, user_id))
    text = 'Ой, кажется я всё забыл, не беда. Давайте начнём общение заново.'
    context.bot.send_message(chat_id=chat_id, text=text)
    conn.commit()
    conn.close()


# Функция для добавления ответа от ассистента к существующему сообщению
def add_assistant_response(chat_id, user_id, username, response):
    save_message(chat_id, user_id, username, response, "assistant")


URL = 'https://api.thecatapi.com/v1/images/search'
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)


def get_new_image():
    try:
        response = requests.get(URL)
    except Exception as error:
        logging.error(f'Ошибка при запросе к основному API: {error}')
        new_url = 'https://api.thedogapi.com/v1/images/search'
        response = requests.get(new_url)
    finally:
        response = response.json()
        random_cat = response[0].get('url')
        return random_cat


def generate_openai_dalle_response(prompt):
    try:
        response = openai.Image.create(
            prompt=f"{prompt}",
            n=1,
            size="1024x1024"
        )
        print(response)
        image_url = response['data'][0]['url']
        "1024x1024"
        return image_url
    except Exception as error:
        logging.error(f'Ошибка при запросе к API OpenAI: {error}')
        return 'Произошла ошибка при запросе к OpenAI DALL-E'


def pre(update, context):
    user = update.message.from_user
    context.user_data['waiting_for_input'] = True  # Устанавливаем флаг ожидания ввода
    reply_markup = ReplyKeyboardMarkup([[KeyboardButton('Отменить')]], one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text('Напишите текст для генерации изображения или нажмите "Отменить".',
                              reply_markup=reply_markup)


def generate_openai_chat_response(chat_id, user_id):
    try:
        conn, cursor = connect_to_database()
        # Запрос к API OpenAI для генерации ответа
        cursor.execute("SELECT messages FROM chat_history WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        result = cursor.fetchone()
        if result:
            messages = json.loads(result[0])
        else:
            messages = []
        # Создаем запрос к OpenAI, включая сохраненные сообщения
        response_first = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                         {"role": "system", "content": "You are a helpful assistant"}
                     ] + messages
        )
        print(messages)
        answer = response_first.choices[0].message.content.strip()
        conn.close()
        return answer
    except Exception as error:
        logging.error(f'Ошибка при запросе к API OpenAI: {error}')
        return 'Произошла ошибка при запросе к OpenAI'


def say_hi(update, context):
    chat = update.effective_chat
    chat_id = chat.id
    message_text = update.message.text
    username = None
    if update.message.from_user.username:
        username = update.message.from_user.username
    user_id = update.message.from_user.id
    print(message_text)
    text = message_text.lower()  # Получаем текст сообщения и переводим его в нижний регистр
    keyword = "представь"
    if 'waiting_for_input' in context.user_data:
        text = update.message.text
        if text.lower() == 'отменить':
            context.user_data.pop('waiting_for_input')  # Удаляем флаг ожидания ввода
            update.message.reply_text('Операция отменена.')
        else:
            context.user_data.pop('waiting_for_input')  # Удаляем флаг ожидания ввода
            generated_image = generate_openai_dalle_response(text)  # Вызываем функцию для генерации изображения
            update.message.reply_text('Ваше изображение готово:')
            update.message.reply_photo(photo=generated_image)  # Отправляем сгенерированное изображение
    # Генерируем ответ от OpenAI на основе текста пользователя
    else:
        save_message(chat_id, user_id, username, message_text, "user")
        openai_response = generate_openai_chat_response(chat_id, user_id)
        add_assistant_response(chat_id, user_id, username, openai_response)
        # Отправляем ответ OpenAI в чат
        context.bot.send_message(chat_id=chat.id, text=openai_response)


def new_cat(update, context):
    chat = update.effective_chat
    context.bot.send_photo(chat.id, get_new_image())


def help(update, context):
    chat_id = update.effective_chat.id
    name = update.message.chat.first_name
    # За счёт параметра resize_keyboard=True сделаем кнопки поменьше
    update.message.reply_text(
        'Возможности бота и как им пользоваться:\n\n\n'
        '1.	Чат с GPT-3.5: Пользователь может общаться с ботом, отправляя текстовые сообщения. '
        'Бот будет генерировать текстовые ответы на вопросы и комментарии пользователя.\n\n'
        '2.	Генерация изображений по текстовому описанию: Если пользователю необходимо сгенерировать изображение,'
        ' он должен воспользоваться командой /imagine. После отправки'
        ' этой команды, бот будет ожидать текстовое описание'
        ' изображения от пользователя и затем сгенерирует изображение'
        ' на основе этого описания. Пользователь может ввести '
        'описание и нажать "Отправить", или ввести "/cancel" для отмены операции.'
        ' Как только изображение будет сгенерировано, бот отправит его в чат.\n\n'
        '3.	Удаление истории: можете удалить память истории нашего общения '
        'и начать общение заново, отправив команду /clear_memory.\n\n'
        '4.	Авторизация: Для некоторых действий, таких как удаление истории, бот может потребовать авторизацию. '
        'Для авторизации пользователь должен ввести секретное слово.\n\n'
        '5.	Получение фото котиков: Пользователь может получить случайное фото котика в ответ на команду /new_cat.\n\n'
        '6.	Приветствие: При старте запрашивается аутентификация и отправляется случайное фото котика.'
        
        'Благодаря этим возможностям, бот предоставляет пользователю выбор между '
        'текстовым чатом с генерацией текстовых ответов или созданием изображений на основе текстовых описаний.')


def start(update, context):
    chat = update.effective_chat
    chat_id = chat.id
    user_id = update.message.from_user.id
    username = None
    if update.message.from_user.username:
        username = update.message.from_user.username
    name = update.message.chat.first_name

    # Проверяем, есть ли запись в базе данных для этого пользователя
    # Если нет, то создаем запись с state=False
    conn, cursor = connect_to_database()
    cursor.execute("SELECT state FROM chat_history WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    result = cursor.fetchone()
    if not result:
        cursor.execute("INSERT INTO chat_history (chat_id, user_id, username, messages, state) VALUES (?, ?, ?, ?, ?)",
                       (chat_id, user_id, username, '[]', False))
        conn.commit()
        conn.close()
        context.bot.send_message(
            chat_id=chat.id,
            text='Привет, {}.'.format(name),
        )
        update.message.reply_text(
            'Возможности бота и как им пользоваться:\n\n'
            '1.	Чат с GPT-3.5: Пользователь может общаться с ботом, отправляя текстовые сообщения. '
            'Бот будет генерировать текстовые ответы на вопросы и комментарии пользователя.\n\n'
            '2.	Генерация изображений по текстовому описанию: Если пользователю необходимо сгенерировать изображение,'
            ' он должен воспользоваться командой /imagine. После отправки'
            ' этой команды, бот будет ожидать текстовое описание'
            ' изображения от пользователя и затем сгенерирует изображение'
            ' на основе этого описания. Пользователь может ввести '
            'описание и нажать "Отправить", или ввести "/cancel" для отмены операции.'
            ' Как только изображение будет сгенерировано, бот отправит его в чат.\n\n'
            '3.	Удаление истории: можете удалить память истории нашего общения '
            'и начать общение заново, отправив команду /clear_memory.\n\n'
            '4.	Авторизация: Для некоторых действий, таких как удаление истории, бот может потребовать авторизацию. '
            'Для авторизации пользователь должен ввести секретное слово.\n\n'
            '5.	Получение фото котиков: Пользователь может получить случайное фото котика в ответ на команду /new_cat.\n\n'
            '6.	Приветствие: При старте чата бот приветствует пользователя и предлагает отправить случайное фото котика.'
            'Благодаря этим возможностям, бот предоставляет пользователю выбор между '
            'текстовым чатом с генерацией текстовых ответов или созданием изображений на основе текстовых описаний.')
        context.bot.send_message(chat_id, 'Посмотри, какого котика я тебе нашёл')
        context.bot.send_photo(chat_id, get_new_image())
        update.message.reply_text("Введите секретное слово для авторизации:")
    else:
        # Пользователь уже есть в базе, проверяем его state
        state = result[0]
        if state:
            # update.message.reply_text('Вы уже авторизованны')
            text = update.message.text
            context.user_data["state"] = AUTHORIZED
            if text == '/help':
                help(update, context)
            elif text == '/new_cat':
                new_cat(update, context)
            elif text == '/imagine':
                pre(update, context)
            elif text == '/clear_memory':
                delete_history(update, context)
            else:
                say_hi(update, context)
            return AUTHORIZED
        # Пользователь уже авторизован, выполните действие для авторизованных пользователей
        else:
            update.message.reply_text("Введите секретное слово для авторизации:")
            # Или можете установить флаг ожидания секретного слова в контексте:
            # context.user_data['waiting_for_secret_word'] = True
    return ENTER_SECRET_WORD


# Обработчик ввода секретного слова
def enter_secret_word(update, context):
    user_input = update.message.text.lower()
    if user_input in SECRET_WORD:
        chat_id = update.effective_chat.id
        user_id = update.message.from_user.id
        conn, cursor = connect_to_database()
        cursor.execute("SELECT state FROM chat_history WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        result = cursor.fetchone()
        cursor.execute("UPDATE chat_history SET state = ? WHERE chat_id = ? AND user_id = ?",
                       (True, chat_id, user_id))
        conn.commit()
        conn.close()
        update.message.reply_text("Вы успешно авторизованы!")
        return AUTHORIZED
    else:
        update.message.reply_text("Неверное секретное слово. Попробуйте ещё раз:")
        return ENTER_SECRET_WORD


def main():
    # Здесь укажите токен,
    # который вы получили от @Botfather при создании бот-аккаунта.
    # Укажите id своего аккаунта в Telegram

    text = 'Вам телеграмма!'
    # Отправка сообщения
    load_dotenv()
    bot_token = os.getenv('TOKEN_GPT_DALLE_bot')
    bot = Bot(token=bot_token)
    chat_id = os.getenv('CHAT_ID')
    openai.api_key = os.getenv("OPENAI_API_KEY")
    bot.send_message(388050565, text)
    updater = Updater(token=bot_token)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start),
                      MessageHandler(Filters.text & ~Filters.command, start)],
        states={
            ENTER_SECRET_WORD: [MessageHandler(Filters.text & ~Filters.command, enter_secret_word)],
            AUTHORIZED: [
                CommandHandler('start', start),
                CommandHandler('help', help),
                CommandHandler('new_cat', new_cat),
                CommandHandler('imagine', pre),
                CommandHandler('clear_memory', delete_history),
                # Регистрируется обработчик MessageHandler;
                # из всех полученных сообщений он будет выбирать только текстовые сообщения
                # и передавать их в функцию say_hi()
                MessageHandler(Filters.text, say_hi)
            ]
        },
        fallbacks=[]
    )
    updater.dispatcher.add_handler(conv_handler)
    # Метод start_polling() запускает процесс polling,
    # приложение начнёт отправлять регулярные запросы для получения обновлений.
    updater.start_polling()
    # Бот будет работать до тех пор, пока не нажмете Ctrl-C
    updater.idle()


if __name__ == '__main__':
    while True:
        try:
            main()  # Здесь вызывайте вашу функцию или скрипт
        except Exception as e:
            print(f"An error occurred: {e}")
            print("Restarting the script in 10 seconds...")
            time.sleep(10)  # Подождите 10 секунд перед перезапуском
# + тест dalle

# + тест gpt

# ограничение запросов у не оплаченных пользователей

# запрос на оплату кнопкой /подписка.
# человеку будет даваться информация по условиям подписки. по кнопке /основать подписку
# будут выданы реквизиты для оплаты, далее он нажимает - /я оплатил,
# выдаётся сообщение об ожидании подтверждения или успешной активации

# настроить детектор оплат, наверное надо запрашивать данные переводящего деньги.
# не совсем понятно как работать со сбером, да и с биржами

# соответственно расширить дата базу

# пока что сделать пароль для доступа и записать его True в таблицу базы данных

# поставить на удалёнку
#
#
#
#
#
#
#
#
#
#
#
#
#
