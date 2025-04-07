import io
import os
from urllib.parse import urlparse
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from telethon import TelegramClient
from settings import settings
import mimetypes
import re

mimetypes.init()

async def get_posts(category_slug: str, per_page: int = 100) -> list:
	"""Retrieve posts from a specific category via the WordPress JSON API."""
	base_url = settings.BASE_URL
	posts = []

	async with aiohttp.ClientSession() as session:
		try:
			async with session.get(f"{base_url}/wp-json/wp/v2/categories", params={"slug": category_slug}) as resp:
				categories = await resp.json()
				if not categories or not categories[0].get('count', 0):
					return []

				category_id = categories[0]['id']
				total_posts = categories[0]['count']

			total_pages = (total_posts + per_page - 1) // per_page
			tasks = [
				session.get(f"{base_url}/wp-json/wp/v2/posts", params={
					"categories": category_id,
					"page": page,
					"per_page": per_page,
					"_fields": "id,title,content,excerpt,link,date"
				}) for page in range(1, total_pages + 1)
			]
			responses = await asyncio.gather(*tasks)

			for response in responses:
				if response.status == 200:
					posts.extend(await response.json())
				else:
					print(f"Failed to fetch page: {await response.text()}")

		except aiohttp.ClientError as e:
			print(f"Network error: {e}")
		except Exception as e:
			print(f"Unexpected error: {e}")

		return posts

async def get_full_post_content(post_url: str) -> str:
	"""Fetch and sanitize the full content of a post from its URL."""
	async with aiohttp.ClientSession() as session:
		try:
			async with session.get(post_url) as response:
				html = await response.text()
				soup = BeautifulSoup(html, 'html5lib')
				content_div = soup.find('div', class_='elementor-widget-theme-post-content')

				if content_div:
					widget_container = content_div.find('div', class_='elementor-widget-container')
					for element in widget_container.find_all(class_=['post-ser-css', 'mejs-container', 'wp-audio-shortcode']):
						element.decompose()
					for p in widget_container.find_all('p'):
						if not p.text.strip() or p.text.strip() == ' ':
							p.decompose()
					return str(widget_container)

				return "محتوا یافت نشد"
		except Exception as e:
			print(f"Error fetching {post_url}: {e}")
			return ""

async def download_to_bytesio(url: str, filename: str, chunk_size: int = 1024*1024) -> io.BytesIO | None:
	"""Download a file from a URL into a BytesIO buffer asynchronously."""
	async with aiohttp.ClientSession() as session:
		try:
			async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as response:
				if response.status != 200:
					return None
				file_buffer = io.BytesIO()
				async for chunk in response.content.iter_chunked(chunk_size):
					file_buffer.write(chunk)
				file_buffer.name = filename
				file_buffer.seek(0)
				return file_buffer
		except (aiohttp.ClientError, asyncio.TimeoutError) as e:
			print(f"Download error: {e}")
			return None
		except Exception as e:
			print(f"Unexpected error: {e}")
			return None

async def get_file_info(url: str) -> tuple[str, str, str] | None:
	"""Retrieve file metadata (URL, filename, content type) using a HEAD request."""
	async with aiohttp.ClientSession() as session:
		try:
			async with session.head(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
				if response.status != 200:
					return None
				content_type = response.headers.get('Content-Type', '')
				content_disp = response.headers.get('Content-Disposition', '')
				filename = next((part.split('=')[1].strip('"') for part in content_disp.split(';') if 'filename=' in part), None) or os.path.basename(urlparse(url).path)
				return url, filename, content_type
		except aiohttp.ClientError as e:
			print(f"Error checking {url}: {e}")
			return None

async def extract_filename(download_links: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
	"""Filter download links to retain only audio and video files."""
	filtered_links = []

	for url, filename, description in download_links:
		# Pre-filter using regex for allowed extensions
		allowed_extensions = r'\.(mp3|ogg|wav|mp4|mkv|avi)$'
		if not re.search(allowed_extensions, filename, re.IGNORECASE):
			continue

		# Validate with HEAD request and mimetypes
		file_info = await get_file_info(url)
		if not file_info:
			continue

		url, server_filename, content_type = file_info
		mime_type, _ = mimetypes.guess_type(filename)

		if (mime_type and ('audio' in mime_type or 'video' in mime_type)) or 'audio' in content_type or 'video' in content_type:
			filtered_links.append((url, filename, description))

	return filtered_links

async def check_user_membership(client: TelegramClient, user_id: int) -> bool:
	"""Verify if a user is a member of the specified Telegram channel."""
	try:
		print(f"Checking membership for user {user_id} in channel {settings.CHANNEL_USERNAME}")
		async for participant in client.iter_participants(settings.CHANNEL_USERNAME, limit=2500):
			if participant.id == user_id:
				print(f"Membership result: True (user {user_id} found in channel)")
				return True
		print(f"Membership result: False (user {user_id} not found in channel)")
		return False
	except Exception as e:
		if "Chat admin privileges are required" in str(e):
			print(f"Error: Bot needs admin privileges in {settings.CHANNEL_USERNAME} to check membership!")
		else:
			print(f"Error checking membership for user {user_id}: {e}")
		return False