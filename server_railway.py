import asyncio
import websockets
import json
import logging
from datetime import datetime
import os
import socket
import ssl

class WebSocketChatServer:
    def __init__(self):
        self.port = int(os.environ.get('PORT', 8000))
        self.host = "0.0.0.0"
        self.clients = set()
        self.setup_logging()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)

    async def handle_client(self, websocket, path):
        """Обработка нового клиента"""
        client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
        self.clients.add(websocket)
        self.logger.info(f"🔗 Новый клиент подключился из {client_ip}. Всего клиентов: {len(self.clients)}")

        nickname = "Anonymous"
        
        try:
            # Получаем никнейм
            await websocket.send(json.dumps({"type": "request_nickname"}))
            self.logger.info(f"📨 Отправлен запрос никнейма клиенту {client_ip}")
            
            nickname_message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
            nickname_data = json.loads(nickname_message)
            nickname = nickname_data.get("nickname", "Anonymous")
            
            self.logger.info(f"👤 Клиент {client_ip} установил никнейм: {nickname}")

            # Уведомляем всех о новом пользователе
            join_message = {
                "type": "user_joined",
                "nickname": nickname,
                "timestamp": datetime.now().isoformat(),
                "message": f"{nickname} присоединился к чату!"
            }
            await self.broadcast(join_message)
            self.logger.info(f"📢 Уведомление о присоединении {nickname} отправлено всем клиентам")

            # Основной цикл обработки сообщений
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get("type") == "message":
                        chat_message = {
                            "type": "chat_message",
                            "nickname": nickname,
                            "message": data["message"],
                            "timestamp": datetime.now().isoformat()
                        }
                        self.logger.info(f"💬 {nickname}: {data['message']}")
                        await self.broadcast(chat_message)
                except json.JSONDecodeError as e:
                    self.logger.error(f"❌ Ошибка декодирования JSON от {nickname}: {e}")
                    continue
                except Exception as e:
                    self.logger.error(f"❌ Ошибка обработки сообщения от {nickname}: {e}")
                    continue

        except asyncio.TimeoutError:
            self.logger.warning(f"⏰ Таймаут ожидания никнейма от клиента {client_ip}")
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.info(f"🔌 Клиент {nickname} отключился: {e}")
        except Exception as e:
            self.logger.error(f"❌ Неожиданная ошибка с клиентом {nickname}: {e}")
        finally:
            if websocket in self.clients:
                self.clients.remove(websocket)
            self.logger.info(f"👋 Клиент {nickname} отключен. Осталось клиентов: {len(self.clients)}")

    async def broadcast(self, message):
        """Отправка сообщения всем клиентам"""
        if self.clients:
            message_json = json.dumps(message)
            disconnected_clients = []
            
            for client in self.clients:
                try:
                    await client.send(message_json)
                except websockets.exceptions.ConnectionClosed:
                    disconnected_clients.append(client)
                except Exception as e:
                    self.logger.error(f"❌ Ошибка отправки сообщения клиенту: {e}")
                    disconnected_clients.append(client)
            
            # Удаляем отключенных клиентов
            for client in disconnected_clients:
                if client in self.clients:
                    self.clients.remove(client)
                    
            if disconnected_clients:
                self.logger.info(f"🧹 Удалено отключенных клиентов: {len(disconnected_clients)}")

    def detect_environment(self):
        """Определяет, работает ли сервер на Railway или локально"""
        if "RAILWAY_ENVIRONMENT" in os.environ or "PORT" in os.environ:
            return "railway"
        return "local"

    def get_local_ip(self):
        """Определяет локальный IP"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    async def start_server(self):
        """Запуск WebSocket сервера"""
        env = self.detect_environment()
        self.logger.info(f"🌐 Среда запуска: {env.upper()}")
        self.logger.info(f"📍 Хост: {self.host}, Порт: {self.port}")

        if env == "local":
            ip = self.get_local_ip()
            self.logger.info(f"🖥  Сервер запущен локально на ws://{ip}:{self.port}")
            self.logger.info(f"💡 Подключайтесь с этого устройства по ws://127.0.0.1:{self.port}")
        else:
            self.logger.info(f"🚀 Railway сервер запущен на порту {self.port}")
            self.logger.info("💡 Для подключения используйте домен Railway с протоколом wss://")

        self.logger.info("📢 Ожидание WebSocket подключений...")

        # На Railway SSL обрабатывается на уровне прокси, поэтому запускаем без SSL
        start_server = websockets.serve(
            self.handle_client, 
            self.host, 
            self.port,
            ping_interval=20,
            ping_timeout=10
        )
        
        async with start_server:
            self.logger.info("✅ WebSocket сервер успешно запущен")
            await asyncio.Future()  # вечный цикл

if __name__ == "__main__":
    server = WebSocketChatServer()
    try:
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        print("\n🛑 Сервер остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка сервера: {e}")