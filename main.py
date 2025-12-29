import engine


game = engine.initialize_game(3, 20, {20:50, 100:50, 200:30}, [20, 100, 200])
engine.initial_betting_round(game)