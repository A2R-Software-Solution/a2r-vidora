import { test } from "node:test";
import assert from "node:assert/strict";
import { newGame, snakeReducer } from "./snake.js";

test("snake starts automatically, eats food and spawns food off its body", () => {
  let game = newGame();
  assert.equal(game.status, "playing");
  for (let i = 0; i < 5; i++) game = snakeReducer(game, { type: "tick", random: .5 });
  assert.equal(game.score, 1);
  assert.equal(game.snake.length, 4);
  assert.ok(!game.snake.some(cell => cell.x === game.food.x && cell.y === game.food.y));
});

test("rejects reverse turns including two key presses within one tick", () => {
  const game = newGame();
  assert.equal(snakeReducer(game, { type: "direction", direction: "left" }), game);
  const up = snakeReducer(game, { type: "direction", direction: "up" });
  const reversed = snakeReducer(up, { type: "direction", direction: "left" });
  assert.equal(reversed.queued, "up");
});

test("pause stops movement, walls end the game and restart resets it", () => {
  let game = snakeReducer(newGame(), { type: "pause" });
  assert.equal(snakeReducer(game, { type: "tick" }), game);
  game = snakeReducer(game, { type: "pause" });
  for (let i = 0; i < 16; i++) game = snakeReducer(game, { type: "tick" });
  assert.equal(game.status, "over");
  assert.deepEqual(snakeReducer(game, { type: "restart" }), newGame());
});
