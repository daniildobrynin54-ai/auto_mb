"""Система логирования с цветным выводом и сохранением в файлы по дням."""

import os
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path


# Цветовые коды для консоли (ANSI)
class Colors:
    """Цветовые коды для терминала."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # Основные цвета
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Яркие цвета
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'
    
    # Фон
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'


class ColoredFormatter(logging.Formatter):
    """Форматтер с цветным выводом в консоль."""
    
    # Цветовая схема для уровней логирования
    LEVEL_COLORS = {
        'DEBUG': Colors.BRIGHT_BLACK,
        'INFO': Colors.BRIGHT_CYAN,
        'WARNING': Colors.BRIGHT_YELLOW,
        'ERROR': Colors.BRIGHT_RED,
        'CRITICAL': Colors.BG_RED + Colors.BRIGHT_WHITE,
    }
    
    # Эмодзи для уровней логирования
    LEVEL_EMOJI = {
        'DEBUG': '🔧',
        'INFO': 'ℹ️ ',
        'WARNING': '⚠️ ',
        'ERROR': '❌',
        'CRITICAL': '🔥',
    }
    
    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None, use_colors: bool = True):
        """
        Инициализация форматтера.
        
        Args:
            fmt: Формат сообщения
            datefmt: Формат даты и времени
            use_colors: Использовать ли цвета в выводе
        """
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors
    
    def format(self, record: logging.LogRecord) -> str:
        """Форматирует запись лога с цветами."""
        if self.use_colors:
            # Получаем цвет и эмодзи для уровня
            level_color = self.LEVEL_COLORS.get(record.levelname, '')
            level_emoji = self.LEVEL_EMOJI.get(record.levelname, '')
            
            # Форматируем уровень с цветом
            levelname = f"{level_color}{level_emoji}  {record.levelname}{Colors.RESET}"
            
            # Сохраняем оригинальное имя уровня
            original_levelname = record.levelname
            record.levelname = levelname
            
            # Форматируем сообщение
            result = super().format(record)
            
            # Восстанавливаем оригинальное имя
            record.levelname = original_levelname
            
            return result
        else:
            return super().format(record)


class PlainFormatter(logging.Formatter):
    """Форматтер без цветов для файлов."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Форматирует запись лога без цветов."""
        return super().format(record)


class AppLogger:
    """Главный класс для управления логированием."""
    
    def __init__(
        self,
        name: str = "MangaBuff",
        base_dir: str = "logs",
        level: int = logging.INFO,
        console_colors: bool = True
    ):
        """
        Инициализация логгера.
        
        Args:
            name: Имя логгера
            base_dir: Базовая директория для логов
            level: Уровень логирования
            console_colors: Использовать ли цвета в консоли
        """
        self.name = name
        self.base_dir = Path(base_dir)
        self.level = level
        self.console_colors = console_colors
        
        # Создаем директорию для логов
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Создаем логгер
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Очищаем существующие обработчики
        self.logger.handlers.clear()
        
        # Добавляем обработчики
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Настраивает обработчики для консоли и файлов."""
        # === КОНСОЛЬНЫЙ ОБРАБОТЧИК ===
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.level)
        
        # Формат для консоли с цветами
        console_format = (
            f"{Colors.BRIGHT_BLACK}[%(asctime)s]{Colors.RESET} "
            f"%(levelname)s "
            f"{Colors.BRIGHT_BLACK}|{Colors.RESET} "
            f"{Colors.CYAN}%(name)s{Colors.RESET} "
            f"{Colors.BRIGHT_BLACK}>{Colors.RESET} "
            f"%(message)s"
        )
        
        console_formatter = ColoredFormatter(
            fmt=console_format,
            datefmt='%H:%M:%S',
            use_colors=self.console_colors
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # === ФАЙЛОВЫЙ ОБРАБОТЧИК (текущий день) ===
        current_date = datetime.now().strftime('%Y-%m-%d')
        log_file = self.base_dir / f"{current_date}.log"
        
        file_handler = logging.FileHandler(
            log_file,
            mode='a',
            encoding='utf-8'
        )
        file_handler.setLevel(self.level)
        
        # Формат для файла без цветов
        file_format = (
            '[%(asctime)s] %(levelname)-8s | %(name)s > %(message)s'
        )
        
        file_formatter = PlainFormatter(
            fmt=file_format,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # === ФАЙЛОВЫЙ ОБРАБОТЧИК (все ошибки) ===
        error_log_file = self.base_dir / "errors.log"
        
        error_handler = logging.FileHandler(
            error_log_file,
            mode='a',
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        self.logger.addHandler(error_handler)
    
    def debug(self, message: str, *args, **kwargs):
        """Логирует сообщение уровня DEBUG."""
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """Логирует сообщение уровня INFO."""
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """Логирует сообщение уровня WARNING."""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """Логирует сообщение уровня ERROR."""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """Логирует сообщение уровня CRITICAL."""
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs):
        """Логирует исключение с трассировкой."""
        self.logger.exception(message, *args, **kwargs)
    
    def section(self, title: str, char: str = "=", length: int = 60):
        """
        Выводит секцию с заголовком.
        
        Args:
            title: Заголовок секции
            char: Символ для рамки
            length: Длина рамки
        """
        border = char * length
        self.info(border)
        self.info(f"  {title}")
        self.info(border)
    
    def success(self, message: str):
        """Выводит сообщение об успехе."""
        colored_msg = f"{Colors.BRIGHT_GREEN}✅ {message}{Colors.RESET}"
        self.logger.info(colored_msg)
    
    def failure(self, message: str):
        """Выводит сообщение об ошибке."""
        colored_msg = f"{Colors.BRIGHT_RED}❌ {message}{Colors.RESET}"
        self.logger.error(colored_msg)


class ModuleLogger:
    """Логгер для отдельного модуля."""
    
    def __init__(self, module_name: str, app_logger: AppLogger):
        """
        Инициализация логгера модуля.
        
        Args:
            module_name: Имя модуля
            app_logger: Главный логгер приложения
        """
        self.module_name = module_name
        self.app_logger = app_logger
        self.logger = logging.getLogger(f"{app_logger.name}.{module_name}")
        self.logger.setLevel(app_logger.level)
    
    def debug(self, message: str, *args, **kwargs):
        """Логирует сообщение уровня DEBUG."""
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """Логирует сообщение уровня INFO."""
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """Логирует сообщение уровня WARNING."""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """Логирует сообщение уровня ERROR."""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """Логирует сообщение уровня CRITICAL."""
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs):
        """Логирует исключение с трассировкой."""
        self.logger.exception(message, *args, **kwargs)
    
    def section(self, title: str, char: str = "=", length: int = 60):
        """
        Выводит секцию с заголовком (делегирует в AppLogger).
        
        Args:
            title: Заголовок секции
            char: Символ для рамки
            length: Длина рамки
        """
        self.app_logger.section(title, char, length)
    
    def success(self, message: str):
        """Выводит сообщение об успехе (делегирует в AppLogger)."""
        self.app_logger.success(message)
    
    def failure(self, message: str):
        """Выводит сообщение об ошибке (делегирует в AppLogger)."""
        self.app_logger.failure(message)


# Глобальный экземпляр логгера
_global_logger: Optional[AppLogger] = None


def setup_logger(
    name: str = "MangaBuff",
    base_dir: str = "logs",
    level: int = logging.INFO,
    console_colors: bool = True
) -> AppLogger:
    """
    Настраивает и возвращает главный логгер приложения.
    
    Args:
        name: Имя логгера
        base_dir: Базовая директория для логов
        level: Уровень логирования
        console_colors: Использовать ли цвета в консоли
    
    Returns:
        Настроенный логгер
    """
    global _global_logger
    _global_logger = AppLogger(
        name=name,
        base_dir=base_dir,
        level=level,
        console_colors=console_colors
    )
    return _global_logger


def get_logger(module_name: Optional[str] = None) -> AppLogger | ModuleLogger:
    """
    Возвращает логгер.
    
    Args:
        module_name: Имя модуля (опционально)
    
    Returns:
        Логгер приложения или модуля
    """
    global _global_logger
    
    if _global_logger is None:
        # Создаем логгер с настройками по умолчанию
        setup_logger()
    
    if module_name:
        return ModuleLogger(module_name, _global_logger)
    
    return _global_logger


# Удобные функции для быстрого доступа
def debug(message: str, *args, **kwargs):
    """Логирует сообщение уровня DEBUG."""
    get_logger().debug(message, *args, **kwargs)


def info(message: str, *args, **kwargs):
    """Логирует сообщение уровня INFO."""
    get_logger().info(message, *args, **kwargs)


def warning(message: str, *args, **kwargs):
    """Логирует сообщение уровня WARNING."""
    get_logger().warning(message, *args, **kwargs)


def error(message: str, *args, **kwargs):
    """Логирует сообщение уровня ERROR."""
    get_logger().error(message, *args, **kwargs)


def critical(message: str, *args, **kwargs):
    """Логирует сообщение уровня CRITICAL."""
    get_logger().critical(message, *args, **kwargs)


def exception(message: str, *args, **kwargs):
    """Логирует исключение с трассировкой."""
    get_logger().exception(message, *args, **kwargs)


def section(title: str, char: str = "=", length: int = 60):
    """Выводит секцию с заголовком."""
    get_logger().section(title, char, length)


def success(message: str):
    """Выводит сообщение об успехе."""
    get_logger().success(message)


def failure(message: str):
    """Выводит сообщение об ошибке."""
    get_logger().failure(message)
