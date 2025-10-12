# client.py
import socket
import threading
import time
import sys

class ChatClient:
    def __init__(self):
        self.client = None
        self.nickname = ""
        self.running = False
        
    def connect_to_server(self, host, port):
        """Подключение к серверу"""
        try:
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client.connect((host, port))
            
            # Получение запроса ника от сервера
            nickname_request = self.client.recv(1024).decode('utf-8')
            if nickname_request == "NICK":
                self.nickname = input("Введите ваш никнейм: ")
                self.client.send(self.nickname.encode('utf-8'))
                
            # Получение подтверждения подключения
            response = self.client.recv(1024).decode('utf-8')
            print(f"\n{response}")
            
            self.running = True
            return True
            
        except Exception as e:
            print(f"Ошибка подключения: {e}")
            return False
            
    def receive_messages(self):
        """Получение сообщений от сервера"""
        while self.running:
            try:
                message = self.client.recv(1024).decode('utf-8')
                if message:
                    print(f"\r{message}\nВы: ", end="")
                else:
                    break
            except:
                print("\nСоединение с сервером потеряно")
                self.running = False
                break
                
    def send_messages(self):
        """Отправка сообщений на сервер"""
        while self.running:
            try:
                message = input("Вы: ")
                if message.lower() == '/quit':
                    self.running = False
                    break
                elif message.strip():
                    self.client.send(message.encode('utf-8'))
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                print(f"Ошибка отправки сообщения: {e}")
                self.running = False
                break
                
    def start(self, host, port):
        """Запуск клиента"""
        print("Подключение к серверу...")
        if not self.connect_to_server(host, port):
            return
            
        print("\nПодключение успешно! Для выхода введите /quit")
        print("-" * 50)
        
        # Поток для получения сообщений
        receive_thread = threading.Thread(target=self.receive_messages)
        receive_thread.daemon = True
        receive_thread.start()
        
        # Основной поток для отправки сообщений
        self.send_messages()
        
        self.client.close()
        print("Клиент завершил работу")

def get_server_info():
    """Получение информации о сервере от пользователя"""
    print("=== Чат-клиент ===")
    
    # Если переданы аргументы командной строки
    if len(sys.argv) == 3:
        return sys.argv[1], int(sys.argv[2])
    
    host = input("Введите IP адрес сервера: ").strip()
    if not host:
        host = "localhost"
        
    port = input("Введите порт сервера (по умолчанию 5555): ").strip()
    if not port:
        port = 5555
    else:
        try:
            port = int(port)
        except ValueError:
            print("Неверный порт, используется порт по умолчанию 5555")
            port = 5555
            
    return host, port

if __name__ == "__main__":
    host, port = get_server_info()
    
    client = ChatClient()
    client.start(host, port)