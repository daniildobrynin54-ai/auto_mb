"""База данных пользователей Telegram v2 с поддержкой множественных аккаунтов."""

import json
import os
import re
from typing import Optional, Dict, List, Tuple
from logger import get_logger

logger = get_logger("telegram_users_db")

USERS_DB_FILE = "telegram_users.json"


class TelegramUsersDB:
    """Управление базой данных пользователей Telegram."""
    
    def __init__(self, db_file: str = USERS_DB_FILE):
        self.db_file = db_file
        self.users = self._load_db()
    
    def _load_db(self) -> Dict[str, Dict]:
        """
        Загружает базу данных из файла.
        
        Новая структура:
        {
          "telegram_id": {
            "telegram_username": "username",
            "mangabuff_accounts": [
              {
                "user_id": "123456",
                "username": "Nickname",
                "notification_type": "dm"  # или "tag"
              }
            ]
          }
        }
        """
        if not os.path.exists(self.db_file):
            logger.info("База данных не найдена, создаем новую")
            return {}
        
        try:
            with open(self.db_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Миграция старого формата
                migrated = self._migrate_old_format(data)
                if migrated:
                    logger.info("Выполнена миграция базы данных")
                    self._save_db_direct(migrated)
                    return migrated
                
                logger.info(f"Загружено {len(data)} пользователей")
                return data
                
        except Exception as e:
            logger.error(f"Ошибка загрузки базы данных: {e}")
            return {}
    
    def _migrate_old_format(self, old_data: Dict) -> Optional[Dict]:
        """
        Мигрирует старый формат в новый.
        
        Старый: {mangabuff_id: {telegram_id, telegram_username}}
        Новый: {telegram_id: {telegram_username, mangabuff_accounts: [...]}}
        """
        # Проверяем нужна ли миграция
        if not old_data:
            return None
        
        # Если уже новый формат - пропускаем
        first_key = next(iter(old_data))
        if 'mangabuff_accounts' in old_data.get(first_key, {}):
            return None
        
        logger.info("Обнаружен старый формат базы, начинаем миграцию...")
        
        new_data = {}
        
        for mangabuff_id, user_data in old_data.items():
            telegram_id = str(user_data.get('telegram_id'))
            telegram_username = user_data.get('telegram_username')
            
            if not telegram_id:
                continue
            
            # Создаем запись для Telegram пользователя
            if telegram_id not in new_data:
                new_data[telegram_id] = {
                    'telegram_username': telegram_username,
                    'mangabuff_accounts': []
                }
            
            # Добавляем MangaBuff аккаунт
            new_data[telegram_id]['mangabuff_accounts'].append({
                'user_id': mangabuff_id,
                'username': f'User{mangabuff_id}',  # Временное имя
                'notification_type': 'tag'  # По умолчанию тег
            })
        
        logger.info(f"Миграция завершена: {len(new_data)} пользователей")
        return new_data
    
    def _save_db_direct(self, data: Dict) -> bool:
        """Прямое сохранение данных."""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}")
            return False
    
    def _save_db(self) -> bool:
        """Сохраняет базу данных."""
        return self._save_db_direct(self.users)
    
    def extract_id_from_url(self, url: str) -> Optional[str]:
        """Извлекает user_id из URL."""
        if url.startswith('@'):
            return None  # Username пока не поддерживается
        
        match = re.search(r'/users/(\d+)', url)
        if match:
            return match.group(1)
        
        # Если просто число
        if url.strip().isdigit():
            return url.strip()
        
        return None
    
    def register_account(
        self,
        telegram_id: int,
        telegram_username: Optional[str],
        mangabuff_url: str,
        mangabuff_username: Optional[str] = None,
        notification_type: str = 'dm'
    ) -> Tuple[bool, str]:
        """
        Регистрирует MangaBuff аккаунт для Telegram пользователя.
        
        Args:
            telegram_id: Telegram ID
            telegram_username: Telegram username
            mangabuff_url: URL профиля MangaBuff
            mangabuff_username: Nickname на MangaBuff (опционально)
            notification_type: 'dm' или 'tag'
        
        Returns:
            (успех, сообщение)
        """
        user_id = self.extract_id_from_url(mangabuff_url)
        
        if not user_id:
            return False, "❌ Не удалось извлечь ID из ссылки"
        
        telegram_id_str = str(telegram_id)
        
        # Создаем запись если нет
        if telegram_id_str not in self.users:
            self.users[telegram_id_str] = {
                'telegram_username': telegram_username,
                'mangabuff_accounts': []
            }
        
        # Проверяем не добавлен ли уже этот аккаунт
        accounts = self.users[telegram_id_str]['mangabuff_accounts']
        for acc in accounts:
            if acc['user_id'] == user_id:
                # Обновляем существующий
                acc['username'] = mangabuff_username or acc.get('username', f'User{user_id}')
                acc['notification_type'] = notification_type
                
                if self._save_db():
                    logger.info(f"Обновлен аккаунт: TG {telegram_id} → MB {user_id}")
                    return True, (
                        f"✅ Аккаунт обновлен!\n"
                        f"MangaBuff: {acc['username']} (ID: {user_id})\n"
                        f"Уведомления: {'Личные сообщения' if notification_type == 'dm' else 'Тег во вкладе'}"
                    )
                return False, "❌ Ошибка сохранения"
        
        # Добавляем новый аккаунт
        new_account = {
            'user_id': user_id,
            'username': mangabuff_username or f'User{user_id}',
            'notification_type': notification_type
        }
        
        accounts.append(new_account)
        
        if self._save_db():
            logger.info(f"Добавлен аккаунт: TG {telegram_id} → MB {user_id}")
            count = len(accounts)
            return True, (
                f"✅ Аккаунт добавлен!\n"
                f"MangaBuff: {new_account['username']} (ID: {user_id})\n"
                f"Уведомления: {'Личные сообщения' if notification_type == 'dm' else 'Тег во вкладе'}\n"
                f"\nВсего привязано аккаунтов: {count}"
            )
        
        return False, "❌ Ошибка сохранения"
    
    def unregister_account(
        self,
        telegram_id: int,
        mangabuff_user_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Удаляет привязку аккаунта.
        
        Args:
            telegram_id: Telegram ID
            mangabuff_user_id: ID аккаунта MangaBuff (если None - удалить все)
        
        Returns:
            (успех, сообщение)
        """
        telegram_id_str = str(telegram_id)
        
        if telegram_id_str not in self.users:
            return False, "❌ У вас нет привязанных аккаунтов"
        
        accounts = self.users[telegram_id_str]['mangabuff_accounts']
        
        # Удалить конкретный аккаунт
        if mangabuff_user_id:
            for acc in accounts:
                if acc['user_id'] == mangabuff_user_id:
                    accounts.remove(acc)
                    
                    if not accounts:
                        del self.users[telegram_id_str]
                    
                    if self._save_db():
                        return True, f"✅ Аккаунт {acc['username']} удален"
                    return False, "❌ Ошибка сохранения"
            
            return False, f"❌ Аккаунт с ID {mangabuff_user_id} не найден"
        
        # Удалить все аккаунты
        del self.users[telegram_id_str]
        
        if self._save_db():
            return True, f"✅ Все привязки удалены ({len(accounts)} аккаунтов)"
        
        return False, "❌ Ошибка сохранения"
    
    def get_user_accounts(self, telegram_id: int) -> List[Dict]:
        """Возвращает список аккаунтов пользователя."""
        telegram_id_str = str(telegram_id)
        
        if telegram_id_str not in self.users:
            return []
        
        return self.users[telegram_id_str]['mangabuff_accounts']
    
    def get_notification_settings(
        self,
        mangabuff_user_ids: List[str]
    ) -> Dict[str, Dict]:
        """
        Получает настройки уведомлений для списка MangaBuff user_ids.
        
        Returns:
            {
              user_id: {
                telegram_id: int,
                username: str,
                notification_type: str
              }
            }
        """
        settings = {}
        
        for telegram_id_str, user_data in self.users.items():
            for account in user_data['mangabuff_accounts']:
                user_id = account['user_id']
                
                if user_id in mangabuff_user_ids:
                    settings[user_id] = {
                        'telegram_id': int(telegram_id_str),
                        'username': account['username'],
                        'notification_type': account['notification_type']
                    }
        
        return settings
    
    def get_user_info(self, telegram_id: int) -> Optional[str]:
        """Возвращает информацию о привязанных аккаунтах."""
        accounts = self.get_user_accounts(telegram_id)
        
        if not accounts:
            return None
        
        lines = ["📝 <b>Ваши аккаунты MangaBuff:</b>\n"]
        
        for i, acc in enumerate(accounts, 1):
            notif_type = "📬 ЛС" if acc['notification_type'] == 'dm' else "🏷 Тег"
            lines.append(
                f"{i}. <b>{acc['username']}</b>\n"
                f"   ID: <code>{acc['user_id']}</code>\n"
                f"   {notif_type}"
            )
        
        return "\n".join(lines)
    
    def get_all_users_count(self) -> int:
        """Количество Telegram пользователей."""
        return len(self.users)
    
    def get_all_accounts_count(self) -> int:
        """Общее количество привязанных MangaBuff аккаунтов."""
        total = 0
        for user_data in self.users.values():
            total += len(user_data['mangabuff_accounts'])
        return total
    
    def set_notification_type(
        self,
        telegram_id: int,
        mangabuff_user_id: str,
        notification_type: str
    ) -> Tuple[bool, str]:
        """
        🔧 ИСПРАВЛЕНО: Изменяет тип уведомлений напрямую в self.users.
        
        Args:
            telegram_id: Telegram ID
            mangabuff_user_id: ID аккаунта MangaBuff
            notification_type: 'dm' или 'tag'
        
        Returns:
            (успех, сообщение)
        """
        if notification_type not in ['dm', 'tag']:
            logger.warning(f"Неверный тип: {notification_type}")
            return False, "❌ Неверный тип уведомлений (dm/tag)"
        
        telegram_id_str = str(telegram_id)
        
        logger.debug(f"🔍 Поиск аккаунта: TG {telegram_id_str} -> MB {mangabuff_user_id}")
        
        # 🔧 КРИТИЧНО: Работаем напрямую с self.users, а не с копией!
        if telegram_id_str not in self.users:
            logger.warning(f"Telegram ID {telegram_id_str} не найден в базе")
            return False, "❌ У вас нет привязанных аккаунтов"
        
        # Получаем прямую ссылку на список аккаунтов
        accounts = self.users[telegram_id_str]['mangabuff_accounts']
        
        logger.debug(f"Найдено аккаунтов: {len(accounts)}")
        
        for acc in accounts:
            logger.debug(f"Проверка аккаунта: {acc['user_id']} (тип: {type(acc['user_id'])})")
            
            # 🔧 ИСПРАВЛЕНО: Сравниваем строки
            if acc['user_id'] == mangabuff_user_id:
                logger.info(f"✅ Аккаунт найден! Изменяем {acc['notification_type']} -> {notification_type}")
                
                # Изменяем напрямую в self.users
                acc['notification_type'] = notification_type
                
                # Сохраняем базу
                if self._save_db():
                    notif_text = "личные сообщения" if notification_type == 'dm' else "тег во вкладе"
                    logger.info(f"✅ База данных сохранена")
                    return True, f"✅ Для {acc['username']}: {notif_text}"
                else:
                    logger.error(f"❌ Ошибка сохранения базы данных")
                    return False, "❌ Ошибка сохранения"
        
        logger.warning(f"Аккаунт {mangabuff_user_id} не найден среди {len(accounts)} аккаунтов")
        return False, f"❌ Аккаунт с ID {mangabuff_user_id} не найден"


# Глобальный экземпляр
_db_instance: Optional[TelegramUsersDB] = None


def get_users_db() -> TelegramUsersDB:
    """Возвращает глобальный экземпляр БД."""
    global _db_instance
    if _db_instance is None:
        _db_instance = TelegramUsersDB()
    return _db_instance
