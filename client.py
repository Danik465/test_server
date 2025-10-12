import asyncio
import websockets
import json
import sys

class WebSocketChatClient:
    def __init__(self):
        self.websocket = None
        self.nickname = ""
        self.running = False
        
    async def connect_to_server(self, uri):
        """Подключение к WebSocket серверу"""
        try:
            print(f"🔄 Подключение к {uri}...")
            self.websocket = await websockets.connect(uri)
            
            # Получаем запрос ника
            message = await self.websocket.recv()
            data = json.loads(message)
            
            if data.get("type") == "request_nickname":
                self.nickname = input("👤 Введите ваш никнейм: ")
                await self.websocket.send(json.dumps({"nickname": self.nickname}))
            
            self.running = True
            return True
            
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False
            
    async def receive_messages(self):
        """Получение сообщений от сервера"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                
                if data["type"] == "chat_message":
                    timestamp = data["timestamp"][11:19]  # Берем только время
                    print(f"\r[{timestamp}] {data['nickname']}: {data['message']}")
                elif data["type"] == "user_joined":
                    print(f"\r🌟 {data['message']}")
                    
                print("Вы: ", end="", flush=True)
                
        except websockets.exceptions.ConnectionClosed:
            print("\n🔌 Соединение с сервером потеряно")
            self.running = False
            
    async def send_messages(self):
        """Отправка сообщений на сервер"""
        try:
            while self.running:
                message = await asyncio.get_event_loop().run_in_executor(
                    None, input, "Вы: "
                )
                
                if message.lower() == '/quit':
                    break
                elif message.strip():
                    await self.websocket.send(json.dumps({
                        "type": "message",
                        "message": message
                    }))
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            
    async def start(self, uri):
        """Запуск клиента"""
        if not await self.connect_to_server(uri):
            return
            
        print("\n✅ Подключение успешно! Для выхода введите /quit")
        print("-" * 50)
        
        # Запускаем задачи параллельно
        receive_task = asyncio.create_task(self.receive_messages())
        send_task = asyncio.create_task(self.send_messages())
        
        # Ждем завершения одной из задач
        await asyncio.gather(receive_task, send_task, return_exceptions=True)
        
        await self.websocket.close()
        print("👋 Клиент завершил работу")

def main():
    print("=== 🚀 WebSocket Чат-клиент ===")
    
    if len(sys.argv) > 1:
        domain = sys.argv[1]
    else:
        domain = input("Введите домен Railway (без http://): ").strip()
    
    # Формируем WebSocket URI
    if domain.startswith('http://'):
        domain = domain[7:]
    if domain.startswith('https://'):
        domain = domain[8:]
    
    # Для Railway используем wss://
    uri = f"wss://{domain}"
    
    client = WebSocketChatClient()
    asyncio.run(client.start(uri))

if __name__ == "__main__":
    main()