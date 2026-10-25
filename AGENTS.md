# Instruções para agentes

## Projeto e execução
- Assistente desktop de Dota 2: builds Dota2ProTracker, counters OpenDota e eventos GSI.
- Python 3.10+, `pip` e `requirements.txt`; Tkinter e recursos nativos de Windows
  (Win32/SAPI via pywin32). Não prometer suporte nativo a outras plataformas.
- Entrada canônica: `python app.py`. Mantenha somente esse ponto de entrada Python
  na raiz; o código da aplicação fica em `assistente/`, sem fachadas legadas.

## Organização e dependências
- `assistente/dominio`: modelos, invariantes e cálculos puros; sem rede, disco,
  Tkinter, COM, threads ou dependências das demais camadas.
- `assistente/aplicacao`: casos de uso e contratos de integrações; depende do domínio.
- `assistente/infraestrutura`: HTTP, JSON, cache, sincronização e recursos Windows;
  implementa os contratos da aplicação.
- `assistente/apresentacao`: painel, sobreposições, formatação e entrada HTTP GSI;
  depende da aplicação e do domínio, não de clientes concretos.
- `assistente/composicao.py`: conecta dependências. `assistente/configuracao.py`
  centraliza as configurações. Não reintroduza imports dos módulos antigos da raiz.
- Testes em `tests/`. Não crie camadas, repositórios de banco ou classes base sem
  uma necessidade existente. Prefira funções e injeção explícita.

## Código e contratos
- Código próprio em português, PEP 8, nomes claros e funções com responsabilidade
  única. Preserve nomes exigidos por frameworks, protocolos e APIs externas.
- Tipar parâmetros e retornos; usar `list`, `dict`, `tuple` e `T | None`. Evitar `Any`
  fora de fronteiras inevitáveis; validar dados externos antes de usá-los.
- Usar dataclasses quando simplificarem modelos; `frozen=True` só para dados
  realmente imutáveis, e `slots=True` apenas com benefício concreto.
- Invariantes ficam próximas dos modelos. Casos de uso orquestram; não renderizam
  texto nem acessam widgets. Nomes oficiais de heróis/itens e chaves externas não
  devem ser traduzidos.
- Preservar orçamento inicial de 600 ouro, quantidades, funções, pesos e limiares
  aprovados. Não misturar build principal, heurísticas e amostras de outras fontes.
- Integrações precisam de timeout, validação e erros específicos. A interface pode
  conter falhas inesperadas com registro; nunca usar `except: pass` ou ocultar erros.
- Preferências e caches JSON existentes exigem compatibilidade de caminhos e formato.
  Cache é opcional: erro de disco não deve impedir uma consulta válida.

## Recursos e desempenho
- Nenhum I/O ou início de trabalhadores durante importação.
- Rede fora da thread gráfica; widgets e `after` somente na thread gráfica.
- Limitar trabalhadores e solicitações pendentes; descartar resultados obsoletos.
- Encerrar servidor, filas e COM explicitamente. Evitar consultas duplicadas e
  manter os limites dos provedores. Não introduzir async, cache ou micro-otimizações
  sem necessidade demonstrada.

## Qualidade e conclusão
- Testes: `python -B -m unittest discover -s tests -v`. Simular rede e voz; testar
  regras, casos de uso e integrações críticas sem exigir GUI ou Windows.
- Ruff/mypy são opcionais; se disponíveis, usar `python -m ruff check .`,
  `python -m ruff format --check .` e `python -m mypy assistente`.
- Não instalar dependências, alterar heurísticas ou remover dados versionados
  automaticamente. Não sobrescrever trabalho preexistente, executar operações
  destrutivas ou criar commits sem autorização.
- Antes de concluir: ler os arquivos afetados; adicionar testes de caracterização
  quando necessário; executar testes relevantes; revisar dependências, tipagem,
  recursos e compatibilidade; conferir `git diff`; informar resultados reais,
  limitações e pendências. Nunca inventar verificações bem-sucedidas.
