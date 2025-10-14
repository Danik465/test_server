import asyncio
import websockets
import json
import sys
import logging
from datetime import datetime

class WebSocketChatClient:
    def __init__(self):
        self.websocket = None
        self.nickname = ""
        self.running = False
        self.setup_logging()
        
    def setup_logging(self):
        """Настройка логирования для клиента"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("client.log", encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("WebSocketClient")

    async def connect_to_server(self, uri):
        try:
            self.logger.info(f"🔄 Попытка подключения к {uri}...")
            
            # Увеличиваем таймаут и отключаем проверку SSL для Railway
            self.websocket = await websockets.connect(
                uri,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10,
                max_size=10**6  # 1MB
            )
            
            self.logger.info("✅ WebSocket соединение установлено")
            
            # Ждем запрос никнейма от сервера
            message = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            data = json.loads(message)
            
            if data.get("type") == "request_nickname":
                self.logger.info("📨 Получен запрос никнейма от сервера")
                self.nickname = input("👤 Введите ваш никнейм: ")
                await self.websocket.send(json.dumps({"nickname": self.nickname}))
                self.logger.info(f"👤 Никнейм '{self.nickname}' отправлен на сервер")
                
            self.running = True
            return True
            
        except asyncio.TimeoutError:
            self.logger.error("⏰ Таймаут при подключении к серверу")
            return False
        except websockets.exceptions.InvalidURI:
            self.logger.error("❌ Неверный URI сервера")
            return False
        except websockets.exceptions.WebSocketException as e:
            self.logger.error(f"❌ Ошибка WebSocket: {e}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Неожиданная ошибка подключения: {e}")
            return False

    async def receive_messages(self):
        try:
            self.logger.info("👂 Начало прослушивания сообщений от сервера")
            async for message in self.websocket:
                data = json.loads(message)
                
                if data["type"] == "chat_message":
                    timestamp = data["timestamp"][11:19]
                    print(f"\r[{timestamp}] {data['nickname']}: {data['message']}")
                    self.logger.info(f"💬 Получено сообщение от {data['nickname']}: {data['message']}")
                    
                elif data["type"] == "user_joined":
                    print(f"\r🌟 {data['message']}")
                    self.logger.info(f"👤 {data['message']}")
                    
                print("Вы: ", end="", flush=True)
                
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(f"🔌 Соединение с сервером закрыто: {e}")
            print("\n🔌 Соединение с сервером потеряно")
            self.running = False
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении сообщений: {e}")
            self.running = False

    async def send_messages(self):
        try:
            self.logger.info("📝 Начало обработки отправки сообщений")
            while self.running:
                message = await asyncio.get_event_loop().run_in_executor(None, input, "Вы: ")
                
                if message.lower() == '/quit':
                    self.logger.info("🚪 Запрошен выход из чата")
                    break
                elif message.lower() == '/status':
                    status = "подключен" if self.running else "отключен"
                    print(f"📊 Статус: {status}, Никнейм: {self.nickname}")
                    continue
                elif message.strip():
                    await self.websocket.send(json.dumps({
                        "type": "message",
                        "message": message
                    }))
                    self.logger.info(f"📤 Отправлено сообщение: {message}")
                    
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки сообщения: {e}")

    async def start(self, uri):
        self.logger.info(f"🚀 Запуск клиента с URI: {uri}")
        
        if not await self.connect_to_server(uri):
            self.logger.error("❌ Не удалось подключиться к серверу")
            return
            
        print("\n✅ Подключение успешно! Для выхода введите /quit")
        print("💡 Для проверки статуса введите /status")
        print("-" * 50)
        
        try:
            receive_task = asyncio.create_task(self.receive_messages())
            send_task = asyncio.create_task(self.send_messages())
            
            await asyncio.gather(receive_task, send_task, return_exceptions=True)
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка в основном цикле: {e}")
        finally:
            self.running = False
            if self.websocket:
                await self.websocket.close()
                self.logger.info("🔌 WebSocket соединение закрыто")
                
        self.logger.info("👋 Клиент завершил работу")
        print("👋 Клиент завершил работу")

def main():
    print("=== 🚀 WebSocket Чат-клиент ===")
    
    # Настройка логирования для main
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Main")
    
    try:
        if len(sys.argv) > 1:
            domain = sys.argv[1]
        else:
            domain = input("Введите домен или 'local' для локального подключения: ").strip()

        if domain.lower() == 'local':
            uri = "ws://127.0.0.1:8000"
            logger.info(f"🔧 Используется локальное подключение: {uri}")
        else:
            # Очистка домена от протоколов
            domain = domain.replace('http://', '').replace('https://', '').replace('ws://', '').replace('wss://', '')
            
            # Для Railway используем wss, но с отключенной проверкой SSL
            uri = f"wss://{domain}"
            logger.info(f"🌐 Используется удаленное подключение: {uri}")

        client = WebSocketChatClient()
        asyncio.run(client.start(uri))
        
    except KeyboardInterrupt:
        logger.info("🛑 Клиент остановлен пользователем")
        print("\n🛑 Клиент остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка клиента: {e}")
        print(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()