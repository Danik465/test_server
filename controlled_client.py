import asyncio
import websockets
import json
import sys
import logging
import base64
import io
from PIL import ImageGrab
from datetime import datetime

class RemoteControlledClient:
    def __init__(self):
        self.websocket = None
        self.client_id = f"controlled_{datetime.now().strftime('%H%M%S')}"
        self.connected = False
        self.screen_capturing = False
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
        """Захват экрана и кодирование в base64"""
        try:
            screenshot = ImageGrab.grab()
            buffer = io.BytesIO()
            screenshot.save(buffer, format='JPEG', quality=50)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
        except Exception as e:
            self.logger.error(f"Ошибка захвата экрана: {e}")
            return None

    async def send_screen_updates(self):
        """Периодическая отправка обновлений экрана"""
        while self.screen_capturing and self.connected:
            try:
                screen_data = self.capture_screen()
                if screen_data and self.websocket:
                    await self.websocket.send(json.dumps({
                        "type": "screen_data",
                        "screen_data": screen_data
                    }))
                await asyncio.sleep(0.5)  # 2 FPS для снижения нагрузки
            except Exception as e:
                self.logger.error(f"Ошибка отправки экрана: {e}")
                break

    async def execute_command(self, command, data=None):
        """Выполнение команд от управляющего клиента"""
        try:
            if command == "capture_screen":
                if not self.screen_capturing:
                    self.screen_capturing = True
                    asyncio.create_task(self.send_screen_updates())
                    await self.send_status("Захват экрана активирован")
                    
            elif command == "toggle_mouse_control":
                # В этой версии просто подтверждаем команду
                await self.send_status("Управление мышью переключено")
                
            else:
                await self.send_status(f"Получена команда: {command}")
                
        except Exception as e:
            self.logger.error(f"Ошибка выполнения команды {command}: {e}")
            await self.send_status(f"Ошибка выполнения: {e}")

    async def send_status(self, status_message):
        """Отправка статуса управляющему"""
        if self.websocket:
            await self.websocket.send(json.dumps({
                "type": "status_update",
                "status": "info",
                "info": status_message
            }))

    async def connect_to_server(self, uri):
        try:
            self.logger.info(f"🔄 Подключение к {uri}...")
            self.websocket = await websockets.connect(
                uri,
                ping_interval=20,
                ping_timeout=10
            )
            
            # Отправляем идентификатор управляемого клиента
            await self.websocket.send(json.dumps({
                "type": "controlled",
                "client_id": self.client_id
            }))
            
            # Ждем подтверждения
            message = await self.websocket.recv()
            data = json.loads(message)
            
            if data.get("type") == "connection_established":
                self.connected = True
                self.logger.info("✅ Подключение к серверу установлено")
                await self.send_status("Управляемый клиент готов к работе")
                return True
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка подключения: {e}")
            return False

    async def receive_commands(self):
        try:
            async for message in self.websocket:
                data = json.loads(message)
                
                if data["type"] == "execute_command":
                    await self.execute_command(data["command"], data.get("data"))
                    
                elif data["type"] == "error":
                    self.logger.error(f"Ошибка от сервера: {data.get('message', '')}")
                    
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("🔌 Соединение с сервером закрыто")
            self.connected = False
            self.screen_capturing = False
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении команд: {e}")
            self.connected = False
            self.screen_capturing = False

    async def start(self, uri):
        if not await self.connect_to_server(uri):
            return
            
        print(f"\n✅ Управляемый клиент {self.client_id} запущен")
        print("💡 Ожидание команд от управляющего клиента...")
        print("-" * 50)
        
        try:
            await self.receive_commands()
        except Exception as e:
            self.logger.error(f"Ошибка в основном цикле: {e}")
        finally:
            self.connected = False
            self.screen_capturing = False
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