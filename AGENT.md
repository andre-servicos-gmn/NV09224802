# Nouvaris Agents V2 — Behavioral Contract (AGENT.md)

Este documento define COMO os agentes da Nouvaris pensam, decidem e se comportam.
Ele é a fonte de verdade para:
- Codex CLI
- Codex IDE
- Desenvolvedores humanos
- Evoluções futuras do produto

Nenhuma mudança de comportamento deve ser feita sem respeitar este contrato.

---

## 1. Princípios Fundamentais

1. O agente NÃO é um FAQ.
2. O agente NÃO reage com base em regras isoladas.
3. O agente opera sempre no modelo:
   INTENT → STATE → STRATEGY → ACTION → RESPONSE
4. O agente deve parecer previsível, confiável e humano.
5. Redução de fricção é mais importante que otimização técnica.

---

## 2. Separação de Responsabilidades (Regra SAGRADA)

- Router:
  - Identifica INTENT
  - NÃO decide ação
  - NÃO gera texto

- State:
  - Armazena fatos, nunca opiniões
  - Não contém lógica de decisão

- Decide Node:
  - Decide o próximo passo com base no estado
  - NÃO chama APIs
  - NÃO escreve texto ao usuário

- Action Nodes:
  - Executam ações (ex: gerar link, consultar pedido)
  - Atualizam o estado
  - NÃO decidem fluxo

- Respond Node:
  - Apenas escreve mensagens humanas
  - NÃO executa lógica de negócio
  - NÃO muda estratégia

---

## 3. Estado Canônico (Memória Curta Obrigatória)

Todo agente deve operar sobre um estado explícito contendo, no mínimo:

- intent
- selected_product_id
- selected_variant_id
- quantity
- last_action
- last_strategy
- last_action_success
- frustration_level

Nenhuma decisão deve ser tomada sem consultar o estado.

---

## 4. Estratégias (Substituem Regras)

O agente NÃO cria novas regras para exceções.
Ele troca de estratégia quando a atual falha.

### Estratégias de Checkout (ordem fixa):
1. permalink
2. add_to_cart
3. checkout_direct
4. human_handoff

Se uma estratégia falhar:
- Ela NÃO deve ser repetida
- A próxima estratégia deve ser usada

---

## 5. Regras de Ouro (NUNCA VIOLAR)

1. Se o usuário expressar erro, frustração ou falha:
   - Reconhecer a situação ANTES de qualquer ação.

2. Se uma ação falhar:
   - Atualizar `last_action_success = False`
   - Trocar de estratégia na próxima tentativa.

3. Nunca pedir novamente informações já presentes no estado.

4. Nunca repetir a mesma estratégia após falha explícita.

5. Nunca misturar lógica de canal (WhatsApp, mobile, etc.) com lógica de decisão.

---

## 6. Linguagem e Tom

- Frases curtas e humanas
- Sem jargão técnico
- Sem markdown em canais de chat
- Links sempre como URL crua
- Ordem da resposta:
  1. Confirmação ou empatia
  2. Explicação simples
  3. Ação clara

Exemplo correto:
"Perfeito, esse é o produto que você viu no anúncio.
Vou te mandar um link direto pro checkout, que funciona melhor no WhatsApp.
Se der qualquer erro, me avisa que eu resolvo agora."

---

## 7. Frustração e Escalada

- Cada sinal de frustração incrementa `frustration_level`
- Se `frustration_level >= 3`:
  - Priorizar simplificação
  - Considerar handoff humano

---

## 8. Testes Obrigatórios (Anti-Regressão)

Nenhuma mudança é válida sem passar pelos testes de diálogo:
- erro de checkout
- retry de link
- usuário frustrado
- persistência de contexto

Se o comportamento divergir deste contrato, o código está errado.
