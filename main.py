import os
import asyncio
from telethon import TelegramClient, events, Button
from settings import settings
from utils import get_posts, get_full_content, download_to_bytesio, filter_links, check_user_membership, extract_download_links

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
	"کتاب‌های درسی": {
		"کتاب‌های درسی تمام پایه‌های تحصیلی": "کتابهای-درسی-تمام-پایههای-تحصیلی",
		"نسخه PDF کتاب‌های درسی سال 1401-1402": "نسخه-pdf-کتاب-های-درسی-سال-1401-1402"
	}
}

# User state management (in-memory for now)
user_states = {}

async def handle_message(event):
	"""Handle incoming messages based on the user's current state."""
	chat_id = event.chat_id
	user_id = event.sender_id

	if event.text == "/start":
		user_states[chat_id] = {"state": "category_selection"}
		buttons = [[Button.text(name)] for name in CATEGORIES.keys()]
		await event.respond("لطفاً یک دسته‌بندی انتخاب کنید:", buttons=buttons)
		return

	if event.text == "/cancel":
		user_states.pop(chat_id, None)
		await event.respond("عملیات لغو شد. برای شروع مجدد از /start استفاده کنید.")
		return

	if chat_id not in user_states:
		user_states[chat_id] = {"state": "category_selection"}
		buttons = [[Button.text(name)] for name in CATEGORIES.keys()]
		await event.respond("لطفاً یک دسته‌بندی انتخاب کنید:", buttons=buttons)
		return

	is_member = await check_user_membership(client, user_id)
	if not is_member:
		user_states[chat_id]["previous_state"] = user_states[chat_id].get("state", "category_selection")
		user_states[chat_id]["state"] = "awaiting_membership"
		await event.respond(
			f"شما عضو کانال {settings.CHANNEL_USERNAME} نیستید. لطفاً ابتدا عضو شوید.",
			buttons=[Button.inline("بررسی عضویت", b"check_membership")]
		)
		return

	current_state = user_states[chat_id]["state"]

	if current_state == "category_selection":
		category_name = event.text.strip()
		if category_name not in CATEGORIES:
			await event.respond("لطفاً یک دسته‌بندی معتبر انتخاب کنید.")
			return

		if isinstance(CATEGORIES[category_name], dict):
			user_states[chat_id]["state"] = "subcategory_selection"
			user_states[chat_id]["category"] = category_name
			subcategories = CATEGORIES[category_name]
			buttons = [[Button.text(sub_name)] for sub_name in subcategories.keys()]
			await event.respond("لطفاً یک زیر‌دسته انتخاب کنید:", buttons=buttons)
		else:
			user_states[chat_id]["state"] = "post_selection"
			user_states[chat_id]["category"] = CATEGORIES[category_name]
			posts = await get_posts(CATEGORIES[category_name])
			print(f"Retrieved {len(posts)} posts for category: {category_name}")

			if not posts:
				await event.respond("هیچ پستی در این دسته‌بندی یافت نشد.")
				user_states.pop(chat_id, None)
				return

			user_states[chat_id]["posts"] = posts
			buttons = [[Button.text(f"{i+1}. {p['title']['rendered']}")] for i, p in enumerate(posts)]
			await event.respond("لطفاً یک پست انتخاب کنید:", buttons=buttons)

	elif current_state == "subcategory_selection":
		category_name = user_states[chat_id]["category"]
		subcategory_name = event.text.strip()
		if subcategory_name not in CATEGORIES[category_name]:
			await event.respond("لطفاً یک زیر‌دسته معتبر انتخاب کنید.")
			return

		user_states[chat_id]["subcategory"] = subcategory_name
		posts = await get_posts(CATEGORIES[category_name][subcategory_name])
		print(f"Retrieved {len(posts)} posts for subcategory: {subcategory_name}")

		if not posts:
			await event.respond("هیچ پستی در این زیر‌دسته یافت نشد.")
			user_states.pop(chat_id, None)
			return

		content, items = await get_full_content(posts[0]["link"], is_textbook=True)
		if not items:
			await event.respond("هیچ فایل دانلودی در این زیر‌دسته یافت نشد.")
			user_states.pop(chat_id, None)
			return

		user_states[chat_id]["items"] = items
		if subcategory_name == "کتاب‌های درسی تمام پایه‌های تحصیلی":
			user_states[chat_id]["state"] = "textbook_selection"
			buttons = [[Button.text(item["title"])] for item in items]
			await event.respond("لطفاً یک پایه تحصیلی انتخاب کنید:", buttons=buttons)
		else:
			user_states[chat_id]["state"] = "textbook_book_selection"
			user_states[chat_id]["selected_item"] = {"title": subcategory_name, "links": [link for item in items for link in item["links"]]}
			buttons = [[Button.text(link["description"] or link["filename"])] for link in user_states[chat_id]["selected_item"]["links"]]
			await event.respond("لطفاً یک فایل انتخاب کنید:", buttons=buttons)

	elif current_state == "textbook_selection":
		selected_title = event.text.strip()
		items = user_states[chat_id]["items"]
		selected_item = next((item for item in items if item["title"] == selected_title), None)

		if not selected_item or not selected_item["links"]:
			await event.respond("هیچ فایل دانلودی برای این پایه تحصیلی یافت نشد.")
			return

		user_states[chat_id]["state"] = "textbook_book_selection"
		user_states[chat_id]["selected_item"] = selected_item
		buttons = [[Button.text(link["description"] or link["filename"])] for link in selected_item["links"]]
		await event.respond("لطفاً یک کتاب انتخاب کنید:", buttons=buttons)

	elif current_state == "textbook_book_selection":
		selected_desc = event.text.strip()
		selected_item = user_states[chat_id]["selected_item"]
		selected_link = next((link for link in selected_item["links"] if (link["description"] or link["filename"]) == selected_desc), None)

		if not selected_link:
			await event.respond("هیچ فایلی برای این انتخاب یافت نشد.")
			return

		download_links = [(selected_link["href"], selected_link["filename"], selected_link["description"])]
		filtered_links = await filter_links(download_links)

		if not filtered_links:
			await event.respond("فایل انتخاب‌شده معتبر نیست.")
			return

		status_msg = await event.respond("در حال پردازش فایل... لطفاً منتظر بمانید ⏳")
		url, filename, description = filtered_links[0]
		file_buffer = await download_to_bytesio(url, filename)
		if file_buffer:
			caption = description or filename
			await client.send_file(chat_id, file_buffer, caption=caption)
			await client.edit_message(chat_id, status_msg.id, "فایل با موفقیت ارسال شد ✅")
		else:
			await client.edit_message(chat_id, status_msg.id, "خطا در دانلود فایل!")

		buttons = [[Button.text(link["description"] or link["filename"])] for link in selected_item["links"]]
		await event.respond("لطفاً یک کتاب دیگر انتخاب کنید یا برای بازگشت به صفحه اصلی از /start استفاده کنید:", buttons=buttons)

	elif current_state == "post_selection":
		try:
			post_index = int(event.text.strip().split(". ")[0]) - 1
			selected_post = user_states[chat_id]["posts"][post_index]
			content, _ = await get_full_content(selected_post['link'], is_textbook=False)

			download_links = await extract_download_links(content)
			if not download_links:
				await event.respond("هیچ لینک قابل دانلودی در این پست یافت نشد.")
				user_states.pop(chat_id, None)
				return

			filtered_links = await filter_links(download_links)
			if not filtered_links:
				await event.respond("هیچ فایل معتبری در این پست یافت نشد.")
				user_states.pop(chat_id, None)
				return

			status_msg = await event.respond(f"در حال پردازش {len(filtered_links)} فایل... لطفاً منتظر بمانید ⏳")
			sent_files = 0

			for idx, (url, filename, description) in enumerate(filtered_links):
				file_buffer = await download_to_bytesio(url, filename)
				if file_buffer:
					caption = f"{description} ({idx + 1} از {len(filtered_links)})" if description else f"فایل {idx + 1} از {len(filtered_links)}"
					await client.send_file(chat_id, file_buffer, caption=caption)
					sent_files += 1
				await asyncio.sleep(1)

			await client.edit_message(chat_id, status_msg.id, f"{sent_files} از {len(filtered_links)} فایل با موفقیت ارسال شد ✅")
			buttons = [[Button.text(f"{i+1}. {p['title']['rendered']}")] for i, p in enumerate(user_states[chat_id]["posts"])]
			await event.respond("لطفاً یک پست دیگر انتخاب کنید یا برای بازگشت به صفحه اصلی از /start استفاده کنید:", buttons=buttons)

		except (ValueError, IndexError):
			await event.respond("لطفاً شماره پست معتبری انتخاب کنید.")
		except Exception as e:
			print(f"Error processing post: {e}")
			await event.respond("خطایی در پردازش درخواست شما رخ داد.")
			user_states.pop(chat_id, None)

async def handle_inline(event):
	"""Handle inline button clicks for membership verification."""
	user_id = event.sender_id
	chat_id = event.chat_id

	if event.data == b"check_membership":
		if await check_user_membership(client, user_id):
			previous_state = user_states[chat_id].get("previous_state", "category_selection")
			user_states[chat_id]["state"] = previous_state

			if previous_state == "category_selection":
				buttons = [[Button.text(name)] for name in CATEGORIES.keys()]
				await event.respond("عضویت شما تأیید شد! لطفاً یک دسته‌بندی انتخاب کنید:", buttons=buttons)
			elif previous_state == "subcategory_selection":
				category_name = user_states[chat_id]["category"]
				subcategories = CATEGORIES[category_name]
				buttons = [[Button.text(sub_name)] for sub_name in subcategories.keys()]
				await event.respond("عضویت شما تأیید شد! لطفاً یک زیر‌دسته انتخاب کنید:", buttons=buttons)
			elif previous_state == "textbook_selection":
				items = user_states[chat_id].get("items", [])
				buttons = [[Button.text(item["title"])] for item in items]
				await event.respond("عضویت شما تأیید شد! لطفاً یک پایه تحصیلی انتخاب کنید:", buttons=buttons)
			elif previous_state == "textbook_book_selection":
				selected_item = user_states[chat_id].get("selected_item", {})
				buttons = [[Button.text(link["description"] or link["filename"])] for link in selected_item["links"]]
				await event.respond("عضویت شما تأیید شد! لطفاً یک کتاب انتخاب کنید:", buttons=buttons)
			elif previous_state == "post_selection":
				posts = user_states[chat_id].get("posts", [])
				buttons = [[Button.text(f"{i+1}. {p['title']['rendered']}")] for i, p in enumerate(posts)]
				await event.respond("عضویت شما تأیید شد! لطفاً یک پست انتخاب کنید:", buttons=buttons)
		else:
			await event.answer("شما هنوز عضو کانال نیستید. لطفاً ابتدا به کانال بپیوندید.")

# Register event handlers
client.on(events.NewMessage)(handle_message)
client.on(events.CallbackQuery)(handle_inline)

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