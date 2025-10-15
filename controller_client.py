import asyncio
import websockets
import json
import sys
import logging
import base64
import tkinter as tk
from PIL import Image, ImageTk
import io
from datetime import datetime
import threading
import queue

class RemoteControllerClient:
    def __init__(self):
        self.websocket = None
        self.client_id = f"controller_{datetime.now().strftime('%H%M%S')}"
        self.connected = False
        self.screen_window = None
        self.control_window = None
        self.asyncio_thread = None
        self.message_queue = queue.Queue()
        self.setup_logging()
        
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("controller.log", encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("RemoteController")

    def create_control_window(self):
        """Создание окна управления"""
        self.control_window = tk.Tk()
        self.control_window.title(f"Удаленное управление - {self.client_id}")
        self.control_window.geometry("400x300")
        self.control_window.protocol("WM_DELETE_WINDOW", self.quit_app)
        
        # Статус
        self.status_label = tk.Label(self.control_window, text="Статус: Отключен", fg="red")
        self.status_label.pack(pady=10)
        
        # Информация
        self.info_text = tk.Text(self.control_window, height=10, width=50)
        self.info_text.pack(pady=10)
        self.info_text.insert(tk.END, "Подключитесь к серверу для начала управления\n")
        
        # Кнопки управления
        button_frame = tk.Frame(self.control_window)
        button_frame.pack(pady=10)
        
        self.screen_btn = tk.Button(button_frame, text="Запросить экран", 
                                   command=self.request_screen, state=tk.DISABLED)
        self.screen_btn.pack(side=tk.LEFT, padx=5)
        
        self.mouse_btn = tk.Button(button_frame, text="Управление мышью", 
                                  command=self.toggle_mouse_control, state=tk.DISABLED)
        self.mouse_btn.pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="Выход", command=self.quit_app).pack(side=tk.LEFT, padx=5)
        
        # Окно для отображения экрана
        self.screen_window = tk.Toplevel(self.control_window)
        self.screen_window.title("Экран удаленного компьютера")
        self.screen_window.geometry("800x600")
        self.screen_label = tk.Label(self.screen_window)
        self.screen_label.pack(fill=tk.BOTH, expand=True)
        self.screen_window.protocol("WM_DELETE_WINDOW", lambda: self.screen_window.withdraw())
        self.screen_window.withdraw()

        # Запускаем обработку сообщений из очереди
        self.process_messages()

    def process_messages(self):
        """Обработка сообщений из очереди (вызывается периодически)"""
        try:
            while True:
                message = self.message_queue.get_nowait()
                self.handle_async_message(message)
        except queue.Empty:
            pass
        finally:
            # Планируем следующую проверку через 100мс
            if self.control_window:
                self.control_window.after(100, self.process_messages)

    def handle_async_message(self, message):
        """Обработка сообщений из асинхронного потока"""
        msg_type = message.get("type")
        
        if msg_type == "screen_update":
            self.log_info("📸 Получен обновленный экран")
            self.display_screen(message["screen_data"])
            
        elif msg_type == "controlled_connected":
            self.log_info("🖥️ Управляемый клиент подключен")
            
        elif msg_type == "controlled_disconnected":
            self.log_info("🔌 Управляемый клиент отключен")
            self.screen_window.withdraw()
            
        elif msg_type == "controlled_status":
            self.log_info(f"📊 Статус управляемого: {message.get('info', '')}")
            
        elif msg_type == "connection_status":
            self.update_status(message["message"], message["connected"])
            
        elif msg_type == "error":
            self.log_info(f"❌ Ошибка: {message.get('message', '')}")

    def update_status(self, message, is_connected=False):
        """Обновление статуса подключения"""
        self.connected = is_connected
        status_text = "Статус: Подключен" if is_connected else "Статус: Отключен"
        self.status_label.config(text=status_text, 
                               fg="green" if is_connected else "red")
        
        self.screen_btn.config(state=tk.NORMAL if is_connected else tk.DISABLED)
        self.mouse_btn.config(state=tk.NORMAL if is_connected else tk.DISABLED)
        
        self.log_info(message)

    def log_info(self, message):
        """Добавление информации в лог"""
        if hasattr(self, 'info_text'):
            self.info_text.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} - {message}\n")
            self.info_text.see(tk.END)

    def display_screen(self, screen_data):
        """Отображение полученного скриншота"""
        try:
            # Декодируем base64 изображение
            image_data = base64.b64decode(screen_data)
            image = Image.open(io.BytesIO(image_data))
            
            # Масштабируем для окна
            image.thumbnail((800, 600), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            
            self.screen_label.config(image=photo)
            self.screen_label.image = photo
            
            if not self.screen_window.winfo_viewable():
                self.screen_window.deiconify()
                
        except Exception as e:
            self.logger.error(f"Ошибка отображения экрана: {e}")

    def request_screen(self):
        """Запрос скриншота с управляемого клиента"""
        if self.connected:
            # Отправляем команду через очередь в asyncio поток
            asyncio.run_coroutine_threadsafe(
                self.send_command("capture_screen"), 
                self.asyncio_loop
            )
            self.log_info("Запрос скриншота отправлен")

    def toggle_mouse_control(self):
        """Включение/выключение управления мышью"""
        if self.connected:
            asyncio.run_coroutine_threadsafe(
                self.send_command("toggle_mouse_control"), 
                self.asyncio_loop
            )
            self.log_info("Команда управления мышью отправлена")

    async def send_command(self, command, data=None):
        """Отправка команды управляемому клиенту"""
        if self.websocket:
            await self.websocket.send(json.dumps({
                "type": "control_command",
                "command": command,
                "data": data
            }))

    async def connect_to_server(self, uri):
        try:
            self.logger.info(f"🔄 Подключение к {uri}...")
            self.websocket = await websockets.connect(
                uri,
                ping_interval=20,
                ping_timeout=10
            )
            
            # Отправляем идентификатор управляющего клиента
            await self.websocket.send(json.dumps({
                "type": "controller",
                "client_id": self.client_id
            }))
            
            # Ждем подтверждения
            message = await self.websocket.recv()
            data = json.loads(message)
            
            if data.get("type") == "connection_established":
                self.message_queue.put({
                    "type": "connection_status",
                    "message": "✅ Подключение к серверу установлено",
                    "connected": True
                })
                return True
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка подключения: {e}")
            self.message_queue.put({
                "type": "connection_status",
                "message": f"❌ Ошибка подключения: {e}",
                "connected": False
            })
            return False

    async def receive_messages(self):
        try:
            async for message in self.websocket:
                data = json.loads(message)
                # Помещаем сообщение в очередь для обработки в главном потоке
                self.message_queue.put(data)
                    
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("🔌 Соединение с сервером закрыто")
            self.message_queue.put({
                "type": "connection_status",
                "message": "🔌 Соединение с сервером потеряно",
                "connected": False
            })
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении сообщений: {e}")
            self.message_queue.put({
                "type": "connection_status", 
                "message": f"❌ Ошибка: {e}",
                "connected": False
            })

    async def async_main(self, uri):
        """Асинхронная основная функция"""
        self.asyncio_loop = asyncio.get_running_loop()
        
        if not await self.connect_to_server(uri):
            return
            
        await self.receive_messages()

    def start_async_thread(self, uri):
        """Запуск асинхронного кода в отдельном потоке"""
        def run_async():
            asyncio.run(self.async_main(uri))
        
        self.asyncio_thread = threading.Thread(target=run_async, daemon=True)
        self.asyncio_thread.start()

    def start(self, uri):
        """Запуск приложения"""
        self.create_control_window()
        self.start_async_thread(uri)
        
        # Запускаем главный цикл Tkinter
        try:
            self.control_window.mainloop()
        except Exception as e:
            self.logger.error(f"Ошибка GUI: {e}")
        finally:
            self.quit_app()

    def quit_app(self):
        """Выход из приложения"""
        if self.websocket:
            # Закрываем WebSocket соединение
            asyncio.run_coroutine_threadsafe(
                self.websocket.close(),
                self.asyncio_loop
            )
        
        if self.control_window:
            self.control_window.quit()
            self.control_window.destroy()

def main():
    print("=== 🎮 Клиент удаленного управления ===")
    
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

        client = RemoteControllerClient()
        client.start(uri)
        
    except KeyboardInterrupt:
        logger.info("🛑 Клиент остановлен пользователем")
        print("\n🛑 Клиент остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        print(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()