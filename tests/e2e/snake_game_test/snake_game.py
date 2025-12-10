#!/usr/bin/env python3

# ... [existing code] ...\n
# High score feature
HIGH_SCORE_FILE = 'high_score.txt'

def load_high_score():
    try:
        with open(HIGH_SCORE_FILE, 'r') as file:
            return int(file.read().strip())
    except FileNotFoundError:
        return 0

def save_high_score(score):
    with open(HIGH_SCORE_FILE, 'w') as file:
        file.write(str(score))

    def reset(self):
        self.snake = Snake()
        self.food = Food()
        self.food.randomize_position(self.snake.positions)
        self.score = 0
        self.game_over = False
        self.high_score = load_high_score()

    def update(self):
        if self.game_over:
            return

        if not self.snake.update():
            self.game_over = True
            return

        # Check if snake ate food
        if self.snake.get_head_position() == self.food.position:
            self.snake.eat()
            self.score += 10
            self.food.randomize_position(self.snake.positions)

            if self.score > self.high_score:
                self.high_score = self.score
                save_high_score(self.high_score)

        # ... [existing code] ...