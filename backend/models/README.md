# Local models

This folder is git-ignored except for this README. Models are fetched, not committed.

## FinBERT (sentiment)

```
cd backend
uv run python scripts/download_finbert.py
```

Installs into `models/finbert/` (override with `--dest`):

- `model.onnx`: int8-quantized ONNX export of ProsusAI/finbert, taken from the Hugging Face repo
  `Xenova/finbert` (`onnx/model_quantized.onnx`, ~110 MB; falls back to fp32 `onnx/model.onnx`).
  `SOURCE.txt` records which file was used.
- `tokenizer.json`, `config.json`: from the same repo. The scorer reads `id2label` from
  `config.json` (positive/negative/neutral) rather than assuming a label order.

### Fallback if the repo disappears

Export it yourself with optimum (not a project dependency; run it in a throwaway environment):

```
uvx --with torch --with transformers "optimum[exporters]" optimum-cli export onnx \
    --model ProsusAI/finbert --task text-classification models/finbert
```

then make sure `tokenizer.json` and `config.json` sit next to `model.onnx`.
