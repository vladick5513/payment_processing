from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASS: str
    DB_NAME: str

    RABBIT_HOST: str
    RABBIT_PORT: int
    RABBIT_USER: str
    RABBIT_PASS: str

    API_KEY: str

    LOG_LEVEL: str

    @property
    def DATABASE_URL_asyncpg(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def RABBIT_URL(self) -> str:
        return (
            f"amqp://{self.RABBIT_USER}:{self.RABBIT_PASS}@{self.RABBIT_HOST}:{self.RABBIT_PORT}/"
        )


settings = Settings()
