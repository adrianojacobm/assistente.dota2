# Assistente Dota 2 — builds Dota2ProTracker

## Instalação
1. Extraia todos os arquivos do ZIP para uma pasta nova.
2. Abra o terminal nessa pasta.
3. Instale as dependências: `python -m pip install -r requirements.txt`
4. Execute: `python app.py`

## Builds por função
A build principal usa o endpoint JSON do Dota2ProTracker por herói e posição: Carry (pos 1), Mid (pos 2), Offlane (pos 3), Support (pos 4) e Hard Support (pos 5). O programa usa a build com a maior amostra retornada para aquela posição.

- **Saída:** tenta usar o combo inicial mais popular que caiba em 600 de ouro. Quantidades repetidas são preservadas. Wards e pergaminhos de TP não são mostrados como recomendação.
- **Core:** itens com pick rate de pelo menos 50%, ordenados pelo tempo médio de compra e distribuídos em Early (<12 min), Mid (12–30 min) e Late (30+ min).
- **Situacionais:** itens menos frequentes aparecem no painel principal, junto de pick rate e minuto médio. Não são tratados como obrigatórios.
- **Opções:** continuam separadas e são calculadas em função da lane selecionada, da ameaça marcada e da função/posição escolhida.

## Atualização/cache
As respostas Dota2ProTracker ficam em `cache/d2pt` por 30 minutos para reduzir chamadas. A janela de dados do site é móvel e depende da amostra recente disponível para aquele herói/função. A rota é mantida pelo próprio site, não é uma API oficial documentada para terceiros; ela pode mudar ou devolver HTTP 403/Cloudflare. Nesses casos, o aplicativo informa a falha em vez de apresentar uma build antiga como se fosse atual.

A consulta HTTP direta não pode ser validada a partir deste ambiente de construção. Testes de parsing e lógica são executados com payloads simulados. O primeiro teste real deve ser feito na sua conexão residencial, abrindo a função desejada e pressionando **Atualizar Build & Calcular Counter-Picks**.

## Testes
`python -m unittest discover -s tests -v`
