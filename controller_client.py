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
import time

class RemoteControllerClient:
    def __init__(self):
        self.websocket = None
        self.client_id = f"controller_{datetime.now().strftime('%H%M%S')}"
        self.connected = False
        self.screen_window = None
        self.control_window = None
        self.asyncio_thread = None
        self.message_queue = queue.Queue()
        self.mouse_control_enabled = False
        self.last_mouse_time = 0
        self.mouse_throttle = 0.033
        
        # Параметры масштабирования
        self.scale_params = {
            'offset_x': 0,
            'offset_y': 0,
            'scaled_width': 1920,
            'scaled_height': 1080,
            'scale_ratio': 1.0
        }
        
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
        self.control_window.geometry("500x400")
        self.control_window.protocol("WM_DELETE_WINDOW", self.quit_app)
        
        # Статус
        status_frame = tk.Frame(self.control_window)
        status_frame.pack(pady=10, fill=tk.X)
        
        self.status_label = tk.Label(status_frame, text="Статус: Отключен", fg="red", font=("Arial", 12))
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Информация о режиме
        mode_label = tk.Label(status_frame, text="Режим: Весь экран", fg="green", font=("Arial", 10))
        mode_label.pack(side=tk.RIGHT, padx=10)
        
        # Информация
        info_frame = tk.Frame(self.control_window)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tk.Label(info_frame, text="Лог событий:", font=("Arial", 10)).pack(anchor=tk.W)
        self.info_text = tk.Text(info_frame, height=12, width=60)
        scrollbar = tk.Scrollbar(info_frame, command=self.info_text.yview)
        self.info_text.config(yscrollcommand=scrollbar.set)
        self.info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.info_text.insert(tk.END, "Подключитесь к серверу для начала управления\n")
        self.info_text.insert(tk.END, "Режим: Отображение ВСЕГО экрана управляемого компьютера\n")
        self.info_text.insert(tk.END, "Все элементы интерфейса будут видны\n")
        
        # Кнопки управления
        button_frame = tk.Frame(self.control_window)
        button_frame.pack(pady=10)
        
        self.screen_btn = tk.Button(button_frame, text="🖥️ Запросить экран", 
                                   command=self.request_screen, state=tk.DISABLED,
                                   width=15, height=2)
        self.screen_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_screen_btn = tk.Button(button_frame, text="⏹️ Остановить экран", 
                                       command=self.stop_screen, state=tk.DISABLED,
                                       width=15, height=2)
        self.stop_screen_btn.pack(side=tk.LEFT, padx=5)
        
        self.mouse_btn = tk.Button(button_frame, text="🐭 Включить управление", 
                                  command=self.toggle_mouse_control, state=tk.DISABLED,
                                  width=15, height=2)
        self.mouse_btn.pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="🔴 Выход", command=self.quit_app,
                 width=10, height=2, bg="red", fg="white").pack(side=tk.LEFT, padx=5)
        
        # Окно для отображения экрана
        self.screen_window = tk.Toplevel(self.control_window)
        self.screen_window.title("Экран удаленного компьютера - Режим: Весь экран")
        self.screen_window.geometry("1920x1080")
        
        # Используем Canvas для отображения
        screen_frame = tk.Frame(self.screen_window)
        screen_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.screen_canvas = tk.Canvas(screen_frame, bg="black", width=1920, height=1080)
        self.screen_canvas.pack(fill=tk.BOTH, expand=True)
        
        self.screen_window.protocol("WM_DELETE_WINDOW", lambda: self.screen_window.withdraw())
        self.screen_window.withdraw()

        self.bind_control_events()
        self.process_messages()

    def bind_control_events(self):
        """Привязка событий мыши и клавиатуры"""
        if not self.screen_window:
            return
            
        # События мыши на Canvas
        self.screen_canvas.bind("<Motion>", self.on_mouse_move)
        self.screen_canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.screen_canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.screen_canvas.bind("<ButtonPress-3>", self.on_right_mouse_down)
        self.screen_canvas.bind("<ButtonRelease-3>", self.on_right_mouse_up)
        self.screen_canvas.bind("<Double-Button-1>", self.on_double_click)
        
        # События клавиатуры
        self.screen_window.bind("<KeyPress>", self.on_key_press)
        self.screen_window.bind("<KeyRelease>", self.on_key_release)
        
        self.screen_canvas.focus_set()

    def is_point_in_image(self, x, y):
        """Проверяет, находится ли точка в области изображения (не в черных полосах)"""
        return (self.scale_params['offset_x'] <= x < self.scale_params['offset_x'] + self.scale_params['scaled_width'] and
                self.scale_params['offset_y'] <= y < self.scale_params['offset_y'] + self.scale_params['scaled_height'])

    def on_mouse_move(self, event):
        """Обработка движения мыши"""
        current_time = time.time()
        if (self.mouse_control_enabled and self.connected and 
            (current_time - self.last_mouse_time) >= self.mouse_throttle):
            
            self.last_mouse_time = current_time
            
            # Проверяем, находится ли курсор в области изображения
            if self.is_point_in_image(event.x, event.y):
                # Добавляем параметры масштабирования к данным мыши
                mouse_data = {
                    "x": event.x,
                    "y": event.y,
                    "scale_ratio": self.scale_params['scale_ratio'],
                    "offset_x": self.scale_params['offset_x'],
                    "offset_y": self.scale_params['offset_y'],
                    "scaled_width": self.scale_params['scaled_width'],
                    "scaled_height": self.scale_params['scaled_height']
                }
                
                asyncio.run_coroutine_threadsafe(
                    self.send_command("mouse_move", mouse_data), 
                    self.asyncio_loop
                )

    def on_mouse_down(self, event):
        """Левый клик мыши - нажатие"""
        if self.mouse_control_enabled and self.connected:
            if self.is_point_in_image(event.x, event.y):
                mouse_data = {
                    "x": event.x,
                    "y": event.y,
                    "button": "left",
                    "scale_ratio": self.scale_params['scale_ratio'],
                    "offset_x": self.scale_params['offset_x'],
                    "offset_y": self.scale_params['offset_y'],
                    "scaled_width": self.scale_params['scaled_width'],
                    "scaled_height": self.scale_params['scaled_height']
                }
                
                asyncio.run_coroutine_threadsafe(
                    self.send_command("mouse_down", mouse_data), 
                    self.asyncio_loop
                )

    def on_mouse_up(self, event):
        """Левый клик мыши - отпускание"""
        if self.mouse_control_enabled and self.connected:
            if self.is_point_in_image(event.x, event.y):
                mouse_data = {
                    "x": event.x,
                    "y": event.y,
                    "button": "left",
                    "scale_ratio": self.scale_params['scale_ratio'],
                    "offset_x": self.scale_params['offset_x'],
                    "offset_y": self.scale_params['offset_y'],
                    "scaled_width": self.scale_params['scaled_width'],
                    "scaled_height": self.scale_params['scaled_height']
                }
                
                asyncio.run_coroutine_threadsafe(
                    self.send_command("mouse_up", mouse_data), 
                    self.asyncio_loop
                )

    def on_right_mouse_down(self, event):
        """Правый клик мыши - нажатие"""
        if self.mouse_control_enabled and self.connected:
            if self.is_point_in_image(event.x, event.y):
                mouse_data = {
                    "x": event.x,
                    "y": event.y,
                    "button": "right",
                    "scale_ratio": self.scale_params['scale_ratio'],
                    "offset_x": self.scale_params['offset_x'],
                    "offset_y": self.scale_params['offset_y'],
                    "scaled_width": self.scale_params['scaled_width'],
                    "scaled_height": self.scale_params['scaled_height']
                }
                
                asyncio.run_coroutine_threadsafe(
                    self.send_command("mouse_down", mouse_data), 
                    self.asyncio_loop
                )

    def on_right_mouse_up(self, event):
        """Правый клик мыши - отпускание"""
        if self.mouse_control_enabled and self.connected:
            if self.is_point_in_image(event.x, event.y):
                mouse_data = {
                    "x": event.x,
                    "y": event.y,
                    "button": "right",
                    "scale_ratio": self.scale_params['scale_ratio'],
                    "offset_x": self.scale_params['offset_x'],
                    "offset_y": self.scale_params['offset_y'],
                    "scaled_width": self.scale_params['scaled_width'],
                    "scaled_height": self.scale_params['scaled_height']
                }
                
                asyncio.run_coroutine_threadsafe(
                    self.send_command("mouse_up", mouse_data), 
                    self.asyncio_loop
                )

    def on_double_click(self, event):
        """Двойной клик"""
        if self.mouse_control_enabled and self.connected:
            if self.is_point_in_image(event.x, event.y):
                mouse_data = {
                    "x": event.x,
                    "y": event.y,
                    "button": "left",
                    "scale_ratio": self.scale_params['scale_ratio'],
                    "offset_x": self.scale_params['offset_x'],
                    "offset_y": self.scale_params['offset_y'],
                    "scaled_width": self.scale_params['scaled_width'],
                    "scaled_height": self.scale_params['scaled_height']
                }
                
                asyncio.run_coroutine_threadsafe(
                    self.send_command("mouse_click", mouse_data), 
                    self.asyncio_loop
                )

    def on_key_press(self, event):
        """Нажатие клавиши"""
        if self.mouse_control_enabled and self.connected:
            key = event.keysym
            special_keys = {
                "Return": "enter", "space": "space", "BackSpace": "backspace",
                "Escape": "esc", "Tab": "tab", "Delete": "delete",
                "Home": "home", "End": "end", "Page_Up": "pageup", 
                "Page_Down": "pagedown", "Left": "left", "Right": "right",
                "Up": "up", "Down": "down"
            }
            
            if key in special_keys:
                asyncio.run_coroutine_threadsafe(
                    self.send_command("key_press", {"key": special_keys[key]}), 
                    self.asyncio_loop
                )
            elif len(key) == 1 and key.isprintable():
                asyncio.run_coroutine_threadsafe(
                    self.send_command("key_press", {"key": key.lower()}), 
                    self.asyncio_loop
                )

    def on_key_release(self, event):
        """Отпускание клавиши"""
        pass

    def process_messages(self):
        """Обработка сообщений из очереди"""
        try:
            while True:
                message = self.message_queue.get_nowait()
                self.handle_async_message(message)
        except queue.Empty:
            pass
        finally:
            if self.control_window:
                self.control_window.after(50, self.process_messages)

    def handle_async_message(self, message):
        """Обработка сообщений из асинхронного потока"""
        msg_type = message.get("type")
        
        if msg_type == "screen_update":
            self.log_info("📸 Получены данные ВСЕГО экрана")
            self.display_screen(message)
            
        elif msg_type == "controlled_connected":
            self.log_info("🖥️ Управляемый клиент подключен")
            
        elif msg_type == "controlled_disconnected":
            self.log_info("🔌 Управляемый клиент отключен")
            self.screen_window.withdraw()
            self.disable_mouse_control()
            
        elif msg_type == "controlled_status":
            self.log_info(f"📊 {message.get('info', '')}")
            
        elif msg_type == "connection_status":
            self.update_status(message["message"], message["connected"])
            
        elif msg_type == "error":
            self.log_info(f"❌ Ошибка: {message.get('message', '')}")

    def display_screen(self, message):
        """Отображение скриншота с информацией о масштабировании"""
        try:
            screen_data = message.get("screen_data")
            if not screen_data:
                self.logger.error("❌ Пустые данные экрана")
                return
                
            # Сохраняем параметры масштабирования
            self.scale_params = {
                'offset_x': message.get('offset_x', 0),
                'offset_y': message.get('offset_y', 0),
                'scaled_width': message.get('scaled_width', 1920),
                'scaled_height': message.get('scaled_height', 1080),
                'scale_ratio': message.get('scale_ratio', 1.0)
            }
            
            self.logger.info(f"🖼️ Параметры масштабирования: {self.scale_params}")
            
            # Декодируем base64
            image_data = base64.b64decode(screen_data)
            
            # Создаем BytesIO объект
            image_buffer = io.BytesIO(image_data)
            
            # Открываем изображение
            image = Image.open(image_buffer)
            
            # Создаем PhotoImage
            photo = ImageTk.PhotoImage(image)
            
            # Очищаем canvas и отображаем изображение
            self.screen_canvas.delete("all")
            self.screen_canvas.create_image(0, 0, anchor=tk.NW, image=photo)
            self.screen_canvas.image = photo  # Сохраняем ссылку
            
            # Показываем окно, если оно скрыто
            if not self.screen_window.winfo_viewable():
                self.screen_window.deiconify()
                    
            self.logger.info("✅ Весь экран отображен корректно")
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка отображения экрана: {e}")
            import traceback
            self.logger.error(f"🔍 Подробности: {traceback.format_exc()}")

    def update_status(self, message, is_connected=False):
        """Обновление статуса подключения"""
        self.connected = is_connected
        status_text = "Статус: Подключен" if is_connected else "Статус: Отключен"
        self.status_label.config(text=status_text, 
                               fg="green" if is_connected else "red")
        
        self.screen_btn.config(state=tk.NORMAL if is_connected else tk.DISABLED)
        self.stop_screen_btn.config(state=tk.NORMAL if is_connected else tk.DISABLED)
        self.mouse_btn.config(state=tk.NORMAL if is_connected else tk.DISABLED)
        
        self.log_info(message)

    def log_info(self, message):
        """Добавление информации в лог"""
        if hasattr(self, 'info_text') and self.info_text:
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.info_text.insert(tk.END, f"{timestamp} - {message}\n")
            self.info_text.see(tk.END)

    def request_screen(self):
        """Запрос скриншота с управляемого клиента"""
        if self.connected:
            asyncio.run_coroutine_threadsafe(
                self.send_command("capture_screen"), 
                self.asyncio_loop
            )
            self.log_info("📨 Запрос ВСЕГО экрана отправлен")

    def stop_screen(self):
        """Остановка передачи экрана"""
        if self.connected:
            asyncio.run_coroutine_threadsafe(
                self.send_command("stop_capture"), 
                self.asyncio_loop
            )
            self.log_info("⏹️ Остановка передачи экрана")
            self.screen_canvas.delete("all")
            self.screen_window.withdraw()

    def toggle_mouse_control(self):
        """Включение/выключение управления мышью"""
        if self.connected:
            if not self.mouse_control_enabled:
                self.enable_mouse_control()
            else:
                self.disable_mouse_control()

    def enable_mouse_control(self):
        """Включение управления мышью"""
        self.mouse_control_enabled = True
        self.mouse_btn.config(text="🐭 Выключить управление", bg="red", fg="white")
        self.log_info("🎮 Управление мышью АКТИВИРОВАНО")
        if not self.screen_window.winfo_viewable():
            self.screen_window.deiconify()
        self.screen_canvas.focus_set()
        
        asyncio.run_coroutine_threadsafe(
            self.send_command("toggle_mouse_control"), 
            self.asyncio_loop
        )

    def disable_mouse_control(self):
        """Выключение управления мышью"""
        self.mouse_control_enabled = False
        self.mouse_btn.config(text="🐭 Включить управление", bg="SystemButtonFace", fg="black")
        self.log_info("🖱️ Управление мышью деактивировано")
        
        asyncio.run_coroutine_threadsafe(
            self.send_command("toggle_mouse_control"), 
            self.asyncio_loop
        )

    async def send_command(self, command, data=None):
        """Отправка команды управляемому клиенту"""
        if self.websocket and self.connected:
            try:
                await self.websocket.send(json.dumps({
                    "type": "control_command",
                    "command": command,
                    "data": data
                }))
                self.logger.debug(f"✅ Команда отправлена: {command}")
            except Exception as e:
                self.logger.error(f"❌ Ошибка отправки команды: {e}")

    async def connect_to_server(self, uri):
        try:
            self.logger.info(f"🔄 Подключение к {uri}...")
            self.websocket = await websockets.connect(
                uri,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
                max_size=10 * 1024 * 1024
            )
            
            await self.websocket.send(json.dumps({
                "type": "controller",
                "client_id": self.client_id
            }))
            
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
        
        try:
            self.control_window.mainloop()
        except Exception as e:
            self.logger.error(f"❌ Ошибка GUI: {e}")
        finally:
            self.quit_app()

    def quit_app(self):
        """Выход из приложения"""
        self.disable_mouse_control()
        
        if self.websocket and self.asyncio_loop:
            asyncio.run_coroutine_threadsafe(
                self.websocket.close(),
                self.asyncio_loop
            )
        
        if self.control_window:
            self.control_window.quit()
            self.control_window.destroy()

def main():
    print("=== 🎮 Клиент удаленного управления ===")
    print("🖥️  Режим: Отображение ВСЕГО экрана управляемого компьютера")
    print("💡 Все элементы интерфейса будут видны")
    
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