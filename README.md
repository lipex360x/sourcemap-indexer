# sourcemap-indexer

Biblioteca Python que indexa qualquer codebase em SQLite, enriquecendo metadados via LLM local (qwen3-coder-30b via llama-server OpenAI-compatible).

## Instalação

```bash
pip install git+https://github.com/lipex360/sourcemap-indexer.git
```

## Dev setup

```bash
git clone https://github.com/lipex360/sourcemap-indexer.git
cd sourcemap-indexer
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
bash scripts/bash/install-hook.sh   # instala pre-commit hook
pytest
```

## Quickstart

```bash
cd <seu-projeto>
sourcemap init
sourcemap walk && sourcemap sync
sourcemap enrich          # requer llama-server rodando
sourcemap stats
```

## Variáveis de ambiente

| Var | Default | Descrição |
|-----|---------|-----------|
| `SOURCEMAP_LLM_URL` | `http://127.0.0.1:8080/v1/chat/completions` | Endpoint LLM |
| `SOURCEMAP_LLM_MODEL` | `qwen3-coder-30b` | Modelo |
