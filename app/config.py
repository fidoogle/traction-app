from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://traction:traction@localhost:5432/traction"
    )
    secret_key: str = DEFAULT_SECRET_KEY
    access_token_expire_minutes: int = 60 * 24
    # Set true once served over HTTPS (e.g. behind a reverse proxy) so the
    # session cookie is marked Secure. False by default so local/plain-HTTP
    # on-prem dev setups still work.
    cookie_secure: bool = False


settings = Settings()
