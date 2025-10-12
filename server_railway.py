import asyncio
import websockets
import json
import logging
from datetime import datetime
import os

class WebSocketChatServer:
    def __init__(self):
        self.port = int(os.environ.get('PORT', 8000))
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
        self.clients.add(websocket)
        self.logger.info(f"🔗 Новый клиент подключился. Всего клиентов: {len(self.clients)}")
        
        try:
            # Получаем никнейм
            await websocket.send(json.dumps({"type": "request_nickname"}))
            nickname_message = await websocket.recv()
            nickname_data = json.loads(nickname_message)
            nickname = nickname_data.get("nickname", "Anonymous")
            
            # Уведомляем всех о новом пользователе
            join_message = {
                "type": "user_joined",
                "nickname": nickname,
                "timestamp": datetime.now().isoformat(),
                "message": f"{nickname} присоединился к чату!"
            }
            await self.broadcast(join_message)
            
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
                except json.JSONDecodeError:
                    continue
                    
        except websockets.exceptions.ConnectionClosed:
            self.logger.info("🔌 Соединение закрыто")
        finally:
            self.clients.remove(websocket)
            self.logger.info(f"👋 Клиент отключен. Осталось клиентов: {len(self.clients)}")
            
    async def broadcast(self, message):
        """Отправка сообщения всем клиентам"""
        if self.clients:
            message_json = json.dumps(message)
            await asyncio.gather(
                *[client.send(message_json) for client in self.clients],
                return_exceptions=True
            )
            
    async def start_server(self):
        """Запуск WebSocket сервера"""
        self.logger.info(f"🚀 WebSocket сервер запущен на порту {self.port}")
        self.logger.info("📢 Ожидание WebSocket подключений...")
        
        async with websockets.serve(self.handle_client, "0.0.0.0", self.port):
            await asyncio.Future()  # Бесконечный цикл

if __name__ == "__main__":
    server = WebSocketChatServer()
    asyncio.run(server.start_server())