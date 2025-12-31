# Nouvaris Agents V2

Base inicial com LangGraph, estado canonico e CLI funcional.

## Setup

1) Criar venv e instalar dependencias

python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]

2) Rodar o CLI

python scripts\cli_chat.py --debug

3) Rodar um dialogo de script

python scripts\cli_chat.py --script tests\dialogs\checkout_retry.txt --debug

4) Rodar testes

pytest -q
