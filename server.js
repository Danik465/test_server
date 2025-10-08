// server.js - простой WebSocket сервер на Node.js
const WebSocket = require('ws');
const server = new WebSocket.Server({ port: 8080 });

server.on('connection', (socket) => {
    console.log('Новое подключение');
    
    socket.on('message', (message) => {
        console.log('Получено сообщение:', message.toString());
        
        // Отправляем сообщение всем подключенным клиентам
        server.clients.forEach((client) => {
            if (client.readyState === WebSocket.OPEN) {
                client.send(message.toString());
            }
        });
    });
    
    socket.on('close', () => {
        console.log('Подключение закрыто');
    });
});

console.log('WebSocket сервер запущен на порту 8080');