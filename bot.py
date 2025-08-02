import asyncio
import os
import atexit
import logging
from pathlib import Path
from dotenv import load_dotenv

# ===== НАСТРОЙКА ЛОГГИРОВАНИЯ =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===== ЗАГРУЗКА ПЕРЕМЕННЫХ СРЕДЫ =====
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / '.env', override=True)
BOT_TOKEN = "8467183577:AAF_lfrVZmnL1jIlQRpeVmoV5WFEGs4T4Gw"
ADMIN_IDS = [834553662, 553588882, 2054326653, 1852003919, 966420322]  # Список ID администраторов

# ===== ИМПОРТЫ ИЗ AIOGRAM =====
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, CallbackQuery,
    InputMediaPhoto
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart, StateFilter

# ===== КОНФИГУРАЦИЯ ПУТЕЙ =====
BASE_PHOTO_DIR = BASE_DIR / "photo_sections"
FAQ_FILE = BASE_DIR / "faq.txt"
MAP_FILE = BASE_DIR / "map.jpg"  # Исправленный путь
MENU_FILE = BASE_DIR / "menu.txt"  # Исправленный путь
INFO_FILE = BASE_DIR / "section_info.txt"

# ===== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ =====
bot = None  # Инициализируется позже

# ===== СОСТОЯНИЯ =====
class FSMFillForm(StatesGroup):
    obrsahenie = State()

class AddInfo(StatesGroup):
    waiting_for_section = State()
    waiting_for_text = State()
    waiting_for_photos = State()

class SetFAQ(StatesGroup):
    waiting_for_text = State()

class SetProgram(StatesGroup):
    waiting_for_photos = State()

class SetMenu(StatesGroup):  # Новый класс для меню
    waiting_for_content = State()

class SetMap(StatesGroup):  # Новый класс для карты
    waiting_for_map = State()

# ===== КОНФИГУРАЦИЯ СЕКЦИЙ =====
SECTIONS = {
    "vneucheb": "Внеучебная служба",
    "edu": "Образовательная служба", 
    "food": "Служба питания",
    "accom": "Служба размещения",
    "members": "Служба по работе с участниками и волонтерами",
    "directorate": "Дирекция форума",
    "program_dir": "Программный директор",
    "find_dir": "Найти-директор",
    "ahd_dir": "Директор АХЧ",
    "activity_dir": "Директор по обеспечению деятельности",
    "partners": "Работа с партнерами",
    "escato": "Программа ЭСКАТО",
    "event": "Ивент служба форума",
    "finance_partners": "Финансовые партнеры",
    "education": "Образовательная программа",
    "tech": "Техническая служба",
    "nonfinance_partners": "Нефинансовые партнеры",
    "directorate_staff": "Штаб Дирекции",
    "field": "Полевая программа",
    "protocol": "Протокольная служба",
    "press_service": "Пресс-служба"
}

# ===== ИНИЦИАЛИЗАЦИЯ =====
router = Router()
section_data = {}

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
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

def get_photo_paths(section_id):
    folder = BASE_PHOTO_DIR / section_id
    if not folder.exists():
        return []
    
    return sorted(
        [f for f in folder.iterdir() if f.suffix.lower() in ('.jpg', '.jpeg', '.png')],
        key=lambda f: f.name
    )

async def forward_to_admins(message: Message, text: str):
    """Отправляет сообщение всем администраторам"""
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

# ===== ОБНОВЛЕННЫЙ ОБРАБОТЧИК ПРОГРАММЫ НА ДЕНЬ =====
@router.message(F.text == "📅 Программа на день")
async def daily_program(message: Message):
    try:
        program_dir = BASE_PHOTO_DIR / "program"
        if not program_dir.exists():
            await message.answer("Программа на день пока не загружена.")
            return
            
        photo_paths = get_photo_paths("program")
        
        if not photo_paths:
            await message.answer("Программа на день пока не загружена.")
            return
            
        media = []
        for i, path in enumerate(photo_paths):
            if i == 0:
                media.append(InputMediaPhoto(
                    media=FSInputFile(path),
                    caption="Программа на день 🌞"
                ))
            else:
                media.append(InputMediaPhoto(
                    media=FSInputFile(path)
                ))
                
        await message.answer_media_group(media)
    except Exception as e:
        logger.error(f"Ошибка загрузки программы: {e}")
        await message.answer("❌ Произошла ошибка при загрузке программы.")

# ===== ОБНОВЛЕННЫЕ АДМИН-КОМАНДЫ ДЛЯ ПРОГРАММЫ =====
@router.message(Command("setprogram"))
async def set_program_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может использовать эту команду.")
        return
        
    program_dir = BASE_PHOTO_DIR / "program"
    program_dir.mkdir(exist_ok=True)
    for file in program_dir.glob("*"):
        file.unlink()
        
    await message.answer(
        "📅 Отправьте до 4 фото программы дня <b>одним сообщением</b>\n"
        "Или /cancel для отмены",
        parse_mode="HTML"
    )
    await state.set_state(SetProgram.waiting_for_photos)

@router.message(SetProgram.waiting_for_photos, F.media_group_id, F.photo)
async def save_program_album(message: Message, album: list[Message], state: FSMContext):
    try:
        program_dir = BASE_PHOTO_DIR / "program"
        
        for i, msg in enumerate(album[:4]):
            photo = msg.photo[-1]
            path = program_dir / f"{i+1}.jpg"
            file = await bot.get_file(photo.file_id)
            await bot.download_file(file.file_path, destination=path)

        await message.answer(f"✅ Программа обновлена! Сохранено {len(album)} фото.")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()

@router.message(Command("cancel"), SetProgram.waiting_for_photos)
async def cancel_program_update(message: Message, state: FSMContext):
    await message.answer("❌ Обновление программы отменено")
    await state.clear()

# ===== НОВЫЙ ОБРАБОТЧИК ДЛЯ МЕНЮ =====
@router.message(Command("setmenu"))
async def set_menu_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может использовать эту команду.")
        return

    await message.answer(
        "🍽 Отправьте <b>текст меню</b> или <b>фото с меню</b>\n"
        "Поддерживаются:\n"
        "- Текстовое сообщение\n"
        "- Одно фото\n"
        "- Альбом из нескольких фото\n\n"
        "Или /cancel для отмены",
        parse_mode="HTML"
    )
    await state.set_state(SetMenu.waiting_for_content)

@router.message(SetMenu.waiting_for_content, F.text)
async def save_menu_text(message: Message, state: FSMContext):
    MENU_FILE.write_text(message.text, encoding="utf-8")
    await message.answer("✅ Текстовое меню сохранено!")
    await state.clear()

@router.message(SetMenu.waiting_for_content, F.photo)
async def save_menu_photo(message: Message, state: FSMContext):
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        await bot.download_file(file.file_path, destination=MENU_FILE.with_suffix('.jpg'))
        
        await message.answer("✅ Меню сохранено как фото!")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@router.message(Command("cancel"), SetMenu.waiting_for_content)
async def cancel_menu_update(message: Message, state: FSMContext):
    await message.answer("❌ Обновление меню отменено")
    await state.clear()

# ===== НОВЫЙ ОБРАБОТЧИК ДЛЯ КАРТЫ =====
@router.message(Command("setmap"))
async def set_map_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только администратор может использовать эту команду.")
        return
        
    await message.answer(
        "🗺 Отправьте новую карту как <b>файл</b> (не как фото!)\n"
        "Или /cancel для отмены",
        parse_mode="HTML"
    )
    await state.set_state(SetMap.waiting_for_map)

@router.message(SetMap.waiting_for_map, F.document)
async def save_map_file(message: Message, state: FSMContext):
    try:
        await bot.download(
            message.document,
            destination=MAP_FILE
        )
        await message.answer("✅ Карта обновлена!")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()

@router.message(Command("cancel"), SetMap.waiting_for_map)
async def cancel_map_update(message: Message, state: FSMContext):
    await message.answer("❌ Обновление карты отменено")
    await state.clear()

# ===== ОСНОВНЫЕ ОБРАБОТЧИКИ (остаются без изменений) =====
# ... (все остальные обработчики из вашего оригинального кода остаются без изменений)

# ===== ЗАПУСК БОТА =====
async def main():
    global bot
    
    # Улучшенная проверка токена
    if not BOT_TOKEN or len(BOT_TOKEN) < 30 or ":" not in BOT_TOKEN:
        logger.error("Неверный формат токена! Токен должен быть в формате '123456789:ABCdefGHIjklMnOpQRSTuVWXyz'")
        return

    try:
        # Создание папок
        BASE_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        for section in SECTIONS.keys():
            (BASE_PHOTO_DIR / section).mkdir(exist_ok=True)
        (BASE_PHOTO_DIR / "program").mkdir(exist_ok=True)

        # Загрузка данных
        load_info()
        
        # Инициализация бота
        bot = Bot(token=BOT_TOKEN, session_timeout=30)
        
        # Проверка подключения
        try:
            me = await bot.get_me()
            logger.info(f"Бот успешно подключен: @{me.username} (ID: {me.id})")
        except Exception as e:
            logger.error(f"Ошибка подключения к Telegram API: {e}")
            return

        # Инициализация диспетчера
        dp = Dispatcher()
        dp.include_router(router)
        
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Бот запущен и ожидает сообщений...")
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
    finally:
        await shutdown()

if __name__ == "__main__":
    atexit.register(lambda: asyncio.run(shutdown()))
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception("Критическая ошибка")
