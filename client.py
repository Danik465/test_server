import socket
import threading
import sys

class RailwayChatClient:
    def __init__(self):
        self.client = None
        self.nickname = ""
        self.running = False
        
    def connect_to_server(self, domain, port=5555):
        """Подключение к серверу на Railway"""
        try:
            print(f"🔄 Подключение к {domain}:{port}...")
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client.connect((domain, port))
            
            # Получение запроса ника от сервера
            nickname_request = self.client.recv(1024).decode('utf-8')
            if nickname_request == "NICK":
                self.nickname = input("👤 Введите ваш никнейм: ")
                self.client.send(self.nickname.encode('utf-8'))
                
            # Получение подтверждения подключения
            response = self.client.recv(1024).decode('utf-8')
            print(f"\n{response}")
            
            self.running = True
            return True
            
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
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
                print("\n❌ Соединение с сервером потеряно")
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
                elif message.lower() == '/users':
                    # Можно добавить команду для просмотра пользователей
                    pass
                elif message.strip():
                    self.client.send(message.encode('utf-8'))
            except KeyboardInterrupt:
                print("\n🛑 Выход из чата...")
                self.running = False
                break
            except Exception as e:
                print(f"❌ Ошибка отправки сообщения: {e}")
                self.running = False
                break
                
    def start(self, domain, port=5555):
        """Запуск клиента"""
        if not self.connect_to_server(domain, port):
            return
            
        print("\n✅ Подключение успешно! Для выхода введите /quit")
        print("-" * 50)
        
        # Поток для получения сообщений
        receive_thread = threading.Thread(target=self.receive_messages)
        receive_thread.daemon = True
        receive_thread.start()
        
        # Основной поток для отправки сообщений
        self.send_messages()
        
        self.client.close()
        print("👋 Клиент завершил работу")

def main():
    print("=== 🚀 Чат-клиент для Railway ===")
    
    # Если переданы аргументы командной строки
    if len(sys.argv) >= 2:
        domain = sys.argv[1]
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 5555
    else:
        domain = input("Введите домен Railway (например: your-project.up.railway.app): ").strip()
        port = input("Введите порт (по умолчанию 5555): ").strip()
        port = int(port) if port else 5555
    
    client = RailwayChatClient()
    client.start(domain, port)

if __name__ == "__main__":
    main()