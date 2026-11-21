"""Split the executed Colab notebook into result files: python bench/extract_results.py <executed.ipynb> <run dir>

The notebook's last cell prints every `vllm bench serve` result file as one JSON line between <<<RESULTS and
RESULTS>>>. This writes each line back to its file name and collects the environment lines (GPU, CPU, versions, the
server's own first-token counters) into environment.txt.
"""
import json
import re
import sys
from pathlib import Path

ENV_LINE = re.compile(r"(Tesla|name, memory|Python 3|torch +\d|transformers +\d|vllm +\d|\d+$|model name|Mem:"
                      r"|vllm:time_to_first_token_seconds_(sum|count))")


def stream_text(cell):
    return "".join("".join(o.get("text", [])) for o in cell.get("outputs", []) if o.get("output_type") == "stream")


if __name__ == "__main__":
    notebook = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    texts = [stream_text(c) for c in notebook["cells"] if c["cell_type"] == "code"]

    block = next(t for t in texts if "<<<RESULTS" in t)  # StopIteration: the results cell was not run
    written = 0
    for line in block[block.index("<<<RESULTS"):block.index("RESULTS>>>")].splitlines():
        if line.startswith("{"):
            result = json.loads(line)
            (out / result.pop("file")).write_text(json.dumps(result) + "\n", encoding="utf-8", newline="\n")
            written += 1

    env = []
    for line in (l.strip() for t in texts for l in t.splitlines()):
        if ENV_LINE.match(line) and line not in env:
            env.append(re.sub(r"\s{2,}", " ", line))
    (out / "environment.txt").write_text("\n".join(env) + "\n", encoding="utf-8", newline="\n")
    print(f"{written} result files and environment.txt ({len(env)} lines) in {out}")
