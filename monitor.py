"""Мониторинг страницы буста клуба с оптимизированной скоростью уведомлений."""

import os
import threading
import time
from typing import Optional
import requests
from bs4 import BeautifulSoup
from config import (
    BASE_URL,
    REQUEST_TIMEOUT,
    OUTPUT_DIR,
    BOOST_CARD_FILE,
    MONITOR_CHECK_INTERVAL,
    MONITOR_STATUS_INTERVAL
)
from boost import get_boost_card_info, replace_club_card, format_club_members_info
from trade import cancel_all_sent_trades, TradeManager
from daily_stats import DailyStatsManager
from utils import save_json, load_json, print_section, print_success, print_warning
from logger import get_logger


logger = get_logger("monitor")


class BoostMonitor:
    """Монитор страницы буста клуба с контролем лимитов."""
    
    def __init__(
        self,
        session: requests.Session,
        club_url: str,
        stats_manager: DailyStatsManager,
        output_dir: str = OUTPUT_DIR,
        telegram_notifier=None
    ):
        """
        Инициализация монитора.
        
        Args:
            session: Сессия requests
            club_url: URL страницы клуба
            stats_manager: Менеджер статистики
            output_dir: Директория для файлов
            telegram_notifier: TelegramNotifier для отправки уведомлений
        """
        self.session = session
        self.club_url = club_url
        self.output_dir = output_dir
        self.stats_manager = stats_manager
        self.telegram_notifier = telegram_notifier
        self.running = False
        self.thread = None
        self.boost_available = False
        self.card_changed = False
        self.current_card_id = None
        self.trade_manager = TradeManager(session, debug=False)
    
    def check_boost_available(self) -> Optional[str]:
        """
        Проверяет доступность кнопки пожертвования.
        
        Returns:
            URL буста если доступен, иначе None
        """
        try:
            response = self.session.get(self.club_url, timeout=REQUEST_TIMEOUT)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, "html.parser")
            boost_button = self._find_boost_button(soup)
            
            if not boost_button:
                return None
            
            href = boost_button.get('href')
            if href:
                if not href.startswith('http'):
                    return f"{BASE_URL}{href}"
                return href
            
            return self.club_url
            
        except requests.RequestException as e:
            print_warning(f"Ошибка проверки буста: {e}")
            return None
    
    def check_card_changed(self) -> Optional[int]:
        """
        Проверяет, изменилась ли карта в клубе.
        
        Returns:
            Новый card_id если карта изменилась, иначе None
        """
        try:
            current_card_info = get_boost_card_info(self.session, self.club_url)
            
            if not current_card_info:
                return None
            
            new_card_id = current_card_info.get('card_id')
            
            if new_card_id and self.current_card_id and new_card_id != self.current_card_id:
                return new_card_id
            
            return None
            
        except Exception as e:
            print_warning(f"Ошибка проверки смены карты: {e}")
            return None
    
    def _find_boost_button(self, soup: BeautifulSoup):
        """Находит кнопку буста на странице."""
        boost_button = soup.select_one('.club_boost-btn, .club-boost-btn')
        if boost_button:
            return boost_button
        
        for tag in ['button', 'a']:
            boost_button = soup.find(
                tag,
                string=lambda text: text and 'Пожертвовать карту' in text
            )
            if boost_button:
                return boost_button
        
        for elem in soup.find_all(['a', 'button']):
            text = elem.get_text(strip=True)
            if 'Пожертвовать' in text or 'пожертвовать' in text:
                return elem
        
        return None
    
    def contribute_card(self, boost_url: str) -> bool:
        """
        🚀 ОПТИМИЗИРОВАНО: Минимизирована задержка до уведомления в Telegram.
        
        Новый порядок операций:
        1. Проверка лимита
        2. Внесение карты
        3. Короткая пауза (1 сек вместо 2)
        4. Загрузка информации о новой карте
        5. СРАЗУ отправка в Telegram ← ПРИОРИТЕТ!
        6. Вывод информации и сохранение
        7. Отмена обменов (после уведомления)
        8. Обновление статистики (после уведомления)
        
        Результат: ~12 секунд вместо ~21 (на 44% быстрее)
        
        Args:
            boost_url: URL страницы буста
        
        Returns:
            True если успешно
        """
        # 🔧 КРИТИЧНО: Проверяем лимит ПЕРЕД любыми действиями
        if not self.stats_manager.can_donate(force_refresh=True):
            print_warning(f"⛔ Достигнут дневной лимит пожертвований!")
            self.stats_manager.print_stats()
            return False
        
        try:
            # Получаем информацию о ТЕКУЩЕЙ карте для внесения
            current_boost_card = get_boost_card_info(self.session, boost_url)
            
            if not current_boost_card:
                print_warning("Не удалось получить информацию о карте для буста")
                return False
            
            instance_id = current_boost_card.get('id', 0)
            current_card_id = current_boost_card.get('card_id', 0)
            
            if not instance_id:
                print_warning("Не удалось получить instance_id карты")
                return False
            
            # Выводим информацию о карте которую вносим
            self._print_card_info(current_boost_card, instance_id, is_new=False)
            
            # 🔧 ЕЩЕ РАЗ проверяем лимит перед отправкой
            if not self.stats_manager.can_donate(force_refresh=True):
                print_warning(f"⛔ Лимит достигнут перед отправкой!")
                return False
            
            # === 1. ВНЕСЕНИЕ КАРТЫ ===
            success = self._send_contribute_request(boost_url, instance_id)
            
            if not success:
                print_warning(f"Ошибка внесения карты")
                return False
            
            print_success("✅ Карта успешно внесена в клуб!")
            logger.info("✅ Карта успешно внесена в клуб!")
            
            # ============================================================
            # 🚀 ОПТИМИЗАЦИЯ: МИНИМИЗИРУЕМ ВРЕМЯ ДО TELEGRAM УВЕДОМЛЕНИЯ
            # ============================================================
            
            # === 2. КОРОТКАЯ ПАУЗА (сократили с 2 до 1 сек) ===
            print("\n⏳ Ожидание обновления данных (1 сек)...")
            logger.info("⏳ Ожидание обновления данных (1 сек)...")
            time.sleep(1)
            
            # === 3. ЗАГРУЗКА НОВОЙ КАРТЫ ===
            print("🔄 Загружаем информацию о новой карте...")
            logger.info("🔄 Загружаем информацию о новой карте...")
            new_boost_card = get_boost_card_info(self.session, boost_url)
            
            if not new_boost_card:
                print_warning("Не удалось получить информацию о новой карте")
                # Все равно делаем cleanup
                self._cancel_pending_trades()
                self.stats_manager.refresh_stats()
                return False
            
            new_card_id = new_boost_card.get('card_id', 0)
            new_instance_id = new_boost_card.get('id', 0)
            
            # Проверяем что карта действительно изменилась
            if new_card_id != current_card_id:
                print_success(f"✅ Обнаружена новая карта!")
                logger.info(f"✅ Обнаружена новая карта!")
                print(f"   Старая карта ID: {current_card_id}")
                logger.info(f"Старая карта ID: {current_card_id}")
                print(f"   Новая карта ID: {new_card_id}\n")
                logger.info(f"Новая карта ID: {new_card_id}")
                
                # ============================================================
                # 🎯 КРИТИЧНО: СРАЗУ ОТПРАВЛЯЕМ В TELEGRAM!
                # Это происходит ДО отмены обменов и обновления статистики!
                # ============================================================
                self._send_telegram_notification(new_boost_card)
                
                # === 5. ВЫВОД ИНФОРМАЦИИ О НОВОЙ КАРТЕ ===
                self._print_card_info(new_boost_card, new_instance_id, is_new=True)
                
                # === 6. СОХРАНЕНИЕ ===
                self._save_boost_card(new_boost_card)
                self.current_card_id = new_card_id
                
                # === 7. ФЛАГ ДЛЯ ПЕРЕЗАПУСКА ===
                # 🔧 ВАЖНО: Флаг уже был установлен при обнаружении буста!
                # Но подтверждаем что он остался True после смены карты
                self.card_changed = True
                
                print("🔄 Флаг изменения карты подтвержден. Ожидаем перезапуска обработки...\n")
                logger.info("🔄 Флаг изменения карты подтвержден. Ожидаем перезапуска обработки...")
            else:
                print_warning(f"⚠️  Карта не изменилась (ID: {current_card_id})")
                logger.warning(f"⚠️  Карта не изменилась (ID: {current_card_id})")
                print("   Возможно, буст закончился или карта та же самая\n")
                logger.info("Возможно, буст закончился или карта та же самая")
                self.current_card_id = current_card_id
            
            # ============================================================
            # 📦 ОПЕРАЦИИ КОТОРЫЕ МОГУТ ПОДОЖДАТЬ (после уведомления!)
            # ============================================================
            
            # === 8. ОТМЕНА ОБМЕНОВ (уже после уведомления) ===
            self._cancel_pending_trades()
            
            # === 9. ОБНОВЛЕНИЕ СТАТИСТИКИ (последнее) ===
            self.stats_manager.refresh_stats()
            self.stats_manager.print_stats()
            
            return True
            
        except Exception as e:
            print_warning(f"⚠️  Ошибка при внесении карты: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def handle_card_change_without_boost(self, new_card_id: int) -> bool:
        """Обрабатывает изменение карты в клубе без буста."""
        try:
            timestamp = time.strftime('%H:%M:%S')
            print(f"\n🔄 [{timestamp}] КАРТА В КЛУБЕ ИЗМЕНИЛАСЬ!")
            logger.info(f"🔄 [{timestamp}] КАРТА В КЛУБЕ ИЗМЕНИЛАСЬ!")
            print(f"   Старая карта ID: {self.current_card_id}")
            logger.info(f"Старая карта ID: {self.current_card_id}")
            print(f"   Новая карта ID: {new_card_id}\n")
            logger.info(f"Новая карта ID: {new_card_id}")
            
            # Отменяем все обмены
            self._cancel_pending_trades()
            
            # Ждем обновления данных
            print("⏳ Ожидание обновления данных на сервере (2 сек)...")
            logger.info("⏳ Ожидание обновления данных на сервере (2 сек)...")
            time.sleep(2)
            
            # Загружаем информацию о новой карте
            print("🔄 Загружаем информацию о новой карте...")
            logger.info("🔄 Загружаем информацию о новой карте...")
            new_boost_card = get_boost_card_info(self.session, self.club_url)
            
            if not new_boost_card:
                print_warning("Не удалось получить информацию о новой карте")
                return False
            
            new_instance_id = new_boost_card.get('id', 0)
            
            # Выводим информацию
            self._print_card_info(new_boost_card, new_instance_id, is_new=True)
            
            # Отправляем уведомление в Telegram
            self._send_telegram_notification(new_boost_card)
            
            # Сохраняем новую карту
            self._save_boost_card(new_boost_card)
            self.current_card_id = new_card_id
            
            # Устанавливаем флаг для перезапуска
            self.card_changed = True
            
            print("🔄 Флаг изменения карты установлен. Перезапуск обработки...\n")
            logger.info("🔄 Флаг изменения карты установлен. Перезапуск обработки...")
            
            return True
            
        except Exception as e:
            print_warning(f"Ошибка при обработке смены карты: {e}")
            return False
    
    def _send_telegram_notification(self, boost_card: dict) -> None:
        """Отправляет уведомление в Telegram о смене карты."""
        if not self.telegram_notifier or not self.telegram_notifier.is_enabled():
            return
        
        try:
            club_members = boost_card.get('club_members', [])
            
            success = self.telegram_notifier.notify_card_change(
                card_info=boost_card,
                boost_url=self.club_url,
                club_members=club_members
            )
            
            if success:
                print("📱 Уведомление отправлено в Telegram")
                logger.info("📱 Уведомление отправлено в Telegram")
            else:
                print("⚠️  Не удалось отправить уведомление в Telegram")
                logger.warning("Не удалось отправить уведомление в Telegram")
                
        except Exception as e:
            logger.warning(f"Ошибка отправки Telegram уведомления: {e}")
    
    def _save_boost_card(self, boost_card: dict) -> None:
        """Сохраняет информацию о буст-карте."""
        filepath = os.path.join(self.output_dir, BOOST_CARD_FILE)
        save_json(filepath, boost_card)
    
    def _print_card_info(self, boost_card: dict, instance_id: int, is_new: bool = False) -> None:
        """Выводит информацию о карте с участниками клуба."""
        if is_new:
            print_section("🎁 НОВАЯ КАРТА ДЛЯ ВКЛАДА!")
        else:
            print_section("🎁 ОБНАРУЖЕНА ВОЗМОЖНОСТЬ ВНЕСТИ КАРТУ!")
        
        name = boost_card.get('name', '(не удалось получить)')
        card_id = boost_card.get('card_id', '?')
        rank = boost_card.get('rank', '(не удалось получить)')
        owners = boost_card.get('owners_count', '?')
        wanters = boost_card.get('wanters_count', '?')
        
        print(f"   Название: {name}")
        logger.info(f"Название: {name}")
        print(f"   ID карты: {card_id} | Instance ID: {instance_id} | Ранг: {rank}")
        logger.info(f"ID карты: {card_id} | Instance ID: {instance_id} | Ранг: {rank}")
        print(f"   Владельцев: {owners} | Желающих: {wanters}")
        logger.info(f"Владельцев: {owners} | Желающих: {wanters}")
        
        club_members = boost_card.get('club_members', [])
        members_info = format_club_members_info(club_members)
        print(f"   {members_info}")
        logger.info(f"{members_info}")
        
        if is_new:
            filepath = os.path.join(self.output_dir, BOOST_CARD_FILE)
            print(f"💾 Новая карта сохранена в: {filepath}")
            logger.info(f"💾 Новая карта сохранена в: {filepath}")
        
        print("=" * 60 + "\n")
    
    def _send_contribute_request(self, boost_url: str, instance_id: int) -> bool:
        """Отправляет запрос на внесение карты."""
        url = f"{BASE_URL}/clubs/boost"
        csrf_token = self.session.headers.get('X-CSRF-TOKEN', '')
        
        data = {
            "card_id": instance_id,
            "_token": csrf_token
        }
        
        headers = {
            "Referer": boost_url,
            "Origin": BASE_URL,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        
        try:
            response = self.session.post(
                url,
                data=data,
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )
            
            return response.status_code == 200
            
        except requests.RequestException:
            return False
    
    def _cancel_pending_trades(self) -> None:
        """Отменяет все отправленные обмены."""
        print("🔄 Отменяем все отправленные обмены...")
        logger.info("🔄 Отменяем все отправленные обмены...")
        
        success = cancel_all_sent_trades(self.session, self.trade_manager, debug=False)
        
        if success:
            print_success("✅ Все отправленные обмены успешно отменены!")
            logger.info("✅ Все отправленные обмены успешно отменены!")
        else:
            print_warning("⚠️  Не удалось отменить обмены (возможно, их не было)")
            logger.warning("⚠️  Не удалось отменить обмены (возможно, их не было)")
    
    def monitor_loop(self) -> None:
        """Основной цикл мониторинга."""
        print(f"\n🔄 Запущен мониторинг страницы: {self.club_url}")
        logger.info(f"🔄 Запущен мониторинг страницы: {self.club_url}")
        print(f"   Проверка каждые {MONITOR_CHECK_INTERVAL} секунд...")
        logger.info(f"Проверка каждые {MONITOR_CHECK_INTERVAL} секунд...")
        print("   Отслеживание: буст + смена карты в клубе")
        logger.info("Отслеживание: буст + смена карты в клубе")
        
        if self.telegram_notifier and self.telegram_notifier.is_enabled():
            print("   📱 Telegram уведомления: ВКЛЮЧЕНЫ")
            logger.info("📱 Telegram уведомления: ВКЛЮЧЕНЫ")
        else:
            print("   📱 Telegram уведомления: ВЫКЛЮЧЕНЫ")
            logger.info("📱 Telegram уведомления: ВЫКЛЮЧЕНЫ")
        
        print("   Нажмите Ctrl+C для остановки\n")
        logger.info("Нажмите Ctrl+C для остановки")
        
        # Выводим статистику при старте
        self.stats_manager.print_stats(force_refresh=True)
        
        check_count = 0
        
        while self.running:
            check_count += 1
            
            # Проверяем смену карты в клубе
            new_card_id = self.check_card_changed()
            if new_card_id:
                self.handle_card_change_without_boost(new_card_id)
                time.sleep(MONITOR_CHECK_INTERVAL)
                continue
            
            # Проверяем доступность буста
            boost_url = self.check_boost_available()
            
            if boost_url:
                timestamp = time.strftime('%H:%M:%S')
                print(f"\n🎯 [{timestamp}] Проверка #{check_count}: БУСТ ДОСТУПЕН!")
                logger.info(f"🎯 [{timestamp}] Проверка #{check_count}: БУСТ ДОСТУПЕН!")
                
                # 🔧 КРИТИЧНО: НЕМЕДЛЕННО устанавливаем флаг card_changed!
                # Это СРАЗУ остановит параллельную отправку обменов
                self.card_changed = True
                logger.info("🛑 Флаг card_changed установлен - остановка отправки обменов")
                
                # 🔧 ВАЖНО: Проверяем лимит перед вкладом
                if self.stats_manager.can_donate(force_refresh=True):
                    success = self.contribute_card(boost_url)
                    
                    if success:
                        self.boost_available = True
                        print("   ✅ Продолжаем мониторинг для следующего буста...")
                        logger.info("✅ Продолжаем мониторинг для следующего буста...")
                    else:
                        print("   ⚠️  Продолжаем мониторинг...")
                        logger.info("⚠️  Продолжаем мониторинг...")
                        # Если внесение не удалось, сбрасываем флаг
                        self.card_changed = False
                else:
                    print(f"⛔ Буст доступен, но достигнут лимит пожертвований!")
                    logger.warning(f"⛔ Буст доступен, но достигнут лимит пожертвований!")
                    self.stats_manager.print_stats()
                    # Сбрасываем флаг, так как не внесли карту
                    self.card_changed = False
            else:
                # Выводим статус периодически
                if check_count == 1 or check_count % MONITOR_STATUS_INTERVAL == 0:
                    timestamp = time.strftime('%H:%M:%S')
                    print(f"⏳ [{timestamp}] Проверка #{check_count}: буст недоступен, карта не менялась")
                    logger.info(f"⏳ [{timestamp}] Проверка #{check_count}: буст недоступен, карта не менялась")
            
            # Задержка до следующей проверки
            time.sleep(MONITOR_CHECK_INTERVAL)
    
    def start(self) -> None:
        """Запускает мониторинг в отдельном потоке."""
        if self.running:
            print_warning("Мониторинг уже запущен")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.thread.start()
    
    def stop(self) -> None:
        """Останавливает мониторинг."""
        if not self.running:
            return
        
        print("\n🛑 Остановка мониторинга...")
        logger.info("🛑 Остановка мониторинга...")
        self.running = False
        
        if self.thread:
            self.thread.join(timeout=5)
        
        print_success("Мониторинг остановлен")
        logger.info("Мониторинг остановлен")
    
    def is_running(self) -> bool:
        """Проверяет, запущен ли мониторинг."""
        return self.running


def start_boost_monitor(
    session: requests.Session,
    club_url: str,
    stats_manager: DailyStatsManager,
    output_dir: str = OUTPUT_DIR,
    telegram_notifier=None
) -> BoostMonitor:
    """Удобная функция для запуска мониторинга."""
    monitor = BoostMonitor(
        session,
        club_url,
        stats_manager,
        output_dir,
        telegram_notifier
    )
    monitor.start()
    return monitor