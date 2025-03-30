import asyncio
from fastapi import FastAPI, HTTPException
import uvicorn
import telebot
from telebot import types
from telebot.async_telebot import AsyncTeleBot
from telebot import asyncio_filters
from telebot.asyncio_storage import StateMemoryStorage
from telebot.asyncio_handler_backends import State, StatesGroup
from telebot.states.asyncio.context import StateContext
from telebot.states.asyncio.middleware import StateMiddleware
from bs4 import BeautifulSoup
from utils import get_posts, get_full_post_content, download_to_bytesio
from settings import settings

app = FastAPI(docs=None, redoc_url=None)
bot = AsyncTeleBot(f'{settings.BOT_TOKEN}', state_storage=StateMemoryStorage())

@app.post(f'/{settings.BOT_TOKEN}')
async def process_webhook(update: dict):
	if update:
		update = telebot.types.Update.de_json(update)
		await bot.process_new_updates([update])
	return

class PostStates(StatesGroup):
	category_selection = State()
	post_selection = State()

# Predefined categories mapping
CATEGORIES = {
"سینمایی خارجی": "سینمایی-خارجی",
"سینمایی ایرانی": "سینمایی-ایرانی",
"سریال خارجی": "سریال-خارجی",
"سریال ایرانی": "سریال-ایرانی",
"انیمیشن": "انیمیشن",
"مستند و گزارش": "مستند-و-گزارش"
}

# Start command handler
@bot.message_handler(commands=["start"])
async def start_command(message: types.Message, state: StateContext):
	await state.set(PostStates.category_selection)
	markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
	buttons = [types.KeyboardButton(name) for name in CATEGORIES.keys()]
	markup.add(*buttons)
	await bot.send_message(message.chat.id, "لطفا یک دسته‌بندی انتخاب کنید:", reply_markup=markup, reply_parameters=types.ReplyParameters(message_id=message.message_id))

# Cancel command handler
@bot.message_handler(state="*", commands=["cancel"])
async def cancel_command(message: types.Message, state: StateContext):
	await state.delete()
	await bot.send_message(message.chat.id, "عملیات کنسل شد. برای شروع مجدد /start را بزنید.", reply_parameters=types.ReplyParameters(message_id=message.message_id))

# Category selection handler
@bot.message_handler(state=PostStates.category_selection)
async def handle_category(message: types.Message, state: StateContext):
	category_name = message.text.strip()
	if category_name not in CATEGORIES:
		await bot.send_message(message.chat.id, "لطفا از گزینه‌های موجود انتخاب کنید")
		return

	await state.add_data(category_slug=CATEGORIES[category_name])
	posts = await get_posts(CATEGORIES[category_name])

	if not posts:
		await state.delete()
		await bot.send_message(message.chat.id, "پستی در این دسته‌بندی یافت نشد")
		return
    
	await state.set(PostStates.post_selection)
	await state.add_data(posts=posts)  # Store posts
    
	markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
	buttons = [types.KeyboardButton(f"{i+1}. {p['title']['rendered']}") for i, p in enumerate(posts)]
	markup.add(*buttons)
	await bot.send_message(message.chat.id, "لطفا یک پست را انتخاب کنید:", reply_markup=markup, reply_parameters=types.ReplyParameters(message_id=message.message_id))

# Post selection handler - modified to send files immediately
@bot.message_handler(state=PostStates.post_selection)
async def handle_post(message: types.Message, state: StateContext):
	try:
		async with state.data() as data:
			posts = data['posts']
			post_index = int(message.text.strip().split('. ')[0]) - 1
			selected_post = posts[post_index]
		# Get full content and extract links with descriptions
		full_content = await get_full_post_content(selected_post['link'])
		soup = BeautifulSoup(full_content, 'html.parser')
		# Extract links with their text descriptions
		download_links = []
		for a in soup.find_all('a', href=True):
			description = a.text.strip() or ""
			download_links.append((a['href'], description))
        
		if len(download_links) == 0:
			await bot.send_message(message.chat.id, "لینک قابل دانلودی یافت نشد")
			await state.delete()
			return
        
		# Send downloading status
		status_msg = await bot.send_message(message.chat.id, f"در حال دریافت {len(download_links)} فایل... لطفا منتظر بمانید⏳")
		# Process and send all files
		sent_files = 0
		for idx, (url, description) in enumerate(download_links):
			try:
				file_buffer = await download_to_bytesio(url)
				if file_buffer:
					await bot.send_document(message.chat.id, file_buffer, caption=f"{description}\n({idx + 1} از {len(download_links)})", reply_parameters=types.ReplyParameters(message_id=status_msg.message_id))
					sent_files += 1
				# Add small delay between sends to avoid rate limits
				await asyncio.sleep(1)
			except Exception as e:
				print(f"Error sending file {url}: {e}")
        
		# Update status message
		await bot.edit_message_text(f"تعداد {sent_files} از {len(download_links)} فایل با موفقیت ارسال شدند ✅", message.chat.id, status_msg.message_id)
        
	except (ValueError, IndexError):
		await bot.send_message(message.chat.id, "لطفا از گزینه‌های موجود انتخاب کنید")
	except Exception as e:
		print(e)
		await bot.send_message(message.chat.id, "خطایی در پردازش پست رخ داد")
	finally:
		await state.delete()
		await bot.send_message(message.chat.id, "برای انتخاب دسته‌بندی جدید /start را بزنید.", reply_markup=types.ReplyKeyboardRemove())

if __name__ == '__main__':
	bot.add_custom_filter(asyncio_filters.StateFilter(bot))
	bot.setup_middleware(StateMiddleware(bot))
	asyncio.run(bot.polling())
	#bot.remove_webhook()
	#bot.set_webhook(url=f'https://{settings.WEBHOOK_HOST}/{settings.BOT_TOKEN}')
	#uvicorn.run(app, host='0.0.0.0', port=settings.WEBHOOK_PORT)
