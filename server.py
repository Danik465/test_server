# server.py
import socket
import threading
import logging
from datetime import datetime

class ChatServer:
    def __init__(self, host='0.0.0.0', port=5555):
        self.host = host
        self.port = port
        self.clients = []
        self.nicknames = []
        self.setup_logging()
        
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('server.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def start_server(self):
        """Запуск сервера"""
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server.bind((self.host, self.port))
            self.server.listen()
            self.logger.info(f"Сервер запущен на {self.host}:{self.port}")
            self.logger.info("Ожидание подключений...")
            
            while True:
                client, address = self.server.accept()
                self.logger.info(f"Новое подключение от {address[0]}:{address[1]}")
                
                # Запрос ника от клиента
                client.send("NICK".encode('utf-8'))
                nickname = client.recv(1024).decode('utf-8')
                
                self.nicknames.append(nickname)
                self.clients.append(client)
                
                self.logger.info(f"Никнейм клиента: {nickname}")
                self.broadcast(f"{nickname} присоединился к чату!".encode('utf-8'))
                client.send("Подключение к серверу успешно!".encode('utf-8'))
                
                # Запуск потока для обработки сообщений от клиента
                thread = threading.Thread(target=self.handle_client, args=(client,))
                thread.daemon = True
                thread.start()
                
        except Exception as e:
            self.logger.error(f"Ошибка сервера: {e}")
        finally:
            self.stop_server()
            
    def handle_client(self, client):
        """Обработка сообщений от клиента"""
        while True:
            try:
                message = client.recv(1024)
                if not message:
                    break
                    
                # Логирование сообщения
                nickname = self.nicknames[self.clients.index(client)]
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.logger.info(f"[{timestamp}] {nickname}: {message.decode('utf-8')}")
                
                self.broadcast(message, nickname)
                
            except (ConnectionResetError, BrokenPipeError):
                self.remove_client(client)
                break
            except Exception as e:
                self.logger.error(f"Ошибка обработки сообщения: {e}")
                self.remove_client(client)
                break
                
    def broadcast(self, message, sender_nickname=None):
        """Отправка сообщения всем клиентам"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if sender_nickname:
            formatted_message = f"[{timestamp}] {sender_nickname}: {message.decode('utf-8')}"
            message = formatted_message.encode('utf-8')
        
        for client in self.clients[:]:
            try:
                client.send(message)
            except:
                self.remove_client(client)
                
    def remove_client(self, client):
        """Удаление клиента при отключении"""
        if client in self.clients:
            index = self.clients.index(client)
            nickname = self.nicknames[index]
            
            self.clients.remove(client)
            self.nicknames.remove(nickname)
            
            client.close()
            self.broadcast(f"{nickname} покинул чат.".encode('utf-8'))
            self.logger.info(f"Клиент {nickname} отключен")
            
    def stop_server(self):
        """Остановка сервера"""
        self.logger.info("Остановка сервера...")
        for client in self.clients:
            client.close()
        if hasattr(self, 'server'):
            self.server.close()
        self.logger.info("Сервер остановлен")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Chat Server')
    parser.add_argument('--host', default='192.168.0.83', help='Host address')
    parser.add_argument('--port', type=int, default=5555, help='Port number')
    
    args = parser.parse_args()
    
    server = ChatServer(args.host, args.port)
    
    try:
        server.start_server()
    except KeyboardInterrupt:
        server.logger.info("Сервер остановлен пользователем")
        server.stop_server()