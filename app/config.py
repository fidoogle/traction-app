from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://traction:traction@localhost:5432/traction"
    )
    secret_key: str = DEFAULT_SECRET_KEY
    access_token_expire_minutes: int = 60 * 24


settings = Settings()
