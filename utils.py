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

async def get_full_content(post_url: str, is_textbook: bool = False) -> tuple[str, list]:
	"""Fetch full content of a post, with special handling for textbooks."""
	async with aiohttp.ClientSession() as session:
		try:
			async with session.get(post_url) as response:
				html = await response.text()
				soup = BeautifulSoup(html, 'html5lib')

				if is_textbook:
					body = soup.find('body')
					if not body:
						return "محتوا یافت نشد", []

					items = []
					current_header = None
					seen_links = set()
					for elem in body.find_all(['h2', 'p', 'a'], recursive=True):
						if elem.name == 'h2':
							current_header = elem.get_text(strip=True)
							items.append({"title": current_header, "links": []})
						elif elem.name == 'a' and current_header:
							href = elem.get('href', '')
							description = elem.get_text(strip=True) or ""
							if (href.startswith(('http://', 'https://')) and 
								('/scb/' in href or href.endswith(('.zip', '.rar'))) and 
								'wp-' not in href and 'login' not in href and 'admin' not in href):
								filename = os.path.basename(urlparse(href).path)
								link_key = (href, description)
								if link_key not in seen_links:
									seen_links.add(link_key)
									items[-1]["links"].append({"href": href, "filename": filename, "description": description})
						elif elem.name == 'p' and elem.find('a'):
							for a in elem.find_all('a'):
								href = a.get('href', '')
								description = a.get_text(strip=True) or ""
								if (href.startswith(('http://', 'https://')) and 
									('/scb/' in href or href.endswith(('.zip', '.rar'))) and 
									'wp-' not in href and 'login' not in href and 'admin' not in href):
									filename = os.path.basename(urlparse(href).path)
									link_key = (href, description)
									if link_key not in seen_links:
										seen_links.add(link_key)
										if current_header:
											items[-1]["links"].append({"href": href, "filename": filename, "description": description})
										else:
											items.append({"title": description, "links": [{"href": href, "filename": filename, "description": description}]})

					filtered_items = [item for item in items if item["links"]]
					return "", filtered_items if filtered_items else []
				else:
					content_div = soup.find('div', class_='elementor-widget-theme-post-content')
					if not content_div:
						return "محتوا یافت نشد", []

					widget_container = content_div.find('div', class_='elementor-widget-container') or content_div
					for element in widget_container.find_all(class_=['post-ser-css', 'mejs-container', 'wp-audio-shortcode']):
						element.decompose()
					for p in widget_container.find_all('p'):
						if not p.text.strip() or p.text.strip() == ' ':
							p.decompose()
					return str(widget_container), []

		except Exception as e:
			print(f"Error fetching {post_url}: {e}")
			return "", []

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

async def extract_filename(url: str) -> tuple[str, str, str] | None:
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

async def filter_links(download_links: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
	"""Filter download links to retain only audio, video, or archive files."""
	filtered_links = []

	for url, filename, description in download_links:
		allowed_extensions = r'\.(mp3|ogg|wav|mp4|mkv|avi|rar|zip)$'
		if not re.search(allowed_extensions, filename, re.IGNORECASE):
			continue

		file_info = await extract_filename(url)
		if not file_info:
			continue

		url, server_filename, content_type = file_info
		mime_type, _ = mimetypes.guess_type(filename)

		if (mime_type and ('audio' in mime_type or 'video' in mime_type or 'zip' in mime_type or 'rar' in mime_type)) or 'audio' in content_type or 'video' in content_type or 'zip' in content_type or 'rar' in content_type:
			filtered_links.append((url, filename, description))

	return filtered_links

async def check_user_membership(client: TelegramClient, user_id: int) -> bool:
	"""Verify if a user is a member of the specified Telegram channel."""
	try:
		print(f"Checking membership for user {user_id} in channel {settings.CHANNEL_USERNAME}")
		async for participant in client.iter_participants(settings.CHANNEL_USERNAME):
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

async def extract_download_links(post_content: str) -> list[tuple[str, str, str]]:
	"""Extract download links and descriptions from post content."""
	soup = BeautifulSoup(post_content, 'html5lib')
	download_links = []
	allowed_extensions = r'\.(mp3|ogg|wav|mp4|mkv|avi|rar|zip)$'
	for a in soup.find_all('a', href=True):
		href = a['href']
		if href.startswith(('http://', 'https://')) and '#' not in href:
			filename = os.path.basename(urlparse(href).path)
			description = a.text.strip() or ""
			if re.search(allowed_extensions, href, re.IGNORECASE):
				download_links.append((href, filename, description))
	return download_links