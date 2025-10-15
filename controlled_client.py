import asyncio
import websockets
import json
import sys
import logging
import base64
import io
import zlib
from PIL import ImageGrab, ImageChops, Image
import pyautogui
from datetime import datetime
import time

class RemoteControlledClient:
    def __init__(self):
        self.websocket = None
        self.client_id = f"controlled_{datetime.now().strftime('%H%M%S')}"
        self.connected = False
        self.screen_capturing = False
        self.mouse_control = False
        self.screen_task = None
        self.last_screenshot = None
        self.command_queue = asyncio.Queue()
        self.setup_logging()
        
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("controlled.log", encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("RemoteControlled")

    def capture_optimized_screen(self):
        """Оптимизированный захват экрана с дифференциальным сжатием"""
        try:
            # Захватываем скриншот
            screenshot = ImageGrab.grab()
            
            # Уменьшаем размер для производительности
            screenshot.thumbnail((1024, 768), Image.Resampling.LANCZOS)
            
            # Применяем дифференциальное сжатие
            if self.last_screenshot:
                # Сравниваем с предыдущим кадром
                diff = ImageChops.difference(screenshot, self.last_screenshot)
                
                # Если изменения минимальны, отправляем только разницу
                bbox = diff.getbbox()
                if bbox and (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) < 50000:  # Порог изменений
                    # Вырезаем измененную область
                    region = screenshot.crop(bbox)
                    buffer = io.BytesIO()
                    region.save(buffer, format='JPEG', quality=40, optimize=True)
                    compressed_data = buffer.getvalue()
                    
                    result = {
                        'type': 'diff',
                        'data': base64.b64encode(compressed_data).decode('utf-8'),
                        'bbox': bbox,
                        'full_size': screenshot.size
                    }
                    self.last_screenshot = screenshot.copy()
                    return result
            
            # Если изменений много или это первый кадр - отправляем полное изображение
            buffer = io.BytesIO()
            screenshot.save(buffer, format='JPEG', quality=40, optimize=True)
            compressed_data = zlib.compress(buffer.getvalue())  # Дополнительное сжатие
            
            result = {
                'type': 'full',
                'data': base64.b64encode(compressed_data).decode('utf-8'),
                'size': screenshot.size
            }
            self.last_screenshot = screenshot.copy()
            return result
            
        except Exception as e:
            self.logger.error(f"Ошибка захвата экрана: {e}")
            return None

    async def send_screen_updates(self):
        """Периодическая отправка обновлений экрана с ограничением FPS"""
        frame_count = 0
        last_time = time.time()
        
        while self.screen_capturing and self.connected:
            try:
                start_time = time.time()
                
                screen_data = self.capture_optimized_screen()
                if screen_data and self.websocket:
                    await self.websocket.send(json.dumps({
                        "type": "screen_data",
                        "screen_data": screen_data,
                        "frame_id": frame_count,
                        "timestamp": start_time
                    }))
                    frame_count += 1
                
                # Ограничиваем FPS до 5 кадров в секунду
                elapsed = time.time() - start_time
                sleep_time = max(0.2 - elapsed, 0)  # 5 FPS
                await asyncio.sleep(sleep_time)
                
                # Логируем FPS каждые 5 секунд
                if time.time() - last_time > 5:
                    current_fps = frame_count / (time.time() - last_time)
                    self.logger.debug(f"Текущий FPS: {current_fps:.1f}")
                    frame_count = 0
                    last_time = time.time()
                    
            except asyncio.CancelledError:
                break
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("Соединение закрыто во время отправки экрана")
                break
            except Exception as e:
                self.logger.error(f"Ошибка отправки экрана: {e}")
                await asyncio.sleep(1)  # Пауза при ошибках

    async def command_processor(self):
        """Обработчик команд с приоритетами"""
        while self.connected:
            try:
                # Берем команду из очереди с таймаутом
                command_data = await asyncio.wait_for(self.command_queue.get(), timeout=1.0)
                command, data = command_data
                
                await self.execute_command(command, data)
                self.command_queue.task_done()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"Ошибка в обработчике команд: {e}")

    async def execute_command(self, command, data=None):
        """Выполнение команд от управляющего клиента"""
        try:
            if command == "capture_screen":
                if not self.screen_capturing:
                    self.screen_capturing = True
                    self.screen_task = asyncio.create_task(self.send_screen_updates())
                    await self.send_status("Захват экрана активирован")
                    
            elif command == "stop_capture":
                if self.screen_capturing:
                    self.screen_capturing = False
                    if self.screen_task:
                        self.screen_task.cancel()
                        try:
                            await self.screen_task
                        except asyncio.CancelledError:
                            pass
                    await self.send_status("Захват экрана остановлен")
                    
            elif command == "toggle_mouse_control":
                self.mouse_control = not self.mouse_control
                status = "активировано" if self.mouse_control else "деактивировано"
                await self.send_status(f"Управление мышью {status}")
                
            elif command == "mouse_move" and self.mouse_control:
                # Получаем текущее разрешение экрана
                screen_width, screen_height = pyautogui.size()
                
                # Масштабируем координаты
                scale_x = screen_width / 1024  # Соответствует размеру скриншота
                scale_y = screen_height / 768
                
                x = int(data['x'] * scale_x)
                y = int(data['y'] * scale_y)
                
                pyautogui.moveTo(x, y, duration=0.05)  # Плавное движение
                
            elif command == "mouse_click" and self.mouse_control:
                screen_width, screen_height = pyautogui.size()
                scale_x = screen_width / 1024
                scale_y = screen_height / 768
                
                x = int(data['x'] * scale_x)
                y = int(data['y'] * scale_y)
                button = data.get('button', 'left')
                
                pyautogui.click(x, y, button=button)
                
            elif command == "mouse_down" and self.mouse_control:
                screen_width, screen_height = pyautogui.size()
                scale_x = screen_width / 1024
                scale_y = screen_height / 768
                
                x = int(data['x'] * scale_x)
                y = int(data['y'] * scale_y)
                button = data.get('button', 'left')
                
                pyautogui.mouseDown(x, y, button=button)
                
            elif command == "mouse_up" and self.mouse_control:
                screen_width, screen_height = pyautogui.size()
                scale_x = screen_width / 1024
                scale_y = screen_height / 768
                
                x = int(data['x'] * scale_x)
                y = int(data['y'] * scale_y)
                button = data.get('button', 'left')
                
                pyautogui.mouseUp(x, y, button=button)
                
            elif command == "key_press" and self.mouse_control:
                key = data['key']
                pyautogui.press(key)
                
            elif command == "key_down" and self.mouse_control:
                key = data['key']
                pyautogui.keyDown(key)
                
            elif command == "key_up" and self.mouse_control:
                key = data['key']
                pyautogui.keyUp(key)
                
            elif command == "type_write" and self.mouse_control:
                text = data['text']
                pyautogui.write(text, interval=0.05)  # Замедленный ввод
                
            else:
                await self.send_status(f"Команда {command} получена")
                
        except Exception as e:
            self.logger.error(f"Ошибка выполнения команды {command}: {e}")
            await self.send_status(f"Ошибка выполнения: {e}")

    async def send_status(self, status_message):
        """Отправка статуса управляющему"""
        if self.websocket and self.connected:
            try:
                await self.websocket.send(json.dumps({
                    "type": "status_update",
                    "status": "info",
                    "info": status_message
                }))
            except Exception as e:
                self.logger.error(f"Ошибка отправки статуса: {e}")

    async def connect_to_server(self, uri, max_retries=5):
        """Подключение к серверу с повторными попытками"""
        for attempt in range(max_retries):
            try:
                self.logger.info(f"🔄 Попытка подключения {attempt + 1}/{max_retries} к {uri}...")
                
                self.websocket = await websockets.connect(
                    uri,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=5,
                    max_size=10 * 1024 * 1024  # 10MB limit
                )
                
                # Отправляем идентификатор
                await self.websocket.send(json.dumps({
                    "type": "controlled",
                    "client_id": self.client_id
                }))
                
                # Ждем подтверждения
                message = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
                data = json.loads(message)
                
                if data.get("type") == "connection_established":
                    self.connected = True
                    self.logger.info("✅ Подключение к серверу установлено")
                    await self.send_status("Управляемый клиент готов к работе")
                    return True
                    
            except Exception as e:
                self.logger.error(f"❌ Ошибка подключения (попытка {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    
        return False

    async def receive_commands(self):
        """Прием команд от сервера"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                
                if data["type"] == "execute_command":
                    # Добавляем команду в очередь для обработки
                    await self.command_queue.put((data["command"], data.get("data")))
                    
                elif data["type"] == "error":
                    self.logger.error(f"Ошибка от сервера: {data.get('message', '')}")
                    
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(f"🔌 Соединение с сервером закрыто: {e}")
            self.connected = False
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении команд: {e}")
            self.connected = False

    async def start(self, uri):
        """Основной цикл клиента"""
        if not await self.connect_to_server(uri):
            self.logger.error("Не удалось подключиться к серверу")
            return
            
        print(f"\n✅ Управляемый клиент {self.client_id} запущен")
        print("💡 Ожидание команд от управляющего клиента...")
        print("⚠️  ВНИМАНИЕ: После активации управления ваш компьютер будет управляться удаленно!")
        print("-" * 50)
        
        # Запускаем обработчик команд
        command_handler = asyncio.create_task(self.command_processor())
        
        try:
            await self.receive_commands()
        except Exception as e:
            self.logger.error(f"Ошибка в основном цикле: {e}")
        finally:
            # Очистка ресурсов
            self.connected = False
            self.screen_capturing = False
            self.mouse_control = False
            
            command_handler.cancel()
            if self.screen_task:
                self.screen_task.cancel()
                
            if self.websocket:
                await self.websocket.close()
                
        self.logger.info("👋 Управляемый клиент завершил работу")

def main():
    print("=== 🖥️ Управляемый клиент ===")
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Main")
    
    try:
        if len(sys.argv) > 1:
            domain = sys.argv[1]
        else:
            domain = input("Введите домен сервера или 'local' для локального: ").strip()

        if domain.lower() == 'local':
            uri = "ws://127.0.0.1:8000"
            logger.info(f"🔧 Локальное подключение: {uri}")
        else:
            domain = domain.replace('http://', '').replace('https://', '').replace('ws://', '').replace('wss://', '')
            uri = f"wss://{domain}"
            logger.info(f"🌐 Удаленное подключение: {uri}")

        client = RemoteControlledClient()
        asyncio.run(client.start(uri))
        
    except KeyboardInterrupt:
        logger.info("🛑 Клиент остановлен пользователем")
        print("\n🛑 Клиент остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        print(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()