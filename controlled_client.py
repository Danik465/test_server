import asyncio
import websockets
import json
import sys
import logging
import base64
import io
from PIL import ImageGrab, Image
import pyautogui
from datetime import datetime
import time

class RemoteControlledClient:
    def __init__(self):
        self.websocket = None
        self.client_id = f"controlled_{datetime.now().strftime('%H%M%S')}"
        self.connected = False
        self.screen_capturing = False
        self.mouse_control = False
        self.screen_task = None
        self.target_width = 1920
        self.target_height = 1080
        self.setup_logging()
        
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("controlled.log", encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("RemoteControlled")

    def capture_screen(self):
        """Захват всего экрана и масштабирование с сохранением всех элементов"""
        try:
            # Захватываем скриншот всего экрана
            screenshot = ImageGrab.grab()
            original_width, original_height = screenshot.size
            
            self.logger.debug(f"🖥️ Исходное разрешение: {original_width}x{original_height}")
            
            # Масштабируем изображение так, чтобы ВЕСЬ экран поместился в 1920x1080
            # Вычисляем коэффициенты масштабирования
            width_ratio = self.target_width / original_width
            height_ratio = self.target_height / original_height
            
            # Используем МЕНЬШИЙ коэффициент, чтобы ВЕСЬ экран поместился
            scale_ratio = min(width_ratio, height_ratio)
            
            # Вычисляем новые размеры
            new_width = int(original_width * scale_ratio)
            new_height = int(original_height * scale_ratio)
            
            # Масштабируем изображение с высоким качеством
            resized_screenshot = screenshot.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Создаем черный фон целевого размера
            final_image = Image.new('RGB', (self.target_width, self.target_height), (0, 0, 0))
            
            # Вычисляем позицию для центрирования изображения
            x_offset = (self.target_width - new_width) // 2
            y_offset = (self.target_height - new_height) // 2
            
            # Вставляем масштабированное изображение в центр
            final_image.paste(resized_screenshot, (x_offset, y_offset))
            
            # Конвертируем в base64
            buffer = io.BytesIO()
            final_image.save(buffer, format='JPEG', quality=85, optimize=True)
            image_data = buffer.getvalue()
            
            self.logger.debug(f"📸 Весь экран масштабирован: {original_width}x{original_height} -> {new_width}x{new_height}")
            
            # Возвращаем также параметры масштабирования для корректной работы мыши
            return {
                'image_data': base64.b64encode(image_data).decode('utf-8'),
                'original_width': original_width,
                'original_height': original_height,
                'scaled_width': new_width,
                'scaled_height': new_height,
                'offset_x': x_offset,
                'offset_y': y_offset,
                'scale_ratio': scale_ratio
            }
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка захвата экрана: {e}")
            import traceback
            self.logger.error(f"🔍 Подробности: {traceback.format_exc()}")
            return None

    async def send_screen_updates(self):
        """Отправка обновлений экрана"""
        self.logger.info("🔄 Начало передачи ВСЕГО экрана")
        
        frame_count = 0
        start_time = time.time()
        
        while self.screen_capturing and self.connected:
            try:
                frame_start = time.time()
                
                capture_result = self.capture_screen()
                if capture_result and self.websocket:
                    await self.websocket.send(json.dumps({
                        "type": "screen_data",
                        "screen_data": capture_result['image_data'],
                        "original_width": capture_result['original_width'],
                        "original_height": capture_result['original_height'],
                        "scaled_width": capture_result['scaled_width'],
                        "scaled_height": capture_result['scaled_height'],
                        "offset_x": capture_result['offset_x'],
                        "offset_y": capture_result['offset_y'],
                        "scale_ratio": capture_result['scale_ratio'],
                        "timestamp": frame_start
                    }))
                    frame_count += 1
                    
                    if frame_count % 30 == 0:
                        elapsed = time.time() - start_time
                        fps = frame_count / elapsed
                        self.logger.info(f"📊 Статистика: {frame_count} кадров, {fps:.1f} FPS")
                
                # Регулируем FPS
                elapsed_frame = time.time() - frame_start
                target_fps = 10
                sleep_time = max(1.0/target_fps - elapsed_frame, 0.01)
                await asyncio.sleep(sleep_time)
                    
            except asyncio.CancelledError:
                self.logger.info("🛑 Передача экрана прервана")
                break
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("🔌 Соединение закрыто во время отправки экрана")
                break
            except Exception as e:
                self.logger.error(f"❌ Ошибка отправки экрана: {e}")
                await asyncio.sleep(0.5)

    async def execute_command(self, command, data=None):
        """Выполнение команд от управляющего клиента"""
        try:
            self.logger.info(f"🔧 Выполнение команды: {command}")
            
            if command == "capture_screen":
                if not self.screen_capturing:
                    self.screen_capturing = True
                    self.screen_task = asyncio.create_task(self.send_screen_updates())
                    await self.send_status("Захват ВСЕГО экрана активирован")
                    
            elif command == "stop_capture":
                if self.screen_capturing:
                    self.screen_capturing = False
                    if self.screen_task:
                        self.screen_task.cancel()
                        try:
                            await self.screen_task
                        except asyncio.CancelledError:
                            pass
                    await self.send_status("Захват экрана остановлен")
                    
            elif command == "toggle_mouse_control":
                self.mouse_control = not self.mouse_control
                status = "активировано" if self.mouse_control else "деактивировано"
                await self.send_status(f"Управление мышью {status}")
                
            elif command == "mouse_move" and self.mouse_control:
                await self.handle_mouse_command("move", data)
                
            elif command == "mouse_click" and self.mouse_control:
                await self.handle_mouse_command("click", data)
                
            elif command == "mouse_down" and self.mouse_control:
                await self.handle_mouse_command("down", data)
                
            elif command == "mouse_up" and self.mouse_control:
                await self.handle_mouse_command("up", data)
                
            elif command == "key_press" and self.mouse_control:
                key = data['key']
                pyautogui.press(key, _pause=False)
                
            elif command == "key_down" and self.mouse_control:
                key = data['key']
                pyautogui.keyDown(key, _pause=False)
                
            elif command == "key_up" and self.mouse_control:
                key = data['key']
                pyautogui.keyUp(key, _pause=False)
                
            elif command == "type_write" and self.mouse_control:
                text = data['text']
                pyautogui.write(text, interval=0.01, _pause=False)
                
            else:
                if self.mouse_control:
                    await self.send_status(f"Получена команда: {command}")
                else:
                    await self.send_status(f"Команда {command} игнорируется (управление отключено)")
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка выполнения команды {command}: {e}")
            await self.send_status(f"Ошибка выполнения: {e}")

    async def handle_mouse_command(self, action, data):
        """Обработка команд мыши с корректным преобразованием координат"""
        try:
            # Получаем параметры масштабирования из данных
            scale_ratio = data.get('scale_ratio', 1.0)
            offset_x = data.get('offset_x', 0)
            offset_y = data.get('offset_y', 0)
            scaled_width = data.get('scaled_width', self.target_width)
            scaled_height = data.get('scaled_height', self.target_height)
            
            # Получаем координаты от управляющего клиента
            remote_x = data['x']
            remote_y = data['y']
            
            # Проверяем, находится ли клик в области изображения (не в черных полосах)
            if (remote_x < offset_x or remote_x >= offset_x + scaled_width or 
                remote_y < offset_y or remote_y >= offset_y + scaled_height):
                return  # Клик в черных полосах - игнорируем
            
            # Преобразуем координаты из масштабированного изображения в реальные
            local_x = int((remote_x - offset_x) / scale_ratio)
            local_y = int((remote_y - offset_y) / scale_ratio)
            
            # Получаем реальное разрешение экрана для проверки границ
            screen_width, screen_height = pyautogui.size()
            local_x = max(0, min(local_x, screen_width - 1))
            local_y = max(0, min(local_y, screen_height - 1))
            
            # Выполняем действие
            button = data.get('button', 'left')
            
            if action == "move":
                pyautogui.moveTo(local_x, local_y, _pause=False)
            elif action == "click":
                pyautogui.click(local_x, local_y, button=button, _pause=False)
            elif action == "down":
                pyautogui.mouseDown(local_x, local_y, button=button, _pause=False)
            elif action == "up":
                pyautogui.mouseUp(local_x, local_y, button=button, _pause=False)
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки команды мыши: {e}")

    async def send_status(self, status_message):
        """Отправка статуса управляющему"""
        if self.websocket and self.connected:
            try:
                await self.websocket.send(json.dumps({
                    "type": "status_update",
                    "status": "info",
                    "info": status_message
                }))
            except Exception as e:
                self.logger.error(f"❌ Ошибка отправки статуса: {e}")

    async def connect_to_server(self, uri, max_retries=5):
        """Подключение к серверу с повторными попытками"""
        for attempt in range(max_retries):
            try:
                self.logger.info(f"🔄 Попытка подключения {attempt + 1}/{max_retries} к {uri}...")
                
                self.websocket = await websockets.connect(
                    uri,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=5,
                    max_size=10 * 1024 * 1024
                )
                
                await self.websocket.send(json.dumps({
                    "type": "controlled",
                    "client_id": self.client_id,
                    "resolution": f"{self.target_width}x{self.target_height}"
                }))
                
                message = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
                data = json.loads(message)
                
                if data.get("type") == "connection_established":
                    self.connected = True
                    self.logger.info("✅ Подключение к серверу установлено")
                    await self.send_status("Управляемый клиент готов к работе (режим: ВЕСЬ экран)")
                    return True
                    
            except Exception as e:
                self.logger.error(f"❌ Ошибка подключения (попытка {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    
        return False

    async def receive_commands(self):
        """Прием команд от сервера"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                
                if data["type"] == "execute_command":
                    await self.execute_command(data["command"], data.get("data"))
                    
                elif data["type"] == "error":
                    self.logger.error(f"❌ Ошибка от сервера: {data.get('message', '')}")
                    
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(f"🔌 Соединение с сервером закрыто: {e}")
            self.connected = False
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении команд: {e}")
            self.connected = False

    async def start(self, uri):
        """Основной цикл клиента"""
        if not await self.connect_to_server(uri):
            self.logger.error("❌ Не удалось подключиться к серверу")
            return
            
        print(f"\n✅ Управляемый клиент {self.client_id} запущен")
        print("🖥️  Режим: Отображение ВСЕГО экрана")
        print("💡 Все элементы интерфейса будут видны")
        print("⚠️  ВНИМАНИЕ: После активации управления ваш компьютер будет управляться удаленно!")
        print("-" * 50)
        
        try:
            await self.receive_commands()
        except Exception as e:
            self.logger.error(f"❌ Ошибка в основном цикле: {e}")
        finally:
            self.connected = False
            self.screen_capturing = False
            self.mouse_control = False
            
            if self.screen_task:
                self.screen_task.cancel()
                
            if self.websocket:
                await self.websocket.close()
                
        self.logger.info("👋 Управляемый клиент завершил работу")

def main():
    print("=== 🖥️ Управляемый клиент ===")
    
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

        client = RemoteControlledClient()
        asyncio.run(client.start(uri))
        
    except KeyboardInterrupt:
        logger.info("🛑 Клиент остановлен пользователем")
        print("\n🛑 Клиент остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        print(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()