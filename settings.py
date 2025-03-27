from pydantic_settings import BaseSettings

class Settings(BaseSettings):
	BOT_TOKEN: str
	GOOSHKON_BOT_USERNAME: str
	GOOSHKON_BOT_PASSWORD: str
	BASE_URL: str = "https://gooshkon.ir"
	WEBHOOK_HOST: str
	WEBHOOK_PORT: int = 8443

	class Config:
		env_file = ".env"

settings = Settings()