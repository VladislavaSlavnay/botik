import asyncio
import os
import atexit
import logging
import json
from pathlib import Path
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, CallbackQuery, InputMediaPhoto
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart, StateFilter

# ===== НАСТРОЙКИ =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / '.env', override=True)

# Получаем токен из переменных среды
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Добавляем проверку токена перед запуском
if not BOT_TOKEN or ":" not in BOT_TOKEN:
    logger.error("❌ Токен бота невалиден или отсутствует!")
    if not BOT_TOKEN:
        logger.error("Токен не найден в переменных среды")
    else:
        logger.error(f"Текущий токен: {BOT_TOKEN}")
    exit(1)

ADMIN_IDS = [834553662, 553588882, 2054326653, 1852003919, 966420322, 1852003919, 834553662]

# Файлы для хранения данных
FAQ_FILE = BASE_DIR / "faq.txt"
MAP_FILE = BASE_DIR / "map.txt"  # Теперь храним file_id
MENU_FILE = BASE_DIR / "menu.txt"
INFO_FILE = BASE_DIR / "section_info.txt"
PHOTO_DATA_FILE = BASE_DIR / "photo_data.json"  # Хранилище file_id

bot = None


# Загрузка данных фото
def load_photo_data():
    if PHOTO_DATA_FILE.exists():
        try:
            with open(PHOTO_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {
        "sections": {},
        "program": [],
        "directorate": [],
        "map": None,
        "menu": None
    }


# Сохранение данных фото
def save_photo_data(data):
    with open(PHOTO_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# Инициализация хранилища
photo_data = load_photo_data()


# Состояния FSM

class SetMenu(StatesGroup):
    waiting_for_content = State()

class FSMFillForm(StatesGroup):
    obrsahenie = State()


class UploadDirectorPhotos(StatesGroup):
    waiting_for_photos = State()


class AddInfo(StatesGroup):
    waiting_for_section = State()
    waiting_for_text = State()
    waiting_for_photos = State()


class SetFAQ(StatesGroup):
    waiting_for_text = State()


class SetProgram(StatesGroup):
    waiting_for_photos = State()


# Секции
SECTIONS = {
    "vneucheb": "Внеучебная служба",
    "edu": "Образовательная служба",
    "food": "Служба питания",
    "accom": "Служба размещения",
    "members": "Служба по работе с участниками и волонтерами",
    "partners": "Работа с партнерами",
    "escato": "Программа ЭСКАТО",
    "event": "Ивент служба форума",
    "finance_partners": "Финансовые партнеры",
    "education": "Образовательная программа",
    "tech": "Техническая служба",
    "directorate_staff": "Штаб Дирекции",
    "field": "Полевая программа",
    "protocol": "Протокольная служба",
    "press_service": "Пресс-служба"
}

APPEALS_FILE = BASE_DIR / "appeals.txt"

# ===== ИНИЦИАЛИЗАЦИЯ =====
router = Router()
section_data = {}


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def load_info():
    if INFO_FILE.exists():
        with open(INFO_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("||", 1)
                if len(parts) == 2:
                    key, text = parts
                    section_data[key] = text


def save_info():
    with open(INFO_FILE, "w", encoding="utf-8") as f:
        for key, text in section_data.items():
            f.write(f"{key}||{text}\n")


async def forward_to_admins(message: Message, text: str):
    with open(APPEALS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{message.date.isoformat()}||{message.from_user.id}||{message.from_user.full_name}||{message.text}\n")

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения админу {admin_id}: {e}")


# ===== КЛАВИАТУРЫ =====
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📝 Найти ответы на вопросы")],
        [KeyboardButton(text="🏡 Позаботиться о комфорте в глэмпинге")],
        [KeyboardButton(text="👥 Познакомиться с дирекцией Форума")],
        [KeyboardButton(text="🗺 Посмотреть карту")],
        [KeyboardButton(text="🍽 Узнать, чем сегодня кормят")],
        [KeyboardButton(text="📅 Программа на день")],
    ],
    resize_keyboard=True
)


def section_keyboard():
    kb = InlineKeyboardBuilder()
    for key, name in SECTIONS.items():
        kb.button(text=name, callback_data=f"section:{key}")
    kb.adjust(2)
    return kb.as_markup()


# ===== ОБРАБОТЧИКИ КОМАНД =====
@router.message(Command("setfaq"))
async def set_faq(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может использовать эту команду.")
        return
    await message.answer("✏️ Отправьте новый текст FAQ целиком:")
    await state.set_state(SetFAQ.waiting_for_text)


@router.message(SetFAQ.waiting_for_text)
async def save_faq_text(message: Message, state: FSMContext):
    try:
        FAQ_FILE.write_text(message.text.strip(), encoding="utf-8")
        await message.answer("✅ FAQ успешно обновлён.")
    except Exception as e:
        logger.error(f"Ошибка сохранения FAQ: {e}")
        await message.answer("❌ Не удалось сохранить FAQ.")
    await state.clear()


# ===== ОБРАБОТЧИК ПРОГРАММЫ НА ДЕНЬ =====
@router.message(F.text == "📅 Программа на день")
async def daily_program(message: Message):
    try:
        program_photos = photo_data.get("program", [])

        if not program_photos:
            await message.answer("Программа на день пока не загружена.")
            return

        media = []
        for i, file_id in enumerate(program_photos):
            if i == 0:
                media.append(InputMediaPhoto(
                    media=file_id,
                    caption="Программа на день 🌞"
                ))
            else:
                media.append(InputMediaPhoto(media=file_id))

        await message.answer_media_group(media)
    except Exception as e:
        logger.error(f"Ошибка загрузки программы: {e}")
        await message.answer("❌ Произошла ошибка при загрузке программы.")


# ===== АДМИН-КОМАНДЫ ДЛЯ ПРОГРАММЫ =====
@router.message(Command("setprogram"))
async def set_program_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может использовать эту команду.")
        return

    # Очищаем предыдущие фото
    photo_data["program"] = []
    save_photo_data(photo_data)

    await message.answer("Отправляйте фото программы по одному. Для завершения отправьте /done")
    await state.set_state(SetProgram.waiting_for_photos)


@router.message(SetProgram.waiting_for_photos, F.photo)
async def save_program_photo(message: Message, state: FSMContext):
    try:
        file_id = message.photo[-1].file_id
        photo_data["program"].append(file_id)
        save_photo_data(photo_data)

        count = len(photo_data["program"])
        await message.answer(f"✅ Фото {count} сохранено.")
    except Exception as e:
        logger.error(f"Ошибка сохранения фото программы: {e}")
        await message.answer("❌ Не удалось сохранить фото.")


@router.message(Command("done"), SetProgram.waiting_for_photos)
async def finish_program_upload(message: Message, state: FSMContext):
    count = len(photo_data["program"])
    await message.answer(f"✅ Программа обновлена! Загружено {count} фото.")
    await state.clear()


# ===== ОСНОВНЫЕ ОБРАБОТЧИКИ =====
@router.message(CommandStart())
async def start(message: Message):
    welcome_text = (
        "Привет, хранитель природы! 🌿 Рад видеть тебя на форуме «Экосистема. Заповедный край». "
        "Я помогу тебе:\n\n"
        "🏡 Комфортно устроиться в нашем экологичном жилом комплексе\n"
        "📝 Найти ответы на частые вопросы\n"
        "🗺 Посмотреть карту\n"
        "👥 Познакомиться с командой организаторов\n"
        "🍽 Узнать, чем сегодня кормят\n"
        "📅 Посмотреть программу на день\n\n"
        "Выбери нужное действие ниже ↓"
    )
    await message.answer(welcome_text, reply_markup=main_kb)


@router.message(F.text == "📝 Найти ответы на вопросы")
async def faq(message: Message):
    try:
        if FAQ_FILE.exists():
            text = FAQ_FILE.read_text(encoding="utf-8").strip()
        else:
            text = "❓ Часто задаваемые вопросы пока не добавлены."

        faq_text = (
            "Здесь мы собрали часто задаваемые вопросы. Просмотри, вдруг ты найдешь здесь ответ для себя:\n\n"
            f"{text}\n\n"
            "Если ответ не удалось найти, то задай его кураторам команды"
        )
        await message.answer(faq_text)
    except Exception as e:
        logger.error(f"Ошибка загрузки FAQ: {e}")
        await message.answer("❌ Произошла ошибка при загрузке FAQ.")


@router.message(F.text == "🏡 Позаботиться о комфорте в глэмпинге")
async def household_prompt(message: Message, state: FSMContext):
    comfort_text = (
        "Столкнулся с проблемой по проживанию или быту? Напиши нам, и мы постараемся решить её как можно скорее!\n\n"
        "Отправь сообщение по форме:\n"
        "\"Твой вопрос/просьба/описание ситуации, ФИО, номер команды, номер палатки\"\n\n"
        "Чтобы вернуться в меню, отправь /cancel"
    )
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )
    await message.answer(comfort_text, reply_markup=cancel_kb)
    await state.set_state(FSMFillForm.obrsahenie)


@router.message(StateFilter(FSMFillForm.obrsahenie), F.text)
async def forward_to_admin(message: Message, state: FSMContext):
    if message.text.lower() in ["отмена", "/cancel", "❌ отмена"]:
        await message.answer("❌ Обращение отменено", reply_markup=main_kb)
        await state.clear()
        return

    try:
        await message.answer("✅ Ваше сообщение отправлено администраторам.", reply_markup=main_kb)
        user = message.from_user
        await forward_to_admins(
            message,
            f"📩 Бытовое обращение от @{user.username or user.full_name} (ID: {user.id}):\n\n{message.text}"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения админам: {e}")
        await message.answer("❌ Не удалось отправить сообщение.")
    await state.clear()


@router.message(F.text == "👥 Познакомиться с дирекцией Форума")
async def directorate(message: Message):
    directorate_text = (
        "Смотри, какие замечательные люди создают наш Форум! "
        "Если будешь встречать их, обязательно поблагодари за их работу 😉\n\n"
        "Выбери необходимую службу:"
    )
    await message.answer(directorate_text, reply_markup=section_keyboard())


@router.callback_query(F.data.startswith("section:"))
async def show_section(callback: CallbackQuery):
    try:
        section_id = callback.data.split(":")[1]
        name = SECTIONS.get(section_id, "Неизвестно")
        text = section_data.get(section_id, "Нет описания.")

        await callback.message.answer(f"📌 <b>{name}</b>\n\n{text}", parse_mode="HTML")

        # Определяем источник фото
        if section_id == "directorate":
            file_ids = photo_data.get("directorate", [])
        else:
            file_ids = photo_data.get("sections", {}).get(section_id, [])

        if not file_ids:
            await callback.message.answer("❌ Фото пока не загружены.")
            return

        media = []
        for i, file_id in enumerate(file_ids):
            if i == 0:
                media.append(InputMediaPhoto(
                    media=file_id,
                    caption=f"{name} (фото {i + 1}/{len(file_ids)})"
                ))
            else:
                media.append(InputMediaPhoto(media=file_id))

        await callback.message.answer_media_group(media)
    except Exception as e:
        logger.error(f"Ошибка показа секции: {e}")
        await callback.message.answer("❌ Произошла ошибка при загрузке информации.")
    await callback.answer()


@router.message(F.text == "🗺 Посмотреть карту")
async def show_map(message: Message):
    try:
        map_text = "Держи карту территории Всероссийского экологического центра \"Экосистема\""
        await message.answer(map_text)

        map_file_id = photo_data.get("map")
        if map_file_id:
            await message.answer_photo(map_file_id)
        else:
            await message.answer("❌ Карта территории пока не загружена.")
    except Exception as e:
        logger.error(f"Ошибка показа карты: {e}")
        await message.answer("❌ Не удалось загрузить карту.")


@router.message(F.text == "🍽 Узнать, чем сегодня кормят")
async def show_menu(message: Message):
    try:
        menu_text = "Вот меню столовой на сегодня.\nПриятного аппетита!\n\n"

        if MENU_FILE.exists():
            menu_text += MENU_FILE.read_text(encoding="utf-8").strip()
        else:
            menu_text += "Меню на сегодня пока не загружено."

        await message.answer(menu_text)

        # Показываем фото меню, если есть
        menu_photo_id = photo_data.get("menu")
        if menu_photo_id:
            await message.answer_photo(menu_photo_id)
    except Exception as e:
        logger.error(f"Ошибка показа меню: {e}")
        await message.answer("❌ Не удалось загрузить меню.")


# ===== АДМИН-КОМАНДЫ =====

# ===== КОМАНДА ДЛЯ ЗАГРУЗКИ ФОТО ДИРЕКЦИИ ОТДЕЛЬНО =====
@router.message(Command("upload_director_photos"))
async def upload_director_photos(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ Только для админов.")

    # Очищаем предыдущие фото
    photo_data["directorate"] = []
    save_photo_data(photo_data)

    await message.answer(
        "📸 Отправляйте фото для дирекции по одному. "
        "Для завершения отправьте /done\n\n"
        "Фото будут добавлены в раздел дирекции."
    )
    await state.set_state(UploadDirectorPhotos.waiting_for_photos)


@router.message(UploadDirectorPhotos.waiting_for_photos, F.photo)
async def save_director_photo(message: Message, state: FSMContext):
    try:
        file_id = message.photo[-1].file_id
        photo_data["directorate"].append(file_id)
        save_photo_data(photo_data)

        count = len(photo_data["directorate"])
        await message.answer(f"✅ Фото {count} сохранено в раздел дирекции.")
    except Exception as e:
        logger.error(f"Ошибка сохранения фото дирекции: {e}")
        await message.answer("❌ Не удалось сохранить фото.")


@router.message(Command("done"), UploadDirectorPhotos.waiting_for_photos)
async def finish_director_upload(message: Message, state: FSMContext):
    count = len(photo_data["directorate"])
    await message.answer(f"✅ Загрузка фото дирекции завершена! Добавлено {count} фото.")
    await state.clear()


@router.message(Command("addinfo"))
async def add_info_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может использовать эту команду.")
        return

    kb = InlineKeyboardBuilder()
    for k, v in SECTIONS.items():
        kb.button(text=v, callback_data=f"admin_set:{k}")
    kb.adjust(2)
    await message.answer("Выберите раздел:", reply_markup=kb.as_markup())
    await state.set_state(AddInfo.waiting_for_section)


@router.callback_query(F.data.startswith("admin_set:"), AddInfo.waiting_for_section)
async def admin_select_section(callback: CallbackQuery, state: FSMContext):
    section_id = callback.data.split(":")[1]
    await state.update_data(section_id=section_id)
    await callback.message.answer("Введите новый текст описания:")
    await state.set_state(AddInfo.waiting_for_text)
    await callback.answer()


@router.message(AddInfo.waiting_for_text)
async def admin_set_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer("Теперь отправляйте фото по одному. Когда закончите — напишите /done")
    await state.set_state(AddInfo.waiting_for_photos)


@router.message(AddInfo.waiting_for_photos, F.photo)
async def admin_save_photos(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        section_id = data["section_id"]

        # Инициализируем хранилище для раздела, если нужно
        if "sections" not in photo_data:
            photo_data["sections"] = {}
        if section_id not in photo_data["sections"]:
            photo_data["sections"][section_id] = []

        # Сохраняем file_id
        file_id = message.photo[-1].file_id
        photo_data["sections"][section_id].append(file_id)
        save_photo_data(photo_data)

        count = len(photo_data["sections"][section_id])
        await message.answer(f"✅ Фото {count} сохранено.")
    except Exception as e:
        logger.error(f"Ошибка сохранения фото: {e}")
        await message.answer("❌ Не удалось сохранить фото.")


@router.message(Command("done"), AddInfo.waiting_for_photos)
async def admin_done_uploading(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        section_id = data["section_id"]
        section_data[section_id] = data["text"]
        save_info()

        count = len(photo_data["sections"].get(section_id, []))
        await message.answer(f"✅ Описание и {count} фото обновлены.")
    except Exception as e:
        logger.error(f"Ошибка завершения загрузки: {e}")
        await message.answer("❌ Не удалось сохранить информацию.")
    await state.clear()


# ДОБАВЛЕНИЕ И УДАЛЕНИЕ АДМИНОВ
@router.message(Command("addadmin"))
async def add_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("⛔️ Только текущий админ может добавить другого администратора.")
    if not message.reply_to_message:
        return await message.answer("Ответьте на сообщение пользователя, которого хотите сделать админом.")
    new_admin_id = message.reply_to_message.from_user.id
    if new_admin_id in ADMIN_IDS:
        return await message.answer("✅ Этот пользователь уже админ.")
    ADMIN_IDS.append(new_admin_id)
    await message.answer(f"✅ Пользователь {new_admin_id} добавлен в администраторы.")


@router.message(Command("listadmins"))
async def list_admins(message: Message):
    if not is_admin(message.from_user.id):
        return
    admins = "\n".join(str(i) for i in ADMIN_IDS)
    await message.answer(f"📋 Список админов:\n{admins}")


# УПРОЩЕННЫЕ КОМАНДЫ ДЛЯ ОБНОВЛЕНИЯ МЕНЮ, КАРТЫ
@router.message(Command("setmap"))
async def set_map(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ Только для админов.")
    await message.answer("📎 Пришлите новое фото карты.")


@router.message(F.photo, Command("setmap"))
async def save_map_photo(message: Message):
    try:
        file_id = message.photo[-1].file_id
        photo_data["map"] = file_id
        save_photo_data(photo_data)
        await message.answer("✅ Карта обновлена.")
    except Exception as e:
        logger.error(f"Ошибка сохранения карты: {e}")
        await message.answer("❌ Не удалось сохранить карту.")


@router.message(Command("setmenu"))
async def set_menu_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ Только для админов.")
    await message.answer(
        "📄 Пришлите текст или фото нового меню.\n"
        "Для отмены отправьте /cancel"
    )
    await state.set_state(SetMenu.waiting_for_content)

@router.message(SetMenu.waiting_for_content, F.text)
async def set_menu_text(message: Message, state: FSMContext):
    try:
        MENU_FILE.write_text(message.text.strip(), encoding="utf-8")
        # Очищаем фото меню, если был текст
        photo_data["menu"] = None
        save_photo_data(photo_data)
        await message.answer("✅ Текстовое меню обновлено.")
    except Exception as e:
        logger.error(f"Ошибка сохранения меню: {e}")
        await message.answer("❌ Не удалось сохранить меню.")
    await state.clear()

@router.message(SetMenu.waiting_for_content, F.photo)
async def set_menu_photo(message: Message, state: FSMContext):
    try:
        file_id = message.photo[-1].file_id
        photo_data["menu"] = file_id
        save_photo_data(photo_data)
        # Очищаем текстовое меню, если было фото
        if MENU_FILE.exists():
            MENU_FILE.unlink()
        await message.answer("✅ Фото меню обновлено.")
    except Exception as e:
        logger.error(f"Ошибка сохранения фото меню: {e}")
        await message.answer("❌ Не удалось сохранить фото.")
    await state.clear()

@router.message(Command("cancel"), SetMenu.waiting_for_content)
async def cancel_menu_update(message: Message, state: FSMContext):
    await message.answer("❌ Обновление меню отменено.")
    await state.clear()
    


@router.message(Command("helpadmin"))
async def help_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "🛠 Команды для админов:\n"
        "/addinfo — обновить описание и фото разделов\n"
        "/setfaq — обновить FAQ\n"
        "/setmap — загрузить карту\n"
        "/setmenu — текст или фото меню\n"
        "/setprogram — фото программы\n"
        "/addadmin — добавить админа (в ответ на его сообщение)\n"
        "/listadmins — показать текущих админов\n"
        "/view_appeals — показать последние обращения\n"
        "/upload_director_photos — загрузить фото дирекции\n"
        "/shutdown — остановить бота\n"
        "/done — завершить загрузку фото"
    )


# ===== ЗАВЕРШЕНИЕ РАБОТЫ =====
async def shutdown():
    global bot
    if bot:
        logger.info("Закрытие сессии бота...")
        try:
            # Отправляем уведомление администраторам
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, "🔴 Бот выключается...")
                except:
                    pass

            # Закрываем сессию
            await bot.session.close()
            logger.info("Сессия закрыта корректно")
        except Exception as e:
            logger.error(f"Ошибка при закрытии сессии: {e}")
    else:
        logger.warning("Бот не был инициализирован, закрытие не требуется")


# ===== ЗАПУСК БОТА =====
async def main():
    global bot

    # Улучшенная проверка токена
    if not BOT_TOKEN or len(BOT_TOKEN) < 30 or ":" not in BOT_TOKEN:
        logger.error("Неверный формат токена! Токен должен быть в формате '123456789:ABCdefGHIjklMnOpQRSTuVWXyz'")
        return

    try:
        # Загрузка данных
        load_info()

        # Инициализация бота с таймаутом
        bot = Bot(token=BOT_TOKEN, session_timeout=30)

        # Проверка подключения
        try:
            me = await bot.get_me()
            logger.info(f"Бот успешно подключен: @{me.username} (ID: {me.id})")
        except Exception as e:
            logger.error(f"Ошибка подключения к Telegram API: {e}")
            logger.error("Проверьте:")
            logger.error("1. Правильность токена")
            logger.error("2. Доступность API Telegram с вашего сервера")
            logger.error("3. Интернет-соединение")
            return

        # Инициализация диспетчера
        dp = Dispatcher()
        dp.include_router(router)

        # Настройка вебхука
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Вебхук успешно удален, режим polling")
        except Exception as e:
            logger.error(f"Ошибка настройки вебхука: {e}")
            return

        logger.info("Бот запущен и ожидает сообщений...")
        await dp.start_polling(bot)

    except asyncio.CancelledError:
        logger.info("Получен сигнал завершения работы")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
    finally:
        await shutdown()


# ===== ТОЧКА ВХОДА =====
if __name__ == "__main__":
    atexit.register(lambda: asyncio.run(shutdown()))

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.exception("Критическая ошибка")




