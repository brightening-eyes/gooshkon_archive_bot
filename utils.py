import io
import os
from urllib.parse import urlparse
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from settings import settings

async def get_posts(category_slug: str, per_page: int = 100) -> list:
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
			tasks = []
			for page in range(1, total_pages + 1):
				tasks.append(session.get(f"{base_url}/wp-json/wp/v2/posts", params={
"categories": category_id,
"page": page,
"per_page": per_page,
"_fields": "id,title,content,excerpt,link,date"}))
			responses = await asyncio.gather(*tasks)            
			for response in responses:
				if response.status == 200:
					posts.extend(await response.json())
				else:
					print(f"Failed to fetch page: {await response.text()}")

		except aiohttp.ClientError as e:
			print(f"Network error: {str(e)}")
		except Exception as e:
			print(f"Unexpected error: {str(e)}")

	return posts

async def get_full_post_content(post_url: str) -> str:
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
						if not p.text.strip() or p.text.strip() == '&nbsp;':
							p.decompose()
                
					return str(widget_container)

				return "Content not found"
		except Exception as e:
			print(f"Error fetching {post_url}: {e}")
			return ""

async def download_to_bytesio(url: str, chunk_size: int = 1024*1024) -> io.BytesIO | None:
	async with aiohttp.ClientSession() as session:
		try:
			async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as response:
				if response.status != 200:
					return None
				content_disp = response.headers.get('Content-Disposition', '')
				filename = next((part.split('=')[1].strip('"') for part in content_disp.split(';') if 'filename=' in part), None) or os.path.basename(urlparse(url).path)
				filename = (filename.replace("%20", " ").split("?")[0].split("#")[0].strip())
				file_buffer = io.BytesIO()
				async for chunk in response.content.iter_chunked(chunk_size):
					file_buffer.write(chunk)

				file_buffer.filename = filename
				file_buffer.seek(0)  # Reset buffer position
				return file_buffer

		except (aiohttp.ClientError, asyncio.TimeoutError) as e:
			print(f"Download error: {str(e)}")
			return None
		except Exception as e:
			print(f"Unexpected error: {str(e)}")
			return None
