import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
    MODEL: str = os.getenv("MODEL", "qwen-plus")
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "8096"))

    OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", "output"))
    TEMP_DIR: Path = Path(os.getenv("TEMP_DIR", "temp"))

    MAX_LAYOUT_CLUSTERS: int = int(os.getenv("MAX_LAYOUT_CLUSTERS", "6"))
    MAX_SLIDES: int = int(os.getenv("MAX_SLIDES", "20"))
    MAX_CONTENT_LENGTH: int = int(os.getenv("MAX_CONTENT_LENGTH", "60000"))

    @classmethod
    def validate(cls) -> None:
        if not cls.DASHSCOPE_API_KEY:
            raise ValueError(
                "DASHSCOPE_API_KEY not set. Please set it in .env file or environment."
            )
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        cls.TEMP_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def ensure_dirs(cls) -> None:
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        cls.TEMP_DIR.mkdir(parents=True, exist_ok=True)


config = Config()
