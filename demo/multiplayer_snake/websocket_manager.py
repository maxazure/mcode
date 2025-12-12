from typing import Dict, List
from fastapi import WebSocket
import json
import asyncio

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.player_names: Dict[str, str] = {}
        self.player_colors: List[str] = [
            "#00FF00",  # 绿色
            "#FF0000",  # 红色  
            "#0000FF",  # 蓝色
            "#FFFF00",  # 黄色
        ]
    
    async def connect(self, websocket: WebSocket, player_id: str, player_name: str):
        await websocket.accept()
        self.active_connections[player_id] = websocket
        self.player_names[player_id] = player_name
        
        # 分配颜色
        player_index = len(self.active_connections) - 1
        color = self.player_colors[player_index % len(self.player_colors)]
        
        return color
    
    def disconnect(self, player_id: str):
        if player_id in self.active_connections:
            del self.active_connections[player_id]
        if player_id in self.player_names:
            del self.player_names[player_id]
    
    async def send_personal_message(self, message: dict, player_id: str):
        if player_id in self.active_connections:
            websocket = self.active_connections[player_id]
            await websocket.send_text(json.dumps(message))
    
    async def broadcast(self, message: dict):
        if self.active_connections:
            await asyncio.gather(
                *[connection.send_text(json.dumps(message)) 
                  for connection in self.active_connections.values()]
            )
    
    def get_connected_players(self) -> List[dict]:
        players = []
        for i, (player_id, name) in enumerate(self.player_names.items()):
            color = self.player_colors[i % len(self.player_colors)]
            players.append({
                "id": player_id,
                "name": name,
                "color": color
            })
        return players
    
    def get_connection_count(self) -> int:
        return len(self.active_connections)

manager = ConnectionManager()