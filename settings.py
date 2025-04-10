from pydantic_settings import BaseSettings

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

	class Config:
		# Load environment variables directly from env.dat
		env_file = "env.dat"

# Instantiate the settings object for use throughout the project
settings = Settings()