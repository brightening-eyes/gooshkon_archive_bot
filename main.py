import asyncio
from fastapi import FastAPI, HTTPException
import uvicorn
from telethon import TelegramClient, events, Button
from settings import settings
from utils import get_posts, get_full_post_content, download_to_bytesio

app = FastAPI(docs=None, redoc_url=None)

# تنظیمات کلاینت تلگرام
api_id = int(settings.API_ID)  # مقدار API_ID را از env بخوانید
api_hash = settings.API_HASH   # مقدار API_HASH را از env بخوانید
bot_token = settings.BOT_TOKEN

client = TelegramClient("bot_session", api_id, api_hash).start(bot_token=bot_token)

# لیست دسته‌بندی‌ها
CATEGORIES = {
    "سینمایی خارجی": "سینمایی-خارجی",
    "سینمایی ایرانی": "سینمایی-ایرانی",
    "سریال خارجی": "سریال-خارجی",
    "سریال ایرانی": "سریال-ایرانی",
    "انیمیشن": "انیمیشن",
    "مستند و گزارش": "مستند-و-گزارش"
}

# مدیریت وضعیت کاربران
user_states = {}

# دستور `/start`
@client.on(events.NewMessage(pattern="/start"))
async def start_command(event):
    chat_id = event.chat_id
    user_states[chat_id] = {"state": "category_selection"}

    buttons = [[Button.text(name)] for name in CATEGORIES.keys()]
    await event.respond("لطفا یک دسته‌بندی انتخاب کنید:", buttons=buttons)

# لغو عملیات با `/cancel`
@client.on(events.NewMessage(pattern="/cancel"))
async def cancel_command(event):
    chat_id = event.chat_id
    user_states.pop(chat_id, None)
    await event.respond("عملیات کنسل شد. برای شروع مجدد /start را بزنید.")

# مدیریت انتخاب دسته‌بندی
@client.on(events.NewMessage)
async def handle_category(event):
    chat_id = event.chat_id
    if chat_id not in user_states or user_states[chat_id]["state"] != "category_selection":
        return

    category_name = event.text.strip()
    if category_name not in CATEGORIES:
        await event.respond("لطفا از گزینه‌های موجود انتخاب کنید")
        return

    user_states[chat_id]["category"] = CATEGORIES[category_name]
    user_states[chat_id]["state"] = "post_selection"

    posts = await get_posts(CATEGORIES[category_name])
    if not posts:
        user_states.pop(chat_id, None)
        await event.respond("پستی در این دسته‌بندی یافت نشد")
        return

    user_states[chat_id]["posts"] = posts
    buttons = [[Button.text(f"{i+1}. {p['title']['rendered']}")] for i, p in enumerate(posts)]
    await event.respond("لطفا یک پست را انتخاب کنید:", buttons=buttons)

# مدیریت انتخاب پست و ارسال فایل‌ها
@client.on(events.NewMessage)
async def handle_post(event):
    chat_id = event.chat_id
    if chat_id not in user_states or user_states[chat_id]["state"] != "post_selection":
        return

    try:
        post_index = int(event.text.strip().split(". ")[0]) - 1
        selected_post = user_states[chat_id]["posts"][post_index]

        full_content = await get_full_post_content(selected_post['link'])
        soup = BeautifulSoup(full_content, 'html.parser')

        # استخراج لینک‌های دانلود
        download_links = [(a['href'], a.text.strip() or "") for a in soup.find_all('a', href=True)]
        if not download_links:
            await event.respond("لینک قابل دانلودی یافت نشد")
            user_states.pop(chat_id, None)
            return

        # ارسال وضعیت دانلود
        status_msg = await event.respond(f"در حال دریافت {len(download_links)} فایل... لطفا منتظر بمانید ⏳")

        sent_files = 0
        for idx, (url, description) in enumerate(download_links):
            try:
                file_buffer = await download_to_bytesio(url)
                if file_buffer:
                    await client.send_file(chat_id, file_buffer, caption=f"{description}\n({idx + 1} از {len(download_links)})")
                    sent_files += 1
                await asyncio.sleep(1)  # جلوگیری از بلاک شدن
            except Exception as e:
                print(f"Error sending file {url}: {e}")

        await client.edit_message(chat_id, status_msg.id, f"تعداد {sent_files} از {len(download_links)} فایل با موفقیت ارسال شدند ✅")

    except (ValueError, IndexError):
        await event.respond("لطفا از گزینه‌های موجود انتخاب کنید")
    except Exception as e:
        print(e)
        await event.respond("خطایی در پردازش پست رخ داد")
    finally:
        user_states.pop(chat_id, None)
        await event.respond("برای انتخاب دسته‌بندی جدید /start را بزنید.")

# اجرای وب‌هوک (اختیاری)
@app.post(f'/{settings.BOT_TOKEN}')
async def process_webhook(update: dict):
    try:
        await client.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(client.run_until_disconnected())

    # برای اجرای وب‌هوک به جای polling
    # uvicorn.run(app, host='0.0.0.0', port=settings.WEBHOOK_PORT)
