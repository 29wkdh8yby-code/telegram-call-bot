from app.bot import CallServiceBot
from app.config import load_settings
from app.logging_config import configure_logging


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    CallServiceBot(settings).run()


if __name__ == "__main__":
    main()
