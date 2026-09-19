export const BOARD_SIZE = 16;
export const DIRECTIONS = {
  up: { x: 0, y: -1 }, down: { x: 0, y: 1 },
  left: { x: -1, y: 0 }, right: { x: 1, y: 0 },
};

export function newGame() {
  return { snake: [{ x: 5, y: 8 }, { x: 4, y: 8 }, { x: 3, y: 8 }],
    direction: "right", queued: "right", food: { x: 10, y: 8 },
    score: 0, status: "playing" };
}

export function snakeReducer(state, action) {
  if (action.type === "restart") return newGame();
  if (action.type === "pause") return { ...state, status: state.status === "playing" ? "paused" : state.status === "paused" ? "playing" : state.status };
  if (action.type === "direction" && state.status === "playing") {
    const current = DIRECTIONS[state.direction];
    const next = DIRECTIONS[action.direction];
    if (!next || (current.x + next.x === 0 && current.y + next.y === 0)) return state;
    return { ...state, queued: action.direction };
  }
  if (action.type !== "tick" || state.status !== "playing") return state;
  const move = DIRECTIONS[state.queued];
  const head = { x: state.snake[0].x + move.x, y: state.snake[0].y + move.y };
  const eating = head.x === state.food.x && head.y === state.food.y;
  const body = eating ? state.snake : state.snake.slice(0, -1);
  if (head.x < 0 || head.y < 0 || head.x >= BOARD_SIZE || head.y >= BOARD_SIZE ||
      body.some(cell => cell.x === head.x && cell.y === head.y)) {
    return { ...state, status: "over" };
  }
  const snake = [head, ...body];
  let food = state.food;
  if (eating) {
    const free = [];
    for (let y = 0; y < BOARD_SIZE; y++) for (let x = 0; x < BOARD_SIZE; x++) {
      if (!snake.some(cell => cell.x === x && cell.y === y)) free.push({ x, y });
    }
    if (!free.length) return { ...state, snake, score: state.score + 1, status: "won" };
    food = free[Math.floor((action.random ?? 0) * free.length)];
  }
  return { ...state, snake, food, direction: state.queued, score: state.score + Number(eating) };
}
