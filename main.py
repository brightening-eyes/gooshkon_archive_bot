from fastapi import FastAPI, HTTPException
import uvicorn
import telebot
from telebot.async_telebot import AsyncTeleBot
from settings import settings

app = FastAPI(docs=None, redoc_url=None)
bot = AsyncTeleBot(f'{settings.BOT_TOKEN}')

@app.post(f'/{settings.BOT_TOKEN}')
async def process_webhook(update: dict):
	if update:
		update = telebot.types.Update.de_json(update)
		await bot.process_new_updates([update])
	return

if __name__ == '__main__':
	bot.remove_webhook()
	bot.set_webhook(url=f'https://{settings.WEBHOOK_HOST}/{settings.BOT_TOKEN}')
	uvicorn.run(app, host='0.0.0.0', port=settings.WEBHOOK_PORT)
