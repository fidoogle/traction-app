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
    # How far back the Activity page goes; older entries are pruned.
    activity_retention_days: int = 90
    # How long the record of sent emails is kept.
    notification_log_retention_days: int = 90

    # Outgoing email. Entirely optional: with no SMTP host (or from-address,
    # or base URL) the app runs exactly as before and sends nothing. Point it
    # at the district's own mail relay; no hosted email service is involved.
    smtp_host: str = ""
    smtp_port: int = 587
    # "starttls" (port 587), "ssl" (implicit TLS, port 465) or "none" (a plain
    # internal relay, usually port 25).
    smtp_security: str = "starttls"
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = ""
    smtp_from_name: str = "Traction"
    smtp_timeout_seconds: int = 10
    # Fallback time zone, used only when an organization's own setting (Settings
    # page; US Central to begin with) is missing or unrecognised. An IANA name.
    default_timezone: str = "America/Chicago"
    # Public address of this app (e.g. https://traction.district.org), used to
    # build links inside emails.
    base_url: str = ""

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_address and self.base_url)

    def absolute_url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"


settings = Settings()
