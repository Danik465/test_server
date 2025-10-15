import asyncio
import websockets
import json
import sys
import logging
import base64
import io
from PIL import ImageGrab, Image
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

    def capture_screen(self):
        """Улучшенный захват экрана"""
        try:
            # Захватываем скриншот
            screenshot = ImageGrab.grab()
            
            # Уменьшаем размер для производительности
            screenshot.thumbnail((800, 600), Image.Resampling.LANCZOS)
            
            # Конвертируем в base64 - используем PNG для лучшего качества
            buffer = io.BytesIO()
            screenshot.save(buffer, format='PNG')  # PNG вместо JPEG
            image_data = buffer.getvalue()
            
            self.logger.debug(f"📸 Скриншот захвачен, размер: {len(image_data)} байт")
            return base64.b64encode(image_data).decode('utf-8')
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка захвата экрана: {e}")
            return None

    async def send_screen_updates(self):
        """Отправка обновлений экрана"""
        self.logger.info("🔄 Начало передачи экрана")
        
        while self.screen_capturing and self.connected:
            try:
                start_time = time.time()
                
                screen_data = self.capture_screen()
                if screen_data and self.websocket:
                    await self.websocket.send(json.dumps({
                        "type": "screen_data",
                        "screen_data": screen_data,
                        "timestamp": start_time
                    }))
                    self.logger.debug(f"✅ Кадр отправлен, размер: {len(screen_data)}")
                elif not screen_data:
                    self.logger.warning("⚠️ Не удалось захватить экран")
                
                # Баланс FPS - 5 кадров в секунду для стабильности
                elapsed = time.time() - start_time
                sleep_time = max(0.2 - elapsed, 0.01)  # 5 FPS
                await asyncio.sleep(sleep_time)
                    
            except asyncio.CancelledError:
                self.logger.info("🛑 Передача экрана прервана")
                break
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("🔌 Соединение закрыто во время отправки экрана")
                break
            except Exception as e:
                self.logger.error(f"❌ Ошибка отправки экрана: {e}")
                await asyncio.sleep(0.5)

    async def execute_command(self, command, data=None):
        """Выполнение команд от управляющего клиента"""
        try:
            self.logger.info(f"🔧 Выполнение команды: {command}")
            
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
                screen_width, screen_height = pyautogui.size()
                scale_x = screen_width / 800
                scale_y = screen_height / 600
                
                x = int(data['x'] * scale_x)
                y = int(data['y'] * scale_y)
                
                pyautogui.moveTo(x, y, _pause=False)
                
            elif command == "mouse_click" and self.mouse_control:
                screen_width, screen_height = pyautogui.size()
                scale_x = screen_width / 800
                scale_y = screen_height / 600
                
                x = int(data['x'] * scale_x)
                y = int(data['y'] * scale_y)
                button = data.get('button', 'left')
                
                pyautogui.click(x, y, button=button, _pause=False)
                
            elif command == "mouse_down" and self.mouse_control:
                screen_width, screen_height = pyautogui.size()
                scale_x = screen_width / 800
                scale_y = screen_height / 600
                
                x = int(data['x'] * scale_x)
                y = int(data['y'] * scale_y)
                button = data.get('button', 'left')
                
                pyautogui.mouseDown(x, y, button=button, _pause=False)
                
            elif command == "mouse_up" and self.mouse_control:
                screen_width, screen_height = pyautogui.size()
                scale_x = screen_width / 800
                scale_y = screen_height / 600
                
                x = int(data['x'] * scale_x)
                y = int(data['y'] * scale_y)
                button = data.get('button', 'left')
                
                pyautogui.mouseUp(x, y, button=button, _pause=False)
                
            elif command == "key_press" and self.mouse_control:
                key = data['key']
                pyautogui.press(key, _pause=False)
                
            elif command == "key_down" and self.mouse_control:
                key = data['key']
                pyautogui.keyDown(key, _pause=False)
                
            elif command == "key_up" and self.mouse_control:
                key = data['key']
                pyautogui.keyUp(key, _pause=False)
                
            elif command == "type_write" and self.mouse_control:
                text = data['text']
                pyautogui.write(text, interval=0.01, _pause=False)
                
            else:
                if self.mouse_control:
                    await self.send_status(f"Получена команда: {command}")
                else:
                    await self.send_status(f"Команда {command} игнорируется (управление отключено)")
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка выполнения команды {command}: {e}")
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
                self.logger.error(f"❌ Ошибка отправки статуса: {e}")

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
                    max_size=10 * 1024 * 1024  # Увеличиваем лимит
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
                    await asyncio.sleep(2 ** attempt)
                    
        return False

    async def receive_commands(self):
        """Прием команд от сервера"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                
                if data["type"] == "execute_command":
                    await self.execute_command(data["command"], data.get("data"))
                    
                elif data["type"] == "error":
                    self.logger.error(f"❌ Ошибка от сервера: {data.get('message', '')}")
                    
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(f"🔌 Соединение с сервером закрыто: {e}")
            self.connected = False
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении команд: {e}")
            self.connected = False

    async def start(self, uri):
        """Основной цикл клиента"""
        if not await self.connect_to_server(uri):
            self.logger.error("❌ Не удалось подключиться к серверу")
            return
            
        print(f"\n✅ Управляемый клиент {self.client_id} запущен")
        print("💡 Ожидание команд от управляющего клиента...")
        print("⚠️  ВНИМАНИЕ: После активации управления ваш компьютер будет управляться удаленно!")
        print("-" * 50)
        
        try:
            await self.receive_commands()
        except Exception as e:
            self.logger.error(f"❌ Ошибка в основном цикле: {e}")
        finally:
            # Очистка ресурсов
            self.connected = False
            self.screen_capturing = False
            self.mouse_control = False
            
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