"""bot settings from environment variables"""
from pydantic_settings import BaseSettings

# bot settings: coded by Amir Ramezani, improved by Hossein Peimani and Roohan
class Settings(BaseSettings):
	# Telegram client ID and hash enabling file uploads beyond 50MB
	API_ID: int = 0  # Default to 0 if not provided
	API_HASH: str = ""  # Default to empty string if not provided
	# Bot authentication token for Telegram API
	BOT_TOKEN: str
	# Base URL of the website to scrape posts from
	BASE_URL: str
	# The channel users must join to use the bot
	CHANNEL_USERNAME: str

	# pydantic way of handling environment variable loading like dotenv
	class Config:
		# Load environment variables directly from env.dat
		env_file = ".env"

# Instantiate the settings object for use throughout the project
settings = Settings()