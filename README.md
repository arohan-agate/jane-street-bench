# jane-street-bench

https://arohan-agate.github.io/jane-street-bench/

Benchmarking on Jane Street puzzles

`eval_model` - evaluate on the current month's Jane Street Puzzle.

`benchmarks` - evaluate a model on all Jane Street Puzzles. The model gets 2 attempts per problem.

`benchmark_reasoning` - evaluate all reasoning models on all Jane Street Puzzles. Each model gets 2 attempts per problem.

`eval_reasoning` - evaluate a reasoning model on a selected problem.

`read_solution_text` - a script to parse solution texts for the final answer.

`check_accuracy_llm` - checks the accuracy of the benchmarks by comparing the model results to the extracted answers, using an LLM. Reads in a `results_{MODEL_NAME}.json` file and writes to `correct_solutions_{MODEL_NAME}.json`.

`check_accuracy_regex` - checks the accuracy of the benchmarks by comparing the model results to the extracted answers, using regular expressions

`extract_correct` - extracts fully and partially correct answers from the solution JSONs. Reads in `correct_solutions_{MODEL_NAME}.json` files and outputs to `full_correct_{MODEL}.json` and `partial_correct_{MODEL}.json` files.

`merge_correct_solutions` - aggregates LLM deemed correct solutions and regular expression deemed correct solutions
