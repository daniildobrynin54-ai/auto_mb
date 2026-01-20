"""Парсер данных профилей из Google Sheets с автоматическим поиском столбца."""

import re
import requests
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
from logger import get_logger

logger = get_logger("google_sheets")

# URL Google Sheets (публичный доступ)
SHEETS_URL = "https://docs.google.com/spreadsheets/d/1sYvrBU9BPhcoxTnNJfx8TOutxwFrSiRm2mw_8s6rdZM/gviz/tq?tqx=out:csv&gid=1142214254"


class GoogleSheetsParser:
    """Парсер профилей из Google Sheets."""
    
    def __init__(self, proxy_manager=None):
        self.proxies = None
        if proxy_manager and proxy_manager.is_enabled():
            self.proxies = proxy_manager.get_proxies()
    
    def fetch_sheet_data(self) -> Optional[str]:
        """Загружает CSV данные из Google Sheets."""
        try:
            logger.debug(f"Загрузка данных из Google Sheets...")
            
            response = requests.get(
                SHEETS_URL,
                proxies=self.proxies,
                timeout=15
            )
            
            if response.status_code == 200:
                logger.debug("✅ Данные загружены успешно")
                return response.text
            else:
                logger.warning(f"Ошибка загрузки: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка загрузки Google Sheets: {e}")
            return None
    
    def parse_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Парсит профиль пользователя из таблицы.
        
        Args:
            user_id: ID пользователя MangaBuff
        
        Returns:
            Словарь с данными профиля или None
        """
        csv_data = self.fetch_sheet_data()
        
        if not csv_data:
            logger.warning("Не удалось загрузить данные из таблицы")
            return None
        
        logger.debug(f"Поиск профиля для user_id: {user_id}")
        
        # Парсим CSV
        lines = csv_data.strip().split('\n')
        
        if len(lines) < 2:
            logger.warning("Таблица пустая или некорректная")
            return None
        
        # Первая строка - заголовки
        headers_line = lines[0]
        headers = [h.strip('"') for h in headers_line.split(',')]
        
        logger.debug(f"Заголовки: {headers}")
        
        # 🔧 ИСПРАВЛЕНО: Автоматический поиск столбца со ссылками
        link_column_index = None
        
        # Сначала пробуем найти по известным названиям
        possible_names = ['ссылка бафф', 'Ник', 'ник бафф', 'link', 'profile']
        for name in possible_names:
            try:
                link_column_index = headers.index(name)
                logger.info(f"Найден столбец '{name}' (индекс {link_column_index})")
                break
            except ValueError:
                continue
        
        # Если не нашли по названию - ищем автоматически по содержимому
        if link_column_index is None:
            logger.info("Столбец не найден по названию, ищем по содержимому...")
            if len(lines) > 1:
                first_data_line = lines[1]
                values = self._parse_csv_line(first_data_line)
                
                for i, value in enumerate(values):
                    if 'HYPERLINK' in value and '/users/' in value:
                        link_column_index = i
                        logger.info(f"✅ Найден столбец со ссылками автоматически (индекс {i})")
                        break
        
        if link_column_index is None:
            logger.error("❌ Столбец со ссылками на пользователей не найден в таблице")
            logger.error(f"Доступные заголовки: {headers}")
            return None
        
        # Ищем пользователя в строках
        for line in lines[1:]:
            # Разделяем CSV с учетом кавычек
            values = self._parse_csv_line(line)
            
            if len(values) <= link_column_index:
                continue
            
            # В столбце со ссылками должна быть формула HYPERLINK:
            # =HYPERLINK("https://mangabuff.ru/users/258280";"LTM I PoliS")
            link_cell = values[link_column_index]
            
            # Извлекаем user_id из HYPERLINK
            match = re.search(r'/users/(\d+)', link_cell)
            if not match:
                continue
            
            found_user_id = match.group(1)
            
            if found_user_id == user_id:
                logger.info(f"✅ Найден профиль для {user_id}")
                
                # Извлекаем название (после точки с запятой в HYPERLINK)
                name_match = re.search(r';"([^"]+)"', link_cell)
                username = name_match.group(1) if name_match else f"User{user_id}"
                
                # Создаем словарь профиля
                profile = {
                    'user_id': user_id,
                    'username': username
                }
                
                # Добавляем остальные поля
                for i, header in enumerate(headers):
                    if i < len(values):
                        # Очищаем от HYPERLINK
                        value = self._clean_value(values[i])
                        profile[header] = value
                
                logger.debug(f"Профиль: {profile}")
                return profile
        
        logger.warning(f"Профиль для {user_id} не найден в таблице")
        return None
    
    def _parse_csv_line(self, line: str) -> list:
        """Парсит строку CSV с учетом кавычек."""
        import csv
        import io
        
        reader = csv.reader(io.StringIO(line))
        return next(reader)
    
    def _clean_value(self, value: str) -> str:
        """Очищает значение от HYPERLINK и кавычек."""
        # Убираем HYPERLINK
        if 'HYPERLINK' in value:
            match = re.search(r';"([^"]+)"', value)
            if match:
                return match.group(1)
        
        # Убираем кавычки
        return value.strip('"')
    
    def format_profile_message(self, profile: Dict[str, Any]) -> str:
        """
        Форматирует профиль в красивое сообщение для Telegram.
        
        Args:
            profile: Словарь с данными профиля
        
        Returns:
            HTML-форматированное сообщение
        """
        username = profile.get('username', 'Неизвестно')
        user_id = profile.get('user_id', '?')
        
        # Формируем сообщение
        lines = [
            f"<b>👤 Профиль: {username}</b>",
            f"<code>ID: {user_id}</code>\n"
        ]
        
        # Добавляем остальные поля из таблицы
        # Пропускаем служебные поля
        skip_fields = {
            'user_id', 
            'username', 
            'Ник', 
            'ссылка бафф',  # 🔧 ДОБАВЛЕНО: пропускаем столбец со ссылками
            'ник бафф'      # Это уже отображено как username
        }
        
        for key, value in profile.items():
            if key in skip_fields or not value:
                continue
            
            # Пропускаем поля которые содержат только служебную информацию
            if key.lower().startswith('id ') or key.lower() == 'id':
                continue
            
            # Форматируем название поля
            field_name = key.strip()
            field_value = str(value).strip()
            
            if field_value and field_value != '0':  # Пропускаем пустые значения
                lines.append(f"<b>{field_name}:</b> {field_value}")
        
        # Добавляем ссылку на профиль
        lines.append(f"\n🔗 <a href='https://mangabuff.ru/users/{user_id}'>Перейти в профиль</a>")
        
        return "\n".join(lines)


# Глобальный экземпляр парсера
_sheets_parser: Optional[GoogleSheetsParser] = None


def get_sheets_parser(proxy_manager=None) -> GoogleSheetsParser:
    """Возвращает глобальный экземпляр парсера."""
    global _sheets_parser
    
    if _sheets_parser is None:
        _sheets_parser = GoogleSheetsParser(proxy_manager)
    
    return _sheets_parser