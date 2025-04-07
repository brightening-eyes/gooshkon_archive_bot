import os
import asyncio
from telethon import TelegramClient, events, Button
from settings import settings
from utils import get_posts, get_full_post_content, download_to_bytesio, get_file_info, extract_filename, check_user_membership
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse

# Telegram client setup
api_id = settings.API_ID
api_hash = settings.API_HASH
bot_token = settings.BOT_TOKEN
client = TelegramClient("bot_session", api_id, api_hash)

# Category definitions
CATEGORIES = {
	"سینمایی خارجی": "سینمایی-خارجی",
	"سینمایی ایرانی": "سینمایی-ایرانی",
	"سریال خارجی": "سریال-خارجی",
	"سریال ایرانی": "سریال-ایرانی",
	"انیمیشن": "انیمیشن",
	"مستند و گزارش": "مستند-و-گزارش"
}

# User state management (in-memory for now)
user_states = {}

async def handle_message(event):
	"""Process incoming messages based on the user's current state."""
	chat_id = event.chat_id
	user_id = event.sender_id

	# Handle /start command
	if event.text == "/start":
		is_member = await check_user_membership(client, user_id)
		if is_member:
			user_states[chat_id] = {"state": "category_selection"}
			buttons = [[Button.text(name)] for name in CATEGORIES.keys()]
			await event.respond("لطفاً یک دسته‌بندی انتخاب کنید:", buttons=buttons)
		else:
			user_states[chat_id] = {"state": "awaiting_membership"}
			await event.respond(
				f"لطفاً برای استفاده از ربات در کانال {settings.CHANNEL_USERNAME} عضو شوید.",
				buttons=[Button.inline("بررسی عضویت", b"check_membership")]
			)
		return

	# Handle /cancel command
	if event.text == "/cancel":
		user_states.pop(chat_id, None)
		await event.respond("عملیات لغو شد. برای شروع مجدد از /start استفاده کنید.")
		return

	# Check if user has a state
	if chat_id not in user_states:
		is_member = await check_user_membership(client, user_id)
		if is_member:
			user_states[chat_id] = {"state": "category_selection"}
			buttons = [[Button.text(name)] for name in CATEGORIES.keys()]
			await event.respond("لطفاً یک دسته‌بندی انتخاب کنید:", buttons=buttons)
		else:
			user_states[chat_id] = {"state": "awaiting_membership"}
			await event.respond(
				f"لطفاً برای استفاده از ربات در کانال {settings.CHANNEL_USERNAME} عضو شوید.",
				buttons=[Button.inline("بررسی عضویت", b"check_membership")]
			)
		return

	# Check membership before processing any state
	is_member = await check_user_membership(client, user_id)
	if not is_member:
		user_states[chat_id]["previous_state"] = user_states[chat_id].get("state", "category_selection")
		user_states[chat_id]["state"] = "awaiting_membership"
		await event.respond(
			f"شما دیگر عضو کانال {settings.CHANNEL_USERNAME} نیستید. لطفاً مجدداً عضو شوید تا ادامه دهید.",
			buttons=[Button.inline("بررسی عضویت", b"check_membership")]
		)
		return

	current_state = user_states[chat_id]["state"]

	# Category selection state
	if current_state == "category_selection":
		category_name = event.text.strip()
		if category_name not in CATEGORIES:
			await event.respond("لطفاً یک دسته‌بندی معتبر از گزینه‌های موجود انتخاب کنید.")
			return

		user_states[chat_id]["category"] = CATEGORIES[category_name]
		user_states[chat_id]["state"] = "post_selection"
		posts = await get_posts(CATEGORIES[category_name])
		print(f"Retrieved {len(posts)} posts for category: {category_name}")

		if not posts:
			user_states.pop(chat_id, None)
			await event.respond("هیچ پستی در این دسته‌بندی یافت نشد.")
			return

		user_states[chat_id]["posts"] = posts
		buttons = [[Button.text(f"{i+1}. {p['title']['rendered']}")] for i, p in enumerate(posts)]
		await event.respond("لطفاً یک پست انتخاب کنید:", buttons=buttons)

	# Post selection state
	elif current_state == "post_selection":
		try:
			post_index = int(event.text.strip().split(". ")[0]) - 1
			selected_post = user_states[chat_id]["posts"][post_index]
			full_content = await get_full_post_content(selected_post['link'])

			soup = BeautifulSoup(full_content, 'html.parser')
			# Extract links as triplets (URL, filename, description)
			download_links = []
			allowed_extensions = r'\.(mp3|ogg|wav|mp4|mkv|avi)$'
			for a in soup.find_all('a', href=True):
				href = a['href']
				if href.startswith(('http://', 'https://')) and '#' not in href:
					filename = os.path.basename(urlparse(href).path)
					description = a.text.strip() or ""
					if re.search(allowed_extensions, href, re.IGNORECASE):
						download_links.append((href, filename, description))

			if not download_links:
				await event.respond("هیچ لینک قابل دانلودی در این پست یافت نشد.")
				user_states.pop(chat_id, None)
				return

			# Filter audio and video links
			print(f"Filtering {len(download_links)} download links for media files")
			filtered_links = await extract_filename(download_links)
			if not filtered_links:
				await event.respond("هیچ فایل رسانه‌ای معتبری در این پست یافت نشد.")
				user_states.pop(chat_id, None)
				return

			# Process and send files
			status_msg = await event.respond(f"در حال پردازش {len(filtered_links)} فایل رسانه‌ای... لطفاً منتظر بمانید ⏳")
			sent_files = 0

			for idx, (url, filename, description) in enumerate(filtered_links):
				try:
					file_buffer = await download_to_bytesio(url, filename)
					if file_buffer:
						caption = f"{description} ({idx + 1} از {len(filtered_links)})" if description else f"فایل {idx + 1} از {len(filtered_links)}"
						await client.send_file(chat_id, file_buffer, caption=caption)
						sent_files += 1
					await asyncio.sleep(1)
				except Exception as e:
					print(f"Error sending file {url}: {e}")

			await client.edit_message(chat_id, status_msg.id, f"{sent_files} از {len(filtered_links)} فایل با موفقیت ارسال شد ✅")
			print(f"Completed sending {sent_files} out of {len(filtered_links)} files")
			user_states.pop(chat_id, None)
			await event.respond("برای انتخاب دسته‌بندی جدید از /start استفاده کنید.")

		except (ValueError, IndexError):
			await event.respond("لطفاً شماره پست معتبری انتخاب کنید.")
		except Exception as e:
			print(f"Error processing post: {e}")
			user_states.pop(chat_id, None)
			await event.respond("خطایی در پردازش درخواست شما رخ داد.")

async def handle_inline(event):
	"""Handle inline button clicks."""
	user_id = event.sender_id
	chat_id = event.chat_id

	if event.data == b"check_membership":
		if await check_user_membership(client, user_id):
			previous_state = user_states[chat_id].get("previous_state", "category_selection")
			user_states[chat_id]["state"] = previous_state

			if previous_state == "category_selection":
				buttons = [[Button.text(name)] for name in CATEGORIES.keys()]
				await event.respond("عضویت شما تأیید شد! لطفاً یک دسته‌بندی انتخاب کنید:", buttons=buttons)
			elif previous_state == "post_selection":
				posts = user_states[chat_id].get("posts", [])
				if not posts:
					user_states[chat_id]["state"] = "category_selection"
					buttons = [[Button.text(name)] for name in CATEGORIES.keys()]
					await event.respond("عضویت شما تأیید شد! لطفاً یک دسته‌بندی انتخاب کنید:", buttons=buttons)
				else:
					buttons = [[Button.text(f"{i+1}. {p['title']['rendered']}")] for i, p in enumerate(posts)]
					await event.respond("عضویت شما تأیید شد! لطفاً یک پست انتخاب کنید:", buttons=buttons)
		else:
			await event.answer("شما هنوز عضو کانال نیستید. لطفاً ابتدا به کانال بپیوندید.")

# Register event handlers
client.on(events.NewMessage)(handle_message)
client.on(events.CallbackQuery)(handle_inline)

# Main execution
async def main():
	"""Initialize and run the Telegram client until disconnected."""
	print("Starting bot...")
	await client.start(bot_token=bot_token)
	print("Bot started successfully!")
	await client.run_until_disconnected()

if __name__ == "__main__":
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		print("Bot stopped by user.")