import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import sheets

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = "8635126806:AAFP-bJLAZgnASFNihhLTviyktvsopiQ9dc"
CHECKIN_HOUR = 21
CHECKIN_MINUTE = 0

USERS = {
    829596300: {
        "sheet": "CycleTracker",
        "relationship_q": "💬 Як стосунки з дружиною сьогодні?",
        "cycle_q": (
            "📅 Фаза циклу дружини?\n"
            "_(наприклад: '3 день місячних', '5 днів до місячних', 'після овуляції'. "
            "Якщо не знаєш — введи '-')_"
        ),
    },
    526756037: {
        "sheet": "CycleTrackerWife",
        "relationship_q": "💬 Як стосунки з чоловіком сьогодні?",
        "cycle_q": (
            "📅 Де ти зараз по циклу?\n"
            "_(наприклад: '3 день місячних', '5 днів до місячних', 'овуляція'. "
            "Якщо не знаєш — введи '-')_"
        ),
    },
}

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def cfg(chat_id: int):
    return USERS.get(chat_id)

# ── FSM States ────────────────────────────────────────────────────────────────
class CheckIn(StatesGroup):
    mood              = State()
    mood_note         = State()
    health            = State()
    health_note       = State()
    relationship      = State()
    relationship_note = State()
    intimacy          = State()
    motivation        = State()
    motivation_note   = State()
    cycle_day         = State()
    notes             = State()

# ── Helpers ───────────────────────────────────────────────────────────────────
def score_keyboard(prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=str(i), callback_data=f"{prefix}:{i}")
        for i in range(1, 6)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])

def intimacy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Так — я ініціатор", callback_data="intimacy:me")],
        [InlineKeyboardButton(text="Так — не я ініціатор", callback_data="intimacy:partner")],
        [InlineKeyboardButton(text="Ні", callback_data="intimacy:no")],
    ])

LABELS = {1: "1 — дуже погано", 2: "2 — погано", 3: "3 — нормально",
          4: "4 — добре", 5: "5 — відмінно"}

INTIMACY_LABELS = {
    "me": "Так — я ініціатор",
    "partner": "Так — не я ініціатор",
    "no": "Ні",
}

NOTE_PROMPT = "_(коротко про причину, або '-' якщо нічого додати)_"

# ── Start ─────────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not cfg(message.chat.id):
        await message.answer(
            f"Цей чат ще не підключений.\nchat_id: {message.chat.id}"
        )
        return
    await message.answer(
        "👋 Привіт! Я твій щоденний трекер.\n\n"
        "Щовечора о 21:00 я буду питати про твій день.\n"
        "Запустити вручну — /checkin\n"
        "Переглянути останні записи — /last"
    )

# ── Manual trigger ────────────────────────────────────────────────────────────
@dp.message(F.text == "/checkin")
async def manual_checkin(message: Message, state: FSMContext):
    if not cfg(message.chat.id):
        return
    await start_checkin(message.chat.id, state)

# ── Scheduled trigger ─────────────────────────────────────────────────────────
async def scheduled_checkin():
    for chat_id in USERS:
        state = dp.fsm.get_context(bot, chat_id, chat_id)
        try:
            await start_checkin(chat_id, state)
        except Exception as e:
            logging.error(f"checkin failed for {chat_id}: {e}")

async def start_checkin(chat_id: int, state: FSMContext):
    await state.clear()
    await state.set_state(CheckIn.mood)
    await bot.send_message(
        chat_id,
        f"🌙 *Вечірній check-in* — {datetime.now().strftime('%d.%m.%Y')}\n\n"
        "😌 Який твій загальний настрій сьогодні?",
        parse_mode="Markdown",
        reply_markup=score_keyboard("mood")
    )

# ── MOOD ──────────────────────────────────────────────────────────────────────
@dp.callback_query(CheckIn.mood, F.data.startswith("mood:"))
async def q_mood(callback: CallbackQuery, state: FSMContext):
    score = int(callback.data.split(":")[1])
    await state.update_data(mood=score)
    await callback.message.edit_text(
        f"😌 Настрій: *{LABELS[score]}*", parse_mode="Markdown"
    )
    await state.set_state(CheckIn.mood_note)
    await callback.message.answer(f"Коротка нотатка про настрій?\n{NOTE_PROMPT}",
                                   parse_mode="Markdown")
    await callback.answer()

@dp.message(CheckIn.mood_note)
async def q_mood_note(message: Message, state: FSMContext):
    if not cfg(message.chat.id):
        return
    note = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(mood_note=note)
    await state.set_state(CheckIn.health)
    await message.answer("💪 Як самопочуття / здоров'я?",
                         reply_markup=score_keyboard("health"))

# ── HEALTH ────────────────────────────────────────────────────────────────────
@dp.callback_query(CheckIn.health, F.data.startswith("health:"))
async def q_health(callback: CallbackQuery, state: FSMContext):
    score = int(callback.data.split(":")[1])
    await state.update_data(health=score)
    await callback.message.edit_text(
        f"💪 Здоров'я: *{LABELS[score]}*", parse_mode="Markdown"
    )
    await state.set_state(CheckIn.health_note)
    await callback.message.answer(f"Коротка нотатка про здоров'я?\n{NOTE_PROMPT}",
                                   parse_mode="Markdown")
    await callback.answer()

@dp.message(CheckIn.health_note)
async def q_health_note(message: Message, state: FSMContext):
    conf = cfg(message.chat.id)
    if not conf:
        return
    note = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(health_note=note)
    await state.set_state(CheckIn.relationship)
    await message.answer(conf["relationship_q"],
                         reply_markup=score_keyboard("relationship"))

# ── RELATIONSHIP ──────────────────────────────────────────────────────────────
@dp.callback_query(CheckIn.relationship, F.data.startswith("relationship:"))
async def q_relationship(callback: CallbackQuery, state: FSMContext):
    score = int(callback.data.split(":")[1])
    await state.update_data(relationship=score)
    await callback.message.edit_text(
        f"💬 Стосунки: *{LABELS[score]}*", parse_mode="Markdown"
    )
    await state.set_state(CheckIn.relationship_note)
    await callback.message.answer(f"Коротка нотатка про стосунки?\n{NOTE_PROMPT}",
                                   parse_mode="Markdown")
    await callback.answer()

@dp.message(CheckIn.relationship_note)
async def q_relationship_note(message: Message, state: FSMContext):
    if not cfg(message.chat.id):
        return
    note = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(relationship_note=note)
    await state.set_state(CheckIn.intimacy)
    await message.answer("❤️ Чи був сьогодні секс?", reply_markup=intimacy_keyboard())

# ── INTIMACY ──────────────────────────────────────────────────────────────────
@dp.callback_query(CheckIn.intimacy, F.data.startswith("intimacy:"))
async def q_intimacy(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[1]
    await state.update_data(intimacy=INTIMACY_LABELS[key])
    await callback.message.edit_text(
        f"❤️ Секс сьогодні: *{INTIMACY_LABELS[key]}*", parse_mode="Markdown"
    )
    await state.set_state(CheckIn.motivation)
    await callback.message.answer("🔥 Мотивація на роботі?",
                                   reply_markup=score_keyboard("motivation"))
    await callback.answer()

# ── MOTIVATION ────────────────────────────────────────────────────────────────
@dp.callback_query(CheckIn.motivation, F.data.startswith("motivation:"))
async def q_motivation(callback: CallbackQuery, state: FSMContext):
    score = int(callback.data.split(":")[1])
    await state.update_data(motivation=score)
    await callback.message.edit_text(
        f"🔥 Мотивація: *{LABELS[score]}*", parse_mode="Markdown"
    )
    await state.set_state(CheckIn.motivation_note)
    await callback.message.answer(f"Коротка нотатка про мотивацію?\n{NOTE_PROMPT}",
                                   parse_mode="Markdown")
    await callback.answer()

@dp.message(CheckIn.motivation_note)
async def q_motivation_note(message: Message, state: FSMContext):
    conf = cfg(message.chat.id)
    if not conf:
        return
    note = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(motivation_note=note)
    await state.set_state(CheckIn.cycle_day)
    await message.answer(conf["cycle_q"], parse_mode="Markdown")

# ── CYCLE DAY ─────────────────────────────────────────────────────────────────
@dp.message(CheckIn.cycle_day)
async def q_cycle_day(message: Message, state: FSMContext):
    if not cfg(message.chat.id):
        return
    cycle = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(cycle_day=cycle)
    await state.set_state(CheckIn.notes)
    await message.answer(
        "📝 Загальна нотатка про день?\n"
        "_(що важливе сталось, або '-' якщо нічого)_",
        parse_mode="Markdown"
    )

# ── FINAL NOTES + SAVE ────────────────────────────────────────────────────────
@dp.message(CheckIn.notes)
async def q_notes(message: Message, state: FSMContext):
    conf = cfg(message.chat.id)
    if not conf:
        return
    notes = "" if message.text.strip() == "-" else message.text.strip()
    data = await state.get_data()
    await state.clear()

    row = {
        "date":              datetime.now().strftime("%Y-%m-%d"),
        "mood":              data.get("mood", ""),
        "mood_note":         data.get("mood_note", ""),
        "health":            data.get("health", ""),
        "health_note":       data.get("health_note", ""),
        "relationship":      data.get("relationship", ""),
        "relationship_note": data.get("relationship_note", ""),
        "intimacy":          data.get("intimacy", ""),
        "motivation":        data.get("motivation", ""),
        "motivation_note":   data.get("motivation_note", ""),
        "cycle_day":         data.get("cycle_day", ""),
        "notes":             notes,
    }

    try:
        sheets.append_row(conf["sheet"], row)
        await message.answer(
            "✅ *Збережено!*\n\n"
            f"😌 Настрій: {row['mood']}" + (f" — _{row['mood_note']}_" if row['mood_note'] else "") + "\n"
            f"💪 Здоров'я: {row['health']}" + (f" — _{row['health_note']}_" if row['health_note'] else "") + "\n"
            f"💬 Стосунки: {row['relationship']}" + (f" — _{row['relationship_note']}_" if row['relationship_note'] else "") + "\n"
            f"❤️ Секс: {row['intimacy']}\n"
            f"🔥 Мотивація: {row['motivation']}" + (f" — _{row['motivation_note']}_" if row['motivation_note'] else "") + "\n"
            f"📅 Цикл: {row['cycle_day'] or '—'}\n"
            f"📝 {row['notes'] or '—'}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"⚠️ Помилка збереження: {e}")
        logging.error(f"Sheets error: {e}")

# ── Last entries ──────────────────────────────────────────────────────────────
@dp.message(F.text == "/last")
async def cmd_last(message: Message):
    conf = cfg(message.chat.id)
    if not conf:
        return
    try:
        rows = sheets.get_last_rows(conf["sheet"], 7)
        if not rows:
            await message.answer("Записів ще немає.")
            return
        text = "📊 *Останні 7 днів:*\n\n"
        for r in rows:
            text += (
                f"*{r['date']}*\n"
                f"😌{r['mood']} 💪{r['health']} 💬{r['relationship']} 🔥{r['motivation']}"
                + (f"\n❤️ _{r.get('intimacy', '')}_" if r.get('intimacy') else "")
                + (f"\n📅 _{r.get('cycle_day', '')}_" if r.get('cycle_day') else "")
                + (f"\n_{r.get('notes', '')}_" if r.get('notes') else "")
                + "\n\n"
            )
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"⚠️ Помилка: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Helsinki")
    scheduler.add_job(scheduled_checkin, "cron",
                      hour=CHECKIN_HOUR, minute=CHECKIN_MINUTE)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
