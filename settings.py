from pydantic_settings import BaseSettings

class Settings(BaseSettings):
	BOT_TOKEN: str
	GOOSHKON_BOT_USERNAME: str
	GOOSHKON_BOT_PASSWORD: str
	WEBHOOK_HOST: str
	WEBHOOK_PORT: int = 8443
