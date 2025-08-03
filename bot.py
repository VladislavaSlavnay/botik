import asyncio
import os
import logging
import json
import signal
import sys
import re
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, List, Dict, Tuple

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_PATH", "data"))  # По умолчанию 'data/', если переменной нет
DATA_DIR.mkdir(exist_ok=True)

import aiogram
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, InputMediaPhoto
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

BASE_DIR = Path("/path/to/bot")
load_dotenv(dotenv_path=BASE_DIR / '.env', override=True)

# Получаем токен из переменных среды
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Проверка токена
if not BOT_TOKEN or ":" not in BOT_TOKEN:
    logger.error("❌ Токен бота невалиден или отсутствует!")
    if not BOT_TOKEN:
        logger.error("Токен не найден в переменных среды")
    else:
        logger.error(f"Текущий токен: {BOT_TOKEN}")
    exit(1)

# ID администраторов (можно добавлять через команду)
ADMIN_IDS = [834553662, 553588882, 2054326653, 1852003919, 966420322]

# ===== СТРУКТУРА ПАПОК =====
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Файлы для хранения данных
FAQ_FILE = DATA_DIR / "faq.txt"
MENU_FILE = DATA_DIR / "menu.txt"
APPEALS_FILE = DATA_DIR / "appeals.txt"
ADMINS_FILE = DATA_DIR / "admins.txt"
PID_FILE = BASE_DIR / "bot.pid"

# Папки для хранения медиа
MAPS_DIR = DATA_DIR / "maps"
MAPS_DIR.mkdir(exist_ok=True)

PROGRAM_DIR = DATA_DIR / "program"
PROGRAM_DIR.mkdir(exist_ok=True)

MENU_PHOTO_DIR = DATA_DIR / "menu_photos"
MENU_PHOTO_DIR.mkdir(exist_ok=True)

SECTIONS_DIR = DATA_DIR / "sections"
SECTIONS_DIR.mkdir(exist_ok=True)

DIRECTORATE_DIR = DATA_DIR / "directorate"
DIRECTORATE_DIR.mkdir(exist_ok=True)

bot = None

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def save_admins():
    """Сохраняет ID администраторов в файл"""
    try:
        with open(ADMINS_FILE, "w") as f:
            for admin_id in ADMIN_IDS:
                f.write(f"{admin_id}\n")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения админов: {e}")
        return False

def load_admins():
    """Загружает ID администраторов из файла"""
    global ADMIN_IDS
    if ADMINS_FILE.exists():
        try:
            with open(ADMINS_FILE, "r") as f:
                ADMIN_IDS = [int(line.strip()) for line in f if line.strip()]
                logger.info(f"Загружено {len(ADMIN_IDS)} администраторов")
        except Exception as e:
            logger.error(f"Ошибка загрузки админов: {e}")
    else:
        save_admins()

async def forward_to_admins(message: Message, text: str):
    """Пересылает сообщение администраторам"""
    try:
        with open(APPEALS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{message.date.isoformat()}||{message.from_user.id}||{message.from_user.full_name}||{message.text}\n")
        
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, text)
            except Exception as e:
                logger.error(f"Ошибка отправки админу {admin_id}: {e}")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения обращения: {e}")
        return False

async def save_media_file(file_id: str, directory: Path, filename: str) -> bool:
    """Сохраняет медиафайл на диск"""
    try:
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        # Создаем целевую папку, если не существует
        directory.mkdir(exist_ok=True, parents=True)
        
        # Формируем путь для сохранения
        dest_path = directory / filename
        
        # Скачиваем и сохраняем файл
        await bot.download_file(file_path, dest_path)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения файла: {str(e)}")
        return False

def get_sorted_photos(directory: Path) -> List[Path]:
    """Возвращает отсортированный список фото в директории"""
    if not directory.exists():
        return []
    
    # Получаем все файлы jpg/jpeg
    photos = list(directory.glob("*.jpg")) + list(directory.glob("*.jpeg"))
    
    # Сортируем по числу в имени файла
    def extract_number(filename):
        match = re.search(r'(\d+)', filename.stem)
        return int(match.group(1)) if match else 0
    
    return sorted(photos, key=extract_number)

# ===== СЕКЦИИ =====
SECTIONS = {
    "vneucheb": "Внеучебная служба",
    "edu": "Образовательная служба",
    "food": "Служба питания",
    "accom": "Служба размещения",
    "members": "Служба по работе с участниками и волонтерами",
    "directorate": "Дирекция форума",
    "partners": "Работа с партнерами",
    "event": "Ивент служба форума",
    "tech": "Техническая служба",
    "directorate_staff": "Штаб Дирекции",
    "field": "Полевая программа",
    "protocol": "Протокольная служба",
    "press_service": "Пресс-служба"
}

def get_section_info(section_id: str) -> Tuple[str, List[Path]]:
    """Возвращает текст и фото для раздела"""
    # Текст
    text_file = SECTIONS_DIR / section_id / "text.txt"
    text = ""
    if text_file.exists():
        try:
            text = text_file.read_text(encoding="utf-8")
        except:
            text = "Описание раздела отсутствует."
    
    # Фото
    photo_dir = SECTIONS_DIR / section_id
    photos = get_sorted_photos(photo_dir)
    
    return text, photos

# ===== ИНИЦИАЛИЗАЦИЯ =====
router = Router()

# Состояния FSM
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

# Загрузка администраторов при старте
load_admins()

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
        success = await forward_to_admins(
            message,
            f"📩 Бытовое обращение от @{message.from_user.username or message.from_user.full_name} (ID: {message.from_user.id}):\n\n{message.text}"
        )
        if success:
            await message.answer("✅ Ваше сообщение отправлено администраторам.", reply_markup=main_kb)
        else:
            await message.answer("❌ Не удалось отправить сообщение.")
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
        
        # Получаем текст и фото для раздела
        text, photos = get_section_info(section_id)
        
        await callback.message.answer(f"📌 <b>{name}</b>\n\n{text}", parse_mode="HTML")

        if not photos:
            await callback.message.answer("❌ Фото пока не загружены.")
            return

        media = []
        for i, photo_path in enumerate(photos):
            with open(photo_path, "rb") as photo_file:
                if i == 0:
                    media.append(InputMediaPhoto(
                        media=photo_file,
                        caption=f"{name} (фото {i + 1}/{len(photos)})"
                    ))
                else:
                    media.append(InputMediaPhoto(media=photo_file))

        await callback.message.answer_media_group(media)
    except Exception as e:
        logger.error(f"Ошибка показа секции: {e}")
        await callback.message.answer("❌ Произошла ошибка при загрузке информации.")
    await callback.answer()

@router.message(F.text == "🍽 Узнать, чем сегодня кормят")
async def show_menu(message: Message):
    try:
        menu_text = "Вот меню столовой на сегодня.\nПриятного аппетита!\n\n"

        if MENU_FILE.exists():
            menu_text += MENU_FILE.read_text(encoding="utf-8").strip()
        else:
            menu_text += "Меню на сегодня пока не загружено."

        await message.answer(menu_text)
        
        # Проверяем наличие фото меню
        menu_photos = get_sorted_photos(MENU_PHOTO_DIR)
        if menu_photos:
            media = []
            for i, photo_path in enumerate(menu_photos):
                with open(photo_path, "rb") as photo_file:
                    if i == 0:
                        media.append(InputMediaPhoto(
                            media=photo_file,
                            caption="Меню на сегодня"
                        ))
                    else:
                        media.append(InputMediaPhoto(media=photo_file))
            await message.answer_media_group(media)
    except Exception as e:
        logger.error(f"Ошибка показа меню: {e}")
        await message.answer("❌ Не удалось загрузить меню.")

@router.message(F.text == "🗺 Посмотреть карту")
async def show_map(message: Message):
    try:
        map_files = get_sorted_photos(MAPS_DIR)
        if not map_files:
            await message.answer("❌ Карта территории пока не загружена.")
            return

        with open(map_files[0], "rb") as map_file:
            await message.answer_photo(
                map_file, 
                caption="Карта территории Всероссийского экологического центра \"Экосистема\""
            )
    except Exception as e:
        logger.error(f"Ошибка показа карты: {str(e)}")
        await message.answer("❌ Не удалось загрузить карту.")

@router.message(F.text == "📅 Программа на день")
async def daily_program(message: Message):
    try:
        program_files = get_sorted_photos(PROGRAM_DIR)
        if not program_files:
            await message.answer("Программа на день пока не загружена.")
            return

        media = []
        for i, program_file in enumerate(program_files):
            with open(program_file, "rb") as f:
                if i == 0:
                    media.append(InputMediaPhoto(
                        media=f,
                        caption="Программа на день 🌞"
                    ))
                else:
                    media.append(InputMediaPhoto(media=f))

        await message.answer_media_group(media)
    except Exception as e:
        logger.error(f"Ошибка загрузки программы: {str(e)}")
        await message.answer("❌ Произошла ошибка при загрузке программы.")

# ===== АДМИН-КОМАНДЫ =====
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

@router.message(Command("setmap"))
async def set_map_command(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ Только для админов.")
    await message.answer("📎 Пришлите новое фото карты:")

@router.message(F.photo, Command("setmap"))
async def handle_map_photo(message: Message):
    try:
        # Удаляем старые карты
        for old_map in MAPS_DIR.glob("*"):
            old_map.unlink()
        
        # Сохраняем новую карту
        file_id = message.photo[-1].file_id
        if await save_media_file(file_id, MAPS_DIR, "map.jpg"):
            await message.answer("✅ Карта успешно обновлена!")
        else:
            await message.answer("❌ Не удалось сохранить карту.")
    except Exception as e:
        logger.error(f"Ошибка сохранения карты: {str(e)}")
        await message.answer("❌ Произошла ошибка при сохранении карты.")

@router.message(Command("setprogram"))
async def set_program_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может использовать эту команду.")
        return

    # Очищаем предыдущую программу
    for old_program in PROGRAM_DIR.glob("*"):
        old_program.unlink()
    
    await message.answer("✅ Предыдущая программа очищена.\nОтправляйте фото программы по одному. Для завершения отправьте /done")
    await state.set_state(SetProgram.waiting_for_photos)

@router.message(SetProgram.waiting_for_photos, F.photo)
async def save_program_photo(message: Message, state: FSMContext):
    try:
        # Определяем следующий номер файла
        existing_files = list(PROGRAM_DIR.glob("*"))
        next_num = len(existing_files) + 1
        filename = f"program_{next_num}.jpg"
        
        file_id = message.photo[-1].file_id
        if await save_media_file(file_id, PROGRAM_DIR, filename):
            await message.answer(f"✅ Фото программы {next_num} сохранено.")
        else:
            await message.answer("❌ Не удалось сохранить фото.")
    except Exception as e:
        logger.error(f"Ошибка сохранения фото программы: {str(e)}")
        await message.answer("❌ Не удалось сохранить фото.")

@router.message(Command("done"), SetProgram.waiting_for_photos)
async def finish_program_upload(message: Message, state: FSMContext):
    try:
        program_files = list(PROGRAM_DIR.glob("*"))
        await message.answer(f"✅ Программа обновлена! Загружено {len(program_files)} фото.")
    except Exception as e:
        logger.error(f"Ошибка завершения загрузки программы: {str(e)}")
        await message.answer("❌ Произошла ошибка при сохранении программы.")
    await state.clear()

@router.message(Command("setmenu"))
async def set_menu_start(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ Только для админов.")
    await message.answer("📄 Пришлите текст или фото нового меню.")

@router.message(F.text, Command("setmenu"))
async def set_menu_text(message: Message):
    try:
        MENU_FILE.write_text(message.text.strip(), encoding="utf-8")
        await message.answer("✅ Текстовое меню обновлено.")
    except Exception as e:
        logger.error(f"Ошибка меню: {e}")
        await message.answer("❌ Не удалось сохранить меню.")

@router.message(F.photo, Command("setmenu"))
async def set_menu_photo(message: Message):
    try:
        # Очищаем старые фото меню
        for old_menu in MENU_PHOTO_DIR.glob("*"):
            old_menu.unlink()
        
        # Сохраняем новое фото
        file_id = message.photo[-1].file_id
        if await save_media_file(file_id, MENU_PHOTO_DIR, "menu.jpg"):
            await message.answer("✅ Фото меню обновлено.")
        else:
            await message.answer("❌ Не удалось сохранить фото меню.")
    except Exception as e:
        logger.error(f"Ошибка сохранения фото меню: {e}")
        await message.answer("❌ Не удалось сохранить фото.")

@router.message(Command("upload_director_photos"))
async def upload_director_photos(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ Только для админов.")

    # Очищаем предыдущие фото
    for old_photo in DIRECTORATE_DIR.glob("*"):
        old_photo.unlink()
    
    await message.answer(
        "✅ Предыдущие фото дирекции очищены.\n"
        "📸 Отправляйте фото для дирекции по одному. "
        "Для завершения отправьте /done\n\n"
        "Фото будут добавлены в раздел дирекции."
    )
    await state.set_state(UploadDirectorPhotos.waiting_for_photos)

@router.message(UploadDirectorPhotos.waiting_for_photos, F.photo)
async def save_director_photo(message: Message, state: FSMContext):
    try:
        # Определяем следующий номер файла
        existing_files = list(DIRECTORATE_DIR.glob("*"))
        next_num = len(existing_files) + 1
        filename = f"photo_{next_num}.jpg"
        
        file_id = message.photo[-1].file_id
        if await save_media_file(file_id, DIRECTORATE_DIR, filename):
            await message.answer(f"✅ Фото {next_num} сохранено в раздел дирекции.")
        else:
            await message.answer("❌ Не удалось сохранить фото.")
    except Exception as e:
        logger.error(f"Ошибка сохранения фото дирекции: {e}")
        await message.answer("❌ Не удалось сохранить фото.")

@router.message(Command("done"), UploadDirectorPhotos.waiting_for_photos)
async def finish_director_upload(message: Message, state: FSMContext):
    photo_files = list(DIRECTORATE_DIR.glob("*"))
    count = len(photo_files)
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
        section_dir = SECTIONS_DIR / section_id
        section_dir.mkdir(exist_ok=True)
        
        # Определяем следующий номер фото
        existing_files = list(section_dir.glob("*.jpg"))
        next_num = len(existing_files) + 1
        filename = f"photo_{next_num}.jpg"
        
        file_id = message.photo[-1].file_id
        if await save_media_file(file_id, section_dir, filename):
            await message.answer(f"✅ Фото {next_num} сохранено для раздела.")
        else:
            await message.answer("❌ Не удалось сохранить фото.")
    except Exception as e:
        logger.error(f"Ошибка сохранения фото: {e}")
        await message.answer("❌ Не удалось сохранить фото.")

@router.message(Command("done"), AddInfo.waiting_for_photos)
async def admin_done_uploading(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        section_id = data["section_id"]
        text = data["text"]
        
        # Сохраняем текст
        text_file = SECTIONS_DIR / section_id / "text.txt"
        text_file.write_text(text, encoding="utf-8")
        
        # Получаем количество фото
        photo_dir = SECTIONS_DIR / section_id
        photo_count = len(list(photo_dir.glob("*.jpg")))
        
        await message.answer(f"✅ Информация для раздела обновлена! Текст сохранён, {photo_count} фото добавлено.")
    except Exception as e:
        logger.error(f"Ошибка завершения загрузки: {e}")
        await message.answer("❌ Не удалось сохранить информацию.")
    await state.clear()

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
    if save_admins():
        await message.answer(f"✅ Пользователь {new_admin_id} добавлен в администраторы.")
    else:
        await message.answer(f"✅ Пользователь {new_admin_id} добавлен, но не сохранён в файл.")

@router.message(Command("listadmins"))
async def list_admins(message: Message):
    if not is_admin(message.from_user.id):
        return
    admins = "\n".join(str(i) for i in ADMIN_IDS)
    await message.answer(f"📋 Список админов:\n{admins}")

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
        "/upload_director_photos — загрузить фото дирекции\n"
        "/shutdown — остановить бота\n"
        "/done — завершить загрузку фото"
    )

@router.message(Command("view_appeals"))
async def view_appeals(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        if not APPEALS_FILE.exists():
            await message.answer("Обращений нет.")
            return
            
        with open(APPEALS_FILE, "r", encoding="utf-8") as f:
            appeals = f.readlines()
        
        if not appeals:
            await message.answer("Обращений нет.")
            return
            
        # Берем последние 10 обращений
        last_appeals = appeals[-10:] if len(appeals) > 10 else appeals
        response = "Последние обращения:\n\n" + "\n".join(last_appeals)
        
        # Разбиваем на части если слишком длинное
        if len(response) > 4000:
            parts = [response[i:i+4000] for i in range(0, len(response), 4000)]
            for part in parts:
                await message.answer(part)
        else:
            await message.answer(response)
    except Exception as e:
        logger.error(f"Ошибка чтения обращений: {e}")
        await message.answer("❌ Не удалось прочитать обращения.")

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
    
    # Удаляем PID-файл при завершении
    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
            logger.info("PID-файл удален")
        except Exception as e:
            logger.error(f"Ошибка удаления PID-файла: {e}")

@router.message(Command("shutdown"))
async def shutdown_command(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🔴 Выключаюсь...")
    await shutdown()
    # Останавливаем event loop
    sys.exit(0)

# ===== ЗАПУСК БОТА =====
async def main():
    global bot

    # Улучшенная проверка токена
    if not BOT_TOKEN or len(BOT_TOKEN) < 30 or ":" not in BOT_TOKEN:
        logger.error("Неверный формат токена! Токен должен быть в формате '123456789:ABCdefGHIjklMnOpQRSTuVWXyz'")
        return

    try:
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
        await dp.start_polling(bot, close_bot_session=True)

    except asyncio.CancelledError:
        logger.info("Получен сигнал завершения работы")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
    finally:
        await shutdown()

# ===== ТОЧКА ВХОДА =====
if __name__ == "__main__":
    # Функция для обработки сигналов
    def handle_exit(signum, frame):
        logger.info(f"Получен сигнал {signum}, завершение работы...")
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(shutdown())
        sys.exit(0)
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    try:
        # Проверка на уже запущенный экземпляр
        if PID_FILE.exists():
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
                
            # Проверяем, существует ли процесс (для Linux)
            if sys.platform != "win32" and os.path.exists(f"/proc/{old_pid}"):
                logger.error("❌ Бот уже запущен! Остановите предыдущий экземпляр.")
                sys.exit(1)
            else:
                # Для Windows просто удаляем устаревший файл
                PID_FILE.unlink()
                logger.warning("Удален устаревший PID-файл")
                
        # Сохраняем PID текущего процесса
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
            
        asyncio.run(main())
        
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.exception("Критическая ошибка")
    finally:
        # Убедимся, что shutdown выполнен
        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except:
                pass


