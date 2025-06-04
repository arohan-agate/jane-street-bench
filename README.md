# jane-street-bench
Benchmarking on Jane Street puzzles

`eval_model` - evaluate on the current month's Jane Street Puzzle.

`benchmarks` - evaluate a model on all Jane Street Puzzles. The model gets 2 attempts per problem.

`benchmark_reasoning` - evaluate all reasoning models on all Jane Street Puzzles. Each model gets 2 attempts per problem.

`eval_reasoning` - evaluate a reasoning model on a selected problem.

`extract_answers` - a script to parse solution texts for the final answer.

`check_accuracy` - checks the accuracy of the benchmarks by comparing the model results to the extracted answers.
