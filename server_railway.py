import asyncio
import websockets
import json
import logging
from datetime import datetime
import os
import socket

class WebSocketRemoteServer:
    def __init__(self):
        self.port = int(os.environ.get('PORT', 8080))
        self.host = "0.0.0.0"
        self.controller_client = None
        self.controlled_client = None
        self.setup_logging()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)

    async def handle_client(self, websocket):
        """Обработка нового клиента"""
        client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
        self.logger.info(f"🔗 Новый клиент подключился из {client_ip}")

        client_type = None
        client_id = None
        
        try:
            # Получаем тип клиента с таймаутом
            init_message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
            init_data = json.loads(init_message)
            client_type = init_data.get("type")
            client_id = init_data.get("client_id", "unknown")

            if client_type == "controller":
                if self.controller_client:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Управляющий клиент уже подключен"
                    }))
                    await websocket.close()
                    return
                self.controller_client = websocket
                self.logger.info(f"🎮 Подключен управляющий клиент: {client_id}")
                await websocket.send(json.dumps({
                    "type": "connection_established",
                    "role": "controller"
                }))

            elif client_type == "controlled":
                if self.controlled_client:
                    await websocket.send(json.dumps({
                        "type": "error", 
                        "message": "Управляемый клиент уже подключен"
                    }))
                    await websocket.close()
                    return
                self.controlled_client = websocket
                self.logger.info(f"🖥️ Подключен управляемый клиент: {client_id}")
                await websocket.send(json.dumps({
                    "type": "connection_established",
                    "role": "controlled"
                }))

                # Уведомляем управляющего
                if self.controller_client:
                    await self.controller_client.send(json.dumps({
                        "type": "controlled_connected",
                        "client_id": client_id
                    }))

            else:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Неизвестный тип клиента"
                }))
                await websocket.close()
                return

            # Основной цикл обработки сообщений
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.route_message(data, websocket, client_type)
                    
                except websockets.exceptions.ConnectionClosed:
                    break
                except json.JSONDecodeError as e:
                    self.logger.error(f"❌ Ошибка декодирования JSON от {client_type}: {e}")
                    continue
                except Exception as e:
                    self.logger.error(f"❌ Ошибка обработки сообщения от {client_type}: {e}")
                    continue

        except asyncio.TimeoutError:
            self.logger.warning(f"⏰ Таймаут инициализации клиента {client_ip}")
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.info(f"🔌 Клиент {client_type} отключился: {e}")
        except Exception as e:
            self.logger.error(f"❌ Неожиданная ошибка с клиентом {client_type}: {e}")
        finally:
            # Очистка при отключении
            if client_type == "controller" and websocket == self.controller_client:
                self.controller_client = None
                self.logger.info("🎮 Управляющий клиент отключен")
            elif client_type == "controlled" and websocket == self.controlled_client:
                self.controlled_client = None
                self.logger.info("🖥️ Управляемый клиент отключен")
                
                if self.controller_client:
                    await self.controller_client.send(json.dumps({
                        "type": "controlled_disconnected"
                    }))

    async def route_message(self, data, websocket, sender_type):
        """Маршрутизация сообщений между клиентами"""
        message_type = data.get("type")
        
        if sender_type == "controller" and message_type == "control_command":
            if self.controlled_client:
                await self.controlled_client.send(json.dumps({
                    "type": "execute_command",
                    "command": data.get("command"),
                    "data": data.get("data")
                }))
            else:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Нет подключенного управляемого клиента"
                }))
                
        elif sender_type == "controlled" and message_type == "screen_data":
            if self.controller_client:
                await self.controller_client.send(json.dumps({
                    "type": "screen_update",
                    "screen_data": data.get("screen_data"),
                    "timestamp": datetime.now().isoformat()
                }))
                
        elif sender_type == "controlled" and message_type == "status_update":
            if self.controller_client:
                await self.controller_client.send(json.dumps({
                    "type": "controlled_status",
                    "status": data.get("status"),
                    "info": data.get("info")
                }))

    async def start_server(self):
        """Запуск WebSocket сервера"""
        self.logger.info(f"🚀 Запуск сервера удаленного доступа")
        self.logger.info(f"📍 Хост: {self.host}, Порт: {self.port}")

        start_server = websockets.serve(
            self.handle_client, 
            self.host, 
            self.port,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5,
            max_size=10 * 1024 * 1024  # 10MB
        )
        
        async with start_server:
            self.logger.info("✅ Сервер удаленного доступа успешно запущен")
            await asyncio.Future()

if __name__ == "__main__":
    server = WebSocketRemoteServer()
    try:
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        print("\n🛑 Сервер остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка сервера: {e}")