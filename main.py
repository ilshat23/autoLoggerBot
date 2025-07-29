import logging
import datetime as dt
import time
from enum import Enum

import telebot as tb  # type: ignore
from telebot.types import (InlineKeyboardMarkup,  # type: ignore
                           InlineKeyboardButton)

from envparse import env  # type: ignore

from sqlite_client import SQLiteClient
from telegram_client import TelegramClient
import queries as qs


logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler()
FORMATTER = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(FORMATTER)
logger.addHandler(console_handler)

env.read_envfile('.env')
TOKEN = env('TOKEN')
ADMIN_CHAT_ID = env('ADMIN_CHAT_ID')
BASE_URL = 'https://api.telegram.org'

if not isinstance(TOKEN, str):
    raise ValueError('TOKEN must be string')


class UserState(Enum):
    WAITING_FOR_CAR = 1
    WAITING_FOR_REPAIR_INFO = 2
    WAITING_FOR_DELETE = 3
    WAITING_FOR_RENAME = 4


class MyBot(tb.TeleBot):
    def __init__(self, sqlite_client: SQLiteClient,
                 telegram_client: TelegramClient, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.telegram_client = telegram_client
        self.sqlite_client = sqlite_client

    def setup_resourses(self):
        self.sqlite_client.create_connection()

    def shutdown(self):
        self.sqlite_client.close_connection()


telegram_client = TelegramClient(TOKEN, BASE_URL)
sqlite_client = SQLiteClient('users.db')
bot = MyBot(sqlite_client, telegram_client, token=TOKEN)

user_states = {}
temp_storage = {}


@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    user_exists = True

    user = bot.sqlite_client.execute_select_command(qs.GET_USER, (user_id,))

    if not user:
        bot.sqlite_client.execute_command(qs.CREATE_USER, (user_id, username))
        user_exists = False

    bot.reply_to(message, text=f"Вы {'уже' if user_exists else ''}"
                 f" зарегистрированы, {username}.")

    if not user_exists:
        user_states[user_id] = UserState.WAITING_FOR_CAR
        bot.send_message(message.chat.id, text='По какому автомобилю хотите'
                                               ' завести сервисную книгу📕? '
                                               'В дальнейшем можно будет доба'
                                               'вить еще автомобили. Для '
                                               'навигации используйте '
                                               'раздел "<b>Меню</b>"')


@bot.message_handler(commands=['delete_my_car'])
def delete_my_car_handler(message):
    name, telegram_id, cars = get_name_id_cars(message)
    temp_storage['user_id'] = telegram_id

    if not cars:
        bot.reply_to(message, f'{name}, удалять нечего.')
    else:
        text = ('Какой автомобиль нужно удалить❌? Обрати внимание, вместе с'
                ' автомобилем сотрется его история обслуживания!')
        create_markup_menu(cars, text, telegram_id, 'delete_my_car')


@bot.callback_query_handler(func=lambda call:
                            call.data.startswith('delete_my_car_'))
def delete_callback(call):
    user_id = temp_storage.get('user_id')
    temp_storage.pop('user_id')
    car_name = call.data[len('delete_my_car_'):]

    if user_id is None:
        raise TypeError('invalid user_id')

    delete_car(car_name, user_id)
    bot.answer_callback_query(call.id, 'Готово.')
    bot.send_message(user_id, f'✅Автомобиль <i>{car_name}</i> был удален '
                     'со всеми записями.', parse_mode='Html')


@bot.message_handler(commands=['add_new_car'])
def add_new_car_handler(message):
    bot.reply_to(message, '✍️Отлично, введи название для нового автомобиля.')
    user_states[message.from_user.id] = UserState.WAITING_FOR_CAR


def rename_car(new_car_name: str, user_id: int, old_car_name):
    bot.sqlite_client.execute_command(qs.UPDATE_CAR_NAME,
                                      (new_car_name, user_id, old_car_name))


@bot.message_handler(commands=['rename_my_car'])
def rename_car_handler(message):
    name, telegram_id, cars = get_name_id_cars(message)
    if not cars:
        bot.reply_to(message, f'{name}, у тебя нет автомобилей в коллекции.')
    elif len(cars) == 1:
        user_states[telegram_id] = UserState.WAITING_FOR_RENAME
        temp_storage['car'] = cars[0][0]
    else:
        create_markup_menu(cars,
                           'Какой автомобиль нужно переименовать?',
                           telegram_id,
                           'rename_my_car')


@bot.callback_query_handler(func=lambda call:
                            call.data.startswith('rename_my_car_'))
def handle_rename_callback(call):
    car_name = call.data[len('rename_my_car_'):]
    user_id = call.from_user.id
    user_states[user_id] = UserState.WAITING_FOR_RENAME
    temp_storage['car'] = car_name
    bot.answer_callback_query(call.id,
                              f'✍️Введи новое название для {car_name}.')


@bot.message_handler(func=lambda m:
                     user_states.get(m.from_user.id) == (
                         UserState.WAITING_FOR_RENAME))
def rename_my_car_handler(message):
    new_car_name = message.text.strip()
    user_id = message.from_user.id
    old_car_name = temp_storage.get('car')
    rename_car(new_car_name, message.from_user.id, old_car_name)
    bot.send_message(user_id,
                     f'✅Название <b>{new_car_name}</b> успешно сохранено.',
                     parse_mode='Html')
    user_states.pop(user_id)


@bot.message_handler(func=lambda m:
                     user_states.get(m.from_user.id) == (
                         UserState.WAITING_FOR_CAR))
def handle_car_name(message):
    user_id = message.from_user.id
    car_name = message.text.strip()

    bot.sqlite_client.execute_command(qs.ADD_NEW_CAR, (user_id, car_name))
    user_states.pop(user_id)
    bot.reply_to(message,
                 f'✅Автомобиль <b>{car_name}</b> успешно сохранен.',
                 parse_mode='Html')


def delete_car(car_name: str, telegram_id: int):
    bot.sqlite_client.execute_command(qs.DELETE_CAR,
                                      (telegram_id, car_name))


@bot.message_handler(commands=['show_my_car'])
def show_user_car(message):
    name, user_id, cars = get_name_id_cars(message)
    many_cars = True if len(cars) > 1 else False

    if not cars:
        bot.send_message(user_id, (f'{name}, странно, но у тебя нет ни '
                                   'одной машины.'))
    else:
        if many_cars:
            user_cars = ", ".join([car[0] for car in cars])
            bot.send_message(user_id,
                             f'{name}, твои машины:\n\n<i>{user_cars}</i>.',
                             parse_mode='Html')
        else:
            bot.send_message(user_id,
                             f'{name}, твоя машина: <i>{cars[0][0]}</i>.',
                             parse_mode='Html')


@bot.message_handler(func=lambda message:
                     user_states.get(message.from_user.id) == (
                         UserState.WAITING_FOR_REPAIR_INFO))
def handle_one_car_desc(message):
    try:
        mileage, description = message.text.strip().split('-')
        user_id = temp_storage['user_id']
        car_name = temp_storage['car']
    except ValueError:
        bot.reply_to(message, '⚠️Некорректный формат сообщения!⚠️\n'
                              'Введи сообщение '
                              'следующего формата:\n"<b>Текущий пробег-Информ'
                              'ация касательно ремонта</b>"',
                              parse_mode='Html')
    else:
        user_states.pop(user_id)
        temp_storage.pop('car')
        temp_storage.pop('user_id')
        add_repair_description(user_id,
                               car_name,
                               dt.date.today(),
                               description,
                               mileage)
        bot.reply_to(message, '✅Запись успешно сохранена.')


@bot.message_handler(commands=['add_service_notation'])
def add_service_notation(message):
    name, user_id, cars = get_name_id_cars(message)
    temp_storage['user_id'] = user_id
    if not cars:
        bot.reply_to(message, f'{name}, у тебя нет автомобилей в коллекции.')
        return
    else:
        if len(cars) < 2:
            user_states[user_id] = UserState.WAITING_FOR_REPAIR_INFO
            temp_storage['car'] = cars[0][0]
            bot.send_message(user_id, (f'Внеси запись для <b>{cars[0][0]}</b>.'
                                       'Введи сообщение следующего формата:\n'
                                       '"Текущий пробег-Выполненные работы"'),
                             parse_mode='Html')
        else:
            text = 'В историю какого автомобиля нужно добавить запись?'
            create_markup_menu(cars, text, user_id, 'add_service_notation')


@bot.callback_query_handler(func=lambda call:
                            call.data.startswith('add_service_notation_'))
def handle_add_service_notation(call):
    car_name = call.data[len('add_service_notation_'):]
    user_id = temp_storage['user_id']
    user_states[user_id] = UserState.WAITING_FOR_REPAIR_INFO
    temp_storage['car'] = car_name

    bot.answer_callback_query(call.id, 'Следуй инструкции в сообщении.')
    bot.send_message(user_id,
                     f'Отлично, ты выбрал <i>{car_name}</i>. Теперь введи'
                     ' пробег и описание ремонта в формате:\n'
                     '"<b>Пробег-Описание проделанных работ</b>"',
                     parse_mode='Html')


def get_user_cars(telegram_id: int) -> list:
    return bot.sqlite_client.execute_select_command(qs.GET_USER_CARS,
                                                    (telegram_id,))


def get_name_id_cars(message) -> tuple[str, int, list]:
    name = message.from_user.first_name
    telegram_id = message.from_user.id
    cars = get_user_cars(telegram_id)

    return name, telegram_id, cars


def add_repair_description(telegram_id: int,
                           car_name: str,
                           repair_date: dt.date,
                           description: str,
                           mileage: str):
    bot.sqlite_client.execute_command(qs.INSERT_REPAIR_DATA, (telegram_id,
                                                              car_name,
                                                              repair_date,
                                                              description,
                                                              mileage))


def create_markup_menu(cars: list, text: str, user_id: int, cmd: str):
    markup = InlineKeyboardMarkup()

    for car in cars:
        markup.add(InlineKeyboardButton(text=car[0],
                                        callback_data=(
                                            f'{cmd}_{car[0]}')))

    bot.send_message(chat_id=user_id,
                     text=text,
                     reply_markup=markup)


@bot.message_handler(commands=['show_full_history'])
def show_repair_history(message):
    name, user_id, cars = get_name_id_cars(message)

    if not cars:
        bot.reply_to(message, f'{name}, у тебя нет автомобилей.')
        return
    elif len(cars) < 2:
        get_car_history(cars[0][0], user_id)
    else:
        text = 'Историю какого автомобиля нужно выгрузить?'
        create_markup_menu(cars, text, user_id, 'get_car_history')


@bot.callback_query_handler(func=lambda call:
                            call.data.startswith('get_car_history_'))
def handle_get_car_history(call):
    car_name = call.data[len('get_car_history_'):]
    get_car_history(car_name, call.from_user.id)


def get_car_history(car_name: str, telegram_id: int):
    data = bot.sqlite_client.execute_select_command(qs.GET_REPAIR_INFO,
                                                    (car_name, telegram_id))

    if data:
        bot.send_message(telegram_id,
                         f'📒История по автомобилю <i>{car_name}</i>:',
                         parse_mode='Html')
        res = []
        for row in data:
            mileage, date, info = row
            text = (f'Пробег: {mileage} км. || Дата: {date} '
                    f'|| Выполненные действия: {info}.')
            res.append(text)
        bot.send_message(telegram_id, '\n\n'.join(res))
    else:
        bot.send_message(telegram_id, 'История пуста.')


@bot.message_handler(func=lambda message:
                     not message.content_type == 'command')
def handle_unknow_message(message):
    bot.reply_to(message,
                 '❗️Я не понял сообщение.❗️\n'
                 'Используй команды, представленные в "<b>Меню</b>".',
                 parse_mode='Html')


def create_error_message(err: Exception) -> str:
    return (f'{dt.datetime.now().strftime("%Y/%m/%d %H:%M")} --- '
            f'{err.__class__} --- {err}')


def main():
    while True:
        try:
            bot.setup_resourses()
            bot.polling()
        except Exception as err:
            error_message = create_error_message(err)
            bot.telegram_client.post(method='sendMessage',
                                     params={'text': error_message,
                                             'chat_id': ADMIN_CHAT_ID})
            logger.error(error_message)

        finally:
            bot.shutdown()
            time.sleep(5)


if __name__ == '__main__':
    main()
