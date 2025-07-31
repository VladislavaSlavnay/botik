import asyncio
import os
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, CallbackQuery
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart, StateFilter


class FSMFillForm(StatesGroup):
        obrsahenie = State()

# ==== НАСТРОЙКИ ====
FAQ_FILE = "faq.txt"
BOT_TOKEN = ""  # Замени
ADMIN_ID = 834553662           # Замени

BASE_PHOTO_DIR = "photo_sections"
INFO_FILE = "section_info.txt"

SECTIONS = {
    "vneucheb": "Внеучебная служба",
    "edu": "Образовательная служба",
    "press": "Пресса",
    "food": "Служба питания",
    "accom": "Служба размещения",
    "members": "Служба по работе с участниками"
}

# FSM состояния для администратора
class AddInfo(StatesGroup):
    waiting_for_section = State()
    waiting_for_text = State()
    waiting_for_photos = State()




# Инициализация
router = Router()
section_data = {}

# === Функции для загрузки и сохранения ===
def load_info():
    if os.path.exists(INFO_FILE):
        with open(INFO_FILE, "r", encoding="utf-8") as f:
            for line in f:
                key, text = line.strip().split("||", 1)
                section_data[key] = text

def save_info():
    with open(INFO_FILE, "w", encoding="utf-8") as f:
        for key, text in section_data.items():
            f.write(f"{key}||{text}\n")

def get_photo_paths(section_id):
    folder = os.path.join(BASE_PHOTO_DIR, section_id)
    if not os.path.exists(folder):
        return []
    files = sorted(os.listdir(folder))
    return [os.path.join(folder, f) for f in files if f.lower().endswith((".jpg", ".jpeg", ".png"))]

# === Кнопки ===
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 FAQ")],
        [KeyboardButton(text="🛠 Бытовые обращения")],
        [KeyboardButton(text="📸 Дирекция")],
    ],
    resize_keyboard=True
)

def section_keyboard():
    kb = InlineKeyboardBuilder()
    for key, name in SECTIONS.items():
        kb.button(text=name, callback_data=f"section:{key}")
    kb.adjust(2)
    return kb.as_markup()


class SetFAQ(StatesGroup):
    waiting_for_text = State()

@router.message(Command("setfaq"))
async def set_faq(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только администратор может использовать эту команду.")
        return

    await message.answer("✏️ Отправьте новый текст FAQ целиком:")
    await state.set_state(SetFAQ.waiting_for_text)

@router.message(SetFAQ.waiting_for_text)
async def save_faq_text(message: Message, state: FSMContext):
    with open(FAQ_FILE, "w", encoding="utf-8") as f:
        f.write(message.text.strip())

    await message.answer("✅ FAQ успешно обновлён.")
    await state.clear()


# === Обработчики ===
@router.message(CommandStart())
async def start(message: Message):
    await message.answer("Добро пожаловать! Выберите нужный раздел:", reply_markup=main_kb)

@router.message(F.text == "📋 FAQ")
async def faq(message: Message):
    if os.path.exists(FAQ_FILE):
        with open(FAQ_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip()
    else:
        text = "❓ Часто задаваемые вопросы пока не добавлены."

    await message.answer(text)

@router.message(F.text == "🛠 Бытовые обращения")
async def household_prompt(message: Message, state: FSMContext):
    await message.answer("Опишите, чего не хватает. Мы передадим это администратору 👇")
    await state.set_state(FSMFillForm.obrsahenie)


@router.message(StateFilter(FSMFillForm.obrsahenie), lambda x: len(x.text.split())  >= 1)
async def forward_to_admin(message: Message, state: FSMContext):
    if message.text and message.text != "/start":
        await message.answer("✅ Ваше сообщение отправлено администратору.")
        user = message.from_user
        await message.bot.send_message(
            ADMIN_ID,
            f"📩 Бытовое обращение от @{user.username or user.full_name}:\n\n{message.text}"
        )
    await state.clear()


@router.message(F.text == "📸 Галерея")
async def gallery(message: Message):
    await message.answer("Выберите раздел:", reply_markup=section_keyboard())

@router.callback_query(F.data.startswith("section:"))
async def show_section(callback: CallbackQuery):
    section_id = callback.data.split(":")[1]
    name = SECTIONS.get(section_id, "Неизвестно")
    text = section_data.get(section_id, "Нет описания.")

    await callback.message.answer(f"📌 <b>{name}</b>\n\n{text}", parse_mode="HTML")

    photo_paths = get_photo_paths(section_id)
    if not photo_paths:
        await callback.message.answer("❌ Фото пока не загружены.")
        return

    for path in photo_paths:
        try:
            await callback.message.answer_photo(FSInputFile(path))
        except Exception as e:
            await callback.message.answer(f"⚠️ Ошибка при отправке {path}: {e}")
    await callback.answer()

# === Команда для добавления от админа ===
@router.message(Command("addinfo"))
async def add_info_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только админ может использовать эту команду.")
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
    await message.answer("Теперь отправляйте фото по одному (JPG/PNG). Когда закончите — напишите /done")
    await state.set_state(AddInfo.waiting_for_photos)

@router.message(AddInfo.waiting_for_photos, F.photo)
async def admin_save_photos(message: Message, state: FSMContext):
    data = await state.get_data()
    section_id = data["section_id"]
    folder = os.path.join(BASE_PHOTO_DIR, section_id)
    os.makedirs(folder, exist_ok=True)

    photo = message.photo[-1]
    count = len(os.listdir(folder)) + 1
    path = os.path.join(folder, f"{count}.jpg")
    file = await message.bot.get_file(photo.file_id)
    await message.bot.download_file(file_path=file.file_path, destination=path)

    await message.answer("📷 Фото добавлено.")

@router.message(Command("done"), AddInfo.waiting_for_photos)
async def admin_done_uploading(message: Message, state: FSMContext):
    data = await state.get_data()
    section_data[data["section_id"]] = data["text"]
    save_info()
    await message.answer("✅ Описание и фото обновлены.")
    await state.clear()



# === Запуск ===
async def main():
    os.makedirs(BASE_PHOTO_DIR, exist_ok=True)
    load_info()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
