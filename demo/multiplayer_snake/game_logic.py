import random
import asyncio
from typing import Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum

# 游戏常量
GRID_WIDTH = 30
GRID_HEIGHT = 20
GRID_SIZE = 20
GAME_SPEED = 100  # 毫秒

# 方向
class Direction(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

@dataclass
class Position:
    x: int
    y: int
    
    def __hash__(self):
        return hash((self.x, self.y))
    
    def __eq__(self, other):
        return self.x == other.x and self.y == other.y

class Snake:
    def __init__(self, player_id: str, name: str, color: str):
        self.player_id = player_id
        self.name = name
        self.color = color
        self.positions: List[Position] = []
        self.direction = Direction.RIGHT
        self.alive = True
        self.score = 0
        self.reset()
    
    def reset(self):
        # 随机生成初始位置
        start_x = random.randint(5, GRID_WIDTH - 5)
        start_y = random.randint(5, GRID_HEIGHT - 5)
        self.positions = [Position(start_x, start_y)]
        self.direction = Direction.RIGHT
        self.alive = True
        self.score = 0
    
    def move(self) -> bool:
        if not self.alive:
            return True
            
        head = self.positions[0]
        dx, dy = self.direction.value
        new_head = Position(head.x + dx, head.y + dy)
        
        # 检查撞墙
        if new_head.x < 0 or new_head.x >= GRID_WIDTH or \
           new_head.y < 0 or new_head.y >= GRID_HEIGHT:
            self.alive = False
            return False
        
        # 检查撞自己
        if new_head in self.positions[1:]:
            self.alive = False
            return False
        
        self.positions.insert(0, new_head)
        return True
    
    def change_direction(self, new_direction: Direction):
        # 防止直接掉头
        opposite = {
            Direction.UP: Direction.DOWN,
            Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT,
            Direction.RIGHT: Direction.LEFT
        }
        
        if new_direction != opposite.get(self.direction):
            self.direction = new_direction
    
    def grow(self):
        """蛇增长（吃食物时调用）"""
        pass  # 位置已经在move中添加，这里不需要额外操作
    
    def shrink(self):
        """移除尾部（正常移动时调用）"""
        if len(self.positions) > 1:
            self.positions.pop()
    
    def eat_food(self):
        self.score += 10
    
    def get_state(self) -> dict:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "color": self.color,
            "positions": [{"x": pos.x, "y": pos.y} for pos in self.positions],
            "alive": self.alive,
            "score": self.score
        }

class Food:
    def __init__(self):
        self.position = None
        self.spawn()
    
    def spawn(self, snake_positions: List[Position] = None):
        """生成食物，避开蛇的位置"""
        if snake_positions is None:
            snake_positions = []
            
        attempts = 0
        while attempts < 100:  # 最多尝试100次
            x = random.randint(0, GRID_WIDTH - 1)
            y = random.randint(0, GRID_HEIGHT - 1)
            new_pos = Position(x, y)
            
            if new_pos not in snake_positions:
                self.position = new_pos
                break
            attempts += 1
    
    def get_state(self) -> dict:
        return {
            "x": self.position.x,
            "y": self.position.y
        }

class MultiplayerGame:
    def __init__(self):
        self.snakes: Dict[str, Snake] = {}
        self.foods: List[Food] = []
        self.game_running = False
        self.game_loop_task = None
    
    def add_player(self, player_id: str, name: str, color: str):
        """添加玩家"""
        snake = Snake(player_id, name, color)
        self.snakes[player_id] = snake
        
        # 如果是第一个玩家，初始化食物
        if len(self.snakes) == 1:
            self.foods = [Food()]
    
    def remove_player(self, player_id: str):
        """移除玩家"""
        if player_id in self.snakes:
            del self.snakes[player_id]
        
        # 如果没有玩家了，停止游戏
        if not self.snakes and self.game_running:
            self.stop_game()
    
    def start_game(self):
        """开始游戏"""
        if not self.game_running and self.snakes:
            self.game_running = True
            # 重置所有玩家
            for snake in self.snakes.values():
                snake.reset()
            # 重新生成食物
            self.foods = [Food()]
            self.foods[0].spawn(self.get_all_snake_positions())
    
    def stop_game(self):
        """停止游戏"""
        self.game_running = False
        if self.game_loop_task:
            self.game_loop_task.cancel()
            self.game_loop_task = None
    
    def get_all_snake_positions(self) -> List[Position]:
        """获取所有蛇的位置"""
        positions = []
        for snake in self.snakes.values():
            if snake.alive:
                positions.extend(snake.positions)
        return positions
    
    def update_player_direction(self, player_id: str, direction: Direction):
        """更新玩家方向"""
        if player_id in self.snakes:
            self.snakes[player_id].change_direction(direction)
    
    def game_step(self):
        """游戏逻辑更新一步"""
        if not self.game_running:
            return
        
        # 移动所有蛇
        for snake in self.snakes.values():
            if snake.alive:
                snake.move()
        
        # 检查蛇之间的碰撞
        for snake1 in self.snakes.values():
            if not snake1.alive:
                continue
            head1 = snake1.positions[0]
            
            for snake2 in self.snakes.values():
                if snake1.player_id == snake2.player_id:
                    continue
                if not snake2.alive:
                    continue
                
                # 检查蛇1头部是否撞到蛇2身体
                if head1 in snake2.positions:
                    snake1.alive = False
                    break
        
        # 检查吃食物
        all_positions = self.get_all_snake_positions()
        for food in self.foods:
            for snake in self.snakes.values():
                if snake.alive and snake.positions[0] == food.position:
                    snake.eat_food()
                    # 重新生成食物
                    food.spawn(all_positions)
                    break
        
        # 正常移动的蛇需要缩短
        for snake in self.snakes.values():
            if snake.alive and len(snake.positions) > 1:
                snake.shrink()
        
        # 检查游戏是否结束（所有蛇都死亡）
        alive_count = sum(1 for snake in self.snakes.values() if snake.alive)
        if alive_count <= 1 and len(self.snakes) > 1:
            self.stop_game()
    
    def get_game_state(self) -> dict:
        """获取当前游戏状态"""
        return {
            "game_running": self.game_running,
            "snakes": [snake.get_state() for snake in self.snakes.values()],
            "foods": [food.get_state() for food in self.foods],
            "grid_width": GRID_WIDTH,
            "grid_height": GRID_HEIGHT
        }
    
    def get_leaderboard(self) -> List[dict]:
        """获取排行榜"""
        return sorted(
            [{"name": snake.name, "score": snake.score, "alive": snake.alive} 
             for snake in self.snakes.values()],
            key=lambda x: x["score"],
            reverse=True
        )