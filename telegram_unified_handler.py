"""Объединенный обработчик Telegram бота - команды + мониторинг ответов."""

import threading
import time
import requests
from typing import Optional, Callable
from telegram_users_db import get_users_db
from logger import get_logger

logger = get_logger("telegram_unified")


class TelegramUnifiedHandler:
    """Единый обработчик для команд и мониторинга ответов."""
    
    TRIGGER_KEYWORDS = [
        "смена карты",
        "смена",
        "заменить",
        "замени",
        "change card",
        "replace"
    ]
    
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        thread_id: Optional[int],
        on_replace_triggered: Optional[Callable] = None,
        proxy_manager=None
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.thread_id = thread_id
        self.on_replace_triggered = on_replace_triggered
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
        self.last_update_id = 0
        self.running = False
        self.thread = None
        self.users_db = get_users_db()
        self.bot_message_ids = set()  # Для мониторинга ответов
        
        # Прокси
        self.proxies = None
        if proxy_manager and proxy_manager.is_enabled():
            self.proxies = proxy_manager.get_proxies()
            logger.info(f"Telegram unified handler использует прокси")
        
        self._test_connection()
    
    def _test_connection(self) -> bool:
        """Тестирует подключение."""
        try:
            url = f"{self.api_url}/getMe"
            response = requests.get(url, proxies=self.proxies, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    bot_info = data.get('result', {})
                    bot_username = bot_info.get('username', 'Unknown')
                    logger.info(f"✅ Telegram бот подключен: @{bot_username}")
                    return True
            
            logger.error(f"❌ Ошибка подключения: {response.status_code}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False
    
    def register_bot_message(self, message_id: int) -> None:
        """Регистрирует ID сообщения бота для мониторинга ответов."""
        self.bot_message_ids.add(message_id)
        logger.debug(f"Зарегистрировано сообщение бота: {message_id}")
    
    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML"
    ) -> bool:
        """Отправляет личное сообщение пользователю."""
        try:
            url = f"{self.api_url}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            
            response = requests.post(url, json=data, proxies=self.proxies, timeout=10)
            
            if response.status_code == 200:
                logger.debug(f"Сообщение отправлено: {chat_id}")
                return True
            else:
                logger.warning(f"Ошибка отправки: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            return False
    
    def _is_trigger_message(self, text: str) -> bool:
        """Проверяет содержит ли текст триггерные слова."""
        if not text:
            return False
        
        text_lower = text.lower().strip()
        return any(keyword in text_lower for keyword in self.TRIGGER_KEYWORDS)
    
    def process_command(
        self,
        chat_id: int,
        telegram_username: Optional[str],
        first_name: Optional[str],
        text: str
    ) -> None:
        """Обрабатывает команду от пользователя."""
        text = text.strip()
        logger.info(f"📩 Команда от {telegram_username or first_name} ({chat_id}): {text[:50]}")
        
        # === КОМАНДА /start ===
        if text.startswith('/start'):
            self.send_message(
                chat_id,
                "👋 <b>Привет!</b>\n\n"
                "Я бот для уведомлений MangaBuff ClubTaro.\n\n"
                "<b>🎯 Зачем регистрироваться?</b>\n"
                "Когда в клубе появится новая карта и она есть у вас, "
                "я отправлю вам уведомление!\n\n"
                "<b>📝 Как зарегистрировать аккаунт:</b>\n"
                "Отправьте мне ссылку на ваш профиль MangaBuff:\n"
                "• <code>https://mangabuff.ru/users/123456</code>\n"
                "• Или просто ID: <code>123456</code>\n\n"
                "<b>📋 Команды:</b>\n"
                "/add - Добавить аккаунт\n"
                "/list - Мои аккаунты\n"
                "/notify - Настройки уведомлений\n"
                "/remove - Удалить аккаунт\n"
                "/stats - Статистика\n"
                "/help - Помощь"
            )
            logger.info(f"✅ Отправлен /start для {chat_id}")
        
        # === КОМАНДА /add ===
        elif text.startswith('/add'):
            self.send_message(
                chat_id,
                "📝 <b>Добавление аккаунта</b>\n\n"
                "Отправьте мне ссылку на ваш профиль MangaBuff:\n"
                "• <code>https://mangabuff.ru/users/123456</code>\n"
                "• Или просто ID: <code>123456</code>\n\n"
                "<i>После добавления вы сможете настроить тип уведомлений</i>"
            )
        
        # === КОМАНДА /list ===
        elif text.startswith('/list'):
            info = self.users_db.get_user_info(chat_id)
            if info:
                self.send_message(chat_id, info)
            else:
                self.send_message(
                    chat_id,
                    "❌ <b>У вас нет привязанных аккаунтов</b>\n\n"
                    "Отправьте мне ссылку на ваш профиль MangaBuff для добавления.\n\n"
                    "<i>Например: https://mangabuff.ru/users/826513</i>"
                )
        
        # === КОМАНДА /notify ===
        elif text.startswith('/notify'):
            accounts = self.users_db.get_user_accounts(chat_id)
            
            if not accounts:
                self.send_message(
                    chat_id,
                    "❌ <b>У вас нет привязанных аккаунтов</b>\n\n"
                    "Сначала добавьте аккаунт с помощью /add"
                )
                return
            
            # Показываем инструкцию
            lines = [
                "<b>⚙️ Настройка уведомлений</b>\n",
                "Выберите тип уведомлений для каждого аккаунта:\n"
            ]
            
            for acc in accounts:
                current = "📬 ЛС" if acc['notification_type'] == 'dm' else "🏷 Теги"
                lines.append(
                    f"• <b>{acc['username']}</b> (ID: {acc['user_id']})\n"
                    f"  Текущий тип: {current}"
                )
            
            lines.append(
                "\n<b>Изменить настройки:</b>\n"
                "<code>/notify_dm USER_ID</code> - личные сообщения\n"
                "<code>/notify_tag USER_ID</code> - теги во вкладе\n\n"
                "<b>Пример:</b>\n"
                f"<code>/notify_dm {accounts[0]['user_id']}</code>"
            )
            
            self.send_message(chat_id, "\n".join(lines))
        
        # === КОМАНДА /notify_dm USER_ID ===
        elif text.startswith('/notify_dm '):
            parts = text.split()
            if len(parts) < 2:
                self.send_message(
                    chat_id,
                    "❌ Укажите USER_ID\n\n"
                    "<i>Пример: /notify_dm 123456</i>"
                )
                return
            
            user_id = parts[1].strip()
            success, message = self.users_db.set_notification_type(
                chat_id,
                user_id,
                'dm'
            )
            self.send_message(chat_id, message)
            logger.info(f"{'✅' if success else '❌'} Изменение типа: {chat_id} -> dm")
        
        # === КОМАНДА /notify_tag USER_ID ===
        elif text.startswith('/notify_tag '):
            parts = text.split()
            if len(parts) < 2:
                self.send_message(
                    chat_id,
                    "❌ Укажите USER_ID\n\n"
                    "<i>Пример: /notify_tag 123456</i>"
                )
                return
            
            user_id = parts[1].strip()
            success, message = self.users_db.set_notification_type(
                chat_id,
                user_id,
                'tag'
            )
            self.send_message(chat_id, message)
            logger.info(f"{'✅' if success else '❌'} Изменение типа: {chat_id} -> tag")
        
        # === КОМАНДА /remove ===
        elif text.startswith('/remove'):
            parts = text.split()
            
            # Удалить конкретный аккаунт
            if len(parts) >= 2:
                user_id = parts[1].strip()
                success, message = self.users_db.unregister_account(chat_id, user_id)
                self.send_message(chat_id, message)
                logger.info(f"{'✅' if success else '❌'} Удаление аккаунта: {chat_id} -> {user_id}")
            
            # Показать инструкцию
            else:
                accounts = self.users_db.get_user_accounts(chat_id)
                
                if not accounts:
                    self.send_message(
                        chat_id,
                        "❌ <b>У вас нет привязанных аккаунтов</b>"
                    )
                    return
                
                lines = ["<b>🗑 Удаление аккаунтов</b>\n"]
                
                for acc in accounts:
                    lines.append(
                        f"• {acc['username']} (ID: {acc['user_id']})\n"
                        f"  <code>/remove {acc['user_id']}</code>"
                    )
                
                self.send_message(chat_id, "\n".join(lines))
        
        # === КОМАНДА /help ===
        elif text.startswith('/help'):
            self.send_message(
                chat_id,
                "<b>❓ Помощь</b>\n\n"
                "<b>🎯 Зачем регистрироваться?</b>\n"
                "Когда в клубе появится новая карта и она есть у вас, "
                "бот отправит уведомление.\n\n"
                "<b>📬 Типы уведомлений:</b>\n"
                "• <b>Личные сообщения (ЛС)</b> - бот пишет вам в личку\n"
                "• <b>Теги во вкладе</b> - бот тегает вас в общем сообщении\n\n"
                "<b>📝 Как добавить аккаунт?</b>\n"
                "1. Зайдите на свой профиль на mangabuff.ru\n"
                "2. Скопируйте ссылку или ID\n"
                "3. Отправьте боту\n\n"
                "<b>📋 Команды:</b>\n"
                "/start - Приветствие\n"
                "/add - Добавить аккаунт\n"
                "/list - Мои аккаунты\n"
                "/notify - Настройки уведомлений\n"
                "/remove - Удалить аккаунт\n"
                "/stats - Статистика"
            )
        
        # === КОМАНДА /stats ===
        elif text.startswith('/stats'):
            users_count = self.users_db.get_all_users_count()
            accounts_count = self.users_db.get_all_accounts_count()
            
            self.send_message(
                chat_id,
                f"📊 <b>Статистика бота</b>\n\n"
                f"Зарегистрировано пользователей: <b>{users_count}</b>\n"
                f"Всего привязанных аккаунтов: <b>{accounts_count}</b>"
            )
        
        # === РЕГИСТРАЦИЯ ПО URL ===
        elif not text.startswith('/'):
            # Это может быть URL или ID для регистрации
            success, message = self.users_db.register_account(
                chat_id,
                telegram_username,
                text,
                mangabuff_username=None,  # Будет обновлено при парсинге
                notification_type='dm'  # По умолчанию ЛС
            )
            
            if success:
                # Добавляем подсказку про настройки
                message += (
                    "\n\n<b>⚙️ Настройки уведомлений:</b>\n"
                    "По умолчанию: 📬 Личные сообщения\n"
                    "Изменить: /notify"
                )
            
            self.send_message(chat_id, message)
            logger.info(f"{'✅' if success else '❌'} Регистрация: {telegram_username} -> {text[:50]}")
        
        # === НЕИЗВЕСТНАЯ КОМАНДА ===
        else:
            self.send_message(
                chat_id,
                "❌ Неизвестная команда\n\n"
                "Используйте /help для списка команд"
            )
    
    def process_reply(
        self,
        chat_id: str,
        reply_to_id: int,
        text: str,
        from_user: dict
    ) -> None:
        """Обрабатывает ответ на сообщение бота."""
        # Проверяем что это ответ на наше сообщение
        if reply_to_id not in self.bot_message_ids:
            return
        
        # Проверяем триггерные слова
        if not self._is_trigger_message(text):
            return
        
        username = from_user.get('username', 'Unknown')
        first_name = from_user.get('first_name', 'User')
        
        logger.info(f"🔔 ТРИГГЕР ЗАМЕНЫ от {username or first_name}: '{text}'")
        print(f"\n🔔 ПОЛУЧЕНА КОМАНДА ЗАМЕНЫ КАРТЫ!")
        print(f"   От: {username or first_name}")
        print(f"   Текст: {text}\n")
        
        # Вызываем callback
        if self.on_replace_triggered:
            self.on_replace_triggered()
        
        # Удаляем ID чтобы не срабатывать повторно
        self.bot_message_ids.discard(reply_to_id)
    
    def get_updates(self) -> list:
        """Получает обновления от Telegram."""
        try:
            url = f"{self.api_url}/getUpdates"
            params = {
                "offset": self.last_update_id + 1,
                "timeout": 30,
                "allowed_updates": ["message"]
            }
            
            response = requests.get(
                url,
                params=params,
                proxies=self.proxies,
                timeout=35
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    return data.get('result', [])
            
            return []
        except requests.Timeout:
            return []
        except Exception as e:
            logger.error(f"Ошибка getUpdates: {e}")
            return []
    
    def process_updates(self) -> None:
        """Обрабатывает полученные обновления."""
        updates = self.get_updates()
        
        if not updates:
            return
        
        logger.debug(f"Получено {len(updates)} обновлений")
        
        for update in updates:
            try:
                self.last_update_id = update.get('update_id', 0)
                
                message = update.get('message')
                if not message:
                    continue
                
                chat = message.get('chat', {})
                chat_id = chat.get('id')
                chat_id_str = str(chat_id)
                chat_type = chat.get('type')
                
                from_user = message.get('from', {})
                telegram_username = from_user.get('username')
                first_name = from_user.get('first_name', 'Unknown')
                text = message.get('text', '')
                
                if not chat_id or not text:
                    continue
                
                # === ЛИЧНЫЕ СООБЩЕНИЯ (команды) ===
                if chat_type == 'private':
                    self.process_command(chat_id, telegram_username, first_name, text)
                
                # === ГРУППОВЫЕ СООБЩЕНИЯ (мониторинг ответов) ===
                elif chat_id_str == self.chat_id:
                    # Проверяем thread_id если указан
                    if self.thread_id:
                        message_thread_id = message.get('message_thread_id')
                        if message_thread_id != self.thread_id:
                            continue
                    
                    # Проверяем это ответ?
                    reply_to = message.get('reply_to_message')
                    if reply_to:
                        replied_to_id = reply_to.get('message_id')
                        self.process_reply(chat_id_str, replied_to_id, text, from_user)
                
            except Exception as e:
                logger.error(f"Ошибка обработки обновления: {e}")
    
    def polling_loop(self) -> None:
        """Основной цикл получения обновлений."""
        logger.info("🤖 Telegram unified handler запущен и ожидает...")
        logger.info(f"👁️  Мониторинг триггеров: {', '.join(self.TRIGGER_KEYWORDS)}")
        logger.info("📱 Отправьте /start боту для регистрации")
        
        consecutive_errors = 0
        max_errors = 5
        
        while self.running:
            try:
                self.process_updates()
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Ошибка в цикле polling ({consecutive_errors}/{max_errors}): {e}")
                
                if consecutive_errors >= max_errors:
                    logger.error(f"Слишком много ошибок подряд ({max_errors}), остановка бота")
                    self.running = False
                    break
                
                time.sleep(5)
    
    def start(self) -> None:
        """Запускает обработчик."""
        if self.running:
            logger.warning("Unified handler уже запущен")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self.polling_loop, daemon=True)
        self.thread.start()
        logger.info("✅ Unified handler запущен")
    
    def stop(self) -> None:
        """Останавливает обработчик."""
        if not self.running:
            return
        
        logger.info("🛑 Остановка unified handler...")
        self.running = False
        
        if self.thread:
            self.thread.join(timeout=5)
        
        logger.info("✅ Unified handler остановлен")


# Глобальный экземпляр
_unified_handler: Optional[TelegramUnifiedHandler] = None


def create_unified_handler(
    bot_token: str,
    chat_id: str,
    thread_id: Optional[int],
    on_replace_triggered: Optional[Callable] = None,
    proxy_manager=None
) -> TelegramUnifiedHandler:
    """Создает и запускает unified handler."""
    global _unified_handler
    
    if _unified_handler and _unified_handler.running:
        _unified_handler.stop()
    
    _unified_handler = TelegramUnifiedHandler(
        bot_token,
        chat_id,
        thread_id,
        on_replace_triggered,
        proxy_manager
    )
    
    _unified_handler.start()
    return _unified_handler


def get_unified_handler() -> Optional[TelegramUnifiedHandler]:
    """Возвращает глобальный unified handler."""
    return _unified_handler


def stop_unified_handler() -> None:
    """Останавливает глобальный unified handler."""
    global _unified_handler
    
    if _unified_handler:
        _unified_handler.stop()
        _unified_handler = None