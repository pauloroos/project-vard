# Mesa: ferramentas de Windows

`nucleo/mesa_mcp.py` é o MCP (stdio) que dá ao cérebro, seja o OpenJarvis ou uma CLI com
`--mcp-config`, acesso ao computador: abrir sites e programas, janelas, monitores, clique e
teclado. Toda ferramenta devolve uma frase em português e nunca levanta exceção (guarda `_seguro`).

## Ferramentas

| Ferramenta | O que faz |
|---|---|
| `abrir_url(url, navegador="")` | Abre um site conhecido, domínio ou URL. `navegador` (brave, chrome, edge, firefox, opera, opera gx, vivaldi, chromium ou o nome de outro exe) é localizado pelo registro (App Paths, StartMenuInternet) e pelas pastas padrão. Vazio usa o navegador padrão. Se o navegador não existir, a frase lista os que foram encontrados. |
| `abrir_programa(nome)` | Abre um programa por apelido, PATH ou menu Iniciar. |
| `listar_janelas()` | Título, processo e, com mais de um monitor, o monitor de cada janela. |
| `focar_janela(titulo)` / `fechar_janela(titulo)` | Traz para a frente / pede para fechar. |
| `listar_monitores()` | Número, nome, resolução, posição, escala, área útil e qual é o principal. |
| `mover_janela(titulo="", monitor=None, posicao="", x, y, largura, altura)` | Posições: maximizar, minimizar, restaurar, esquerda, direita, cima, baixo, centro e tela cheia. Só `monitor` leva a janela mantendo posição e tamanho proporcionais. `x`/`y` contam a partir do canto da área útil do monitor. |
| `elementos_da_janela(titulo="", filtro="")` | Botões, links, campos e itens visíveis pela UI Automation, com id curto (`e1`...) e retângulo. Até 40 itens e 80 caracteres por nome; o filtro procura no nome sem diferenciar acento ou caixa. |
| `clicar_elemento(titulo, nome_ou_id)` | Aciona pela UI Automation (Invoke, Select, Toggle ou Expand); sem esses padrões, clica no centro do elemento. O id vale para a última lista daquela janela. |
| `clicar(x, y, botao="esquerdo", duplo=False)` | Clique em coordenadas de tela. É a reserva quando a UI Automation não expõe o alvo (por exemplo, miniaturas de vídeo). |
| `digitar(texto, janela="")` | Digita no foco atual ou foca a janela antes. Os caracteres vão como Unicode, então acentos funcionam em qualquer layout (ABNT2 incluso). A resposta só diz quantos caracteres foram digitados. |
| `teclar(combinacao, janela="", vezes=1)` | `enter`, `esc`, `tab`, `f5`, `ctrl+l`, `ctrl+shift+t`, `alt+tab`, `seta para baixo`... |
| `rolar(quantidade, x=None, y=None)` | Roda do mouse: positivo desce, negativo sobe (no máximo 50). |
| `print_da_tela(caminho="", monitor=None)` | PNG do monitor principal, de um monitor numerado ou de `todos`, salvo na pasta de prints. |
| `hora_atual()` | Data e hora em português. |

Título vazio em `mover_janela`, `elementos_da_janela` e `clicar_elemento` quer dizer a janela ativa.

## Coordenadas

O processo da mesa se declara *per-monitor DPI aware* (v2). Por isso todas as coordenadas são
pixels físicos da área de trabalho virtual: as do `print_da_tela`, dos retângulos de
`elementos_da_janela`, de `listar_monitores` e as que `clicar`/`rolar` recebem. Um monitor à
esquerda do principal tem `x` negativo.

Os monitores são numerados da esquerda para a direita, a partir de 1. Essa numeração pode
diferir da que aparece nas Configurações do Windows. O nome (`DISPLAY2`) ajuda a conferir.

O `print_da_tela` reduz a imagem para no máximo 1568 px no lado maior e cerca de 1,15 megapixel,
o tamanho que o modelo enxerga sem nova redução. A frase devolvida traz a conversão:

```
Pixel (px, py) da imagem = tela x = <origem_x> + px*<fator>, y = <origem_y> + py*<fator>.
```

Exemplo fictício: monitor de 2560x1440 em (-2560, 0) vira imagem de 1429x804 com fator 1,7915;
o pixel (700, 400) da imagem corresponde a `clicar(-2560 + 700*1.7915, 0 + 400*1.7915)`, ou seja,
`clicar(-1306, 717)`.

## Segurança

- Todas as ferramentas passam pela guarda `_seguro`. Frases de erro já prontas (`Frase`,
  `ValueError`) chegam sem prefixo técnico; o resto vira "Não consegui ...".
- `elementos_da_janela` nunca lê o valor de campos; campo de senha aparece só como
  "(campo de senha)". `digitar` nunca repete o texto na resposta.
- `teclar` recusa Ctrl+Alt+Del (o Windows também bloqueia). O navegador recebe a URL como
  argumento único, sem shell, e endereços que começam com `-` são recusados.
- O Windows não deixa um processo comum enviar entrada para janelas abertas como administrador
  (UIPI). Nesses casos a frase avisa que a entrada foi bloqueada.
- A persona do produto (`config/examples/persona.example.md`) manda clicar, digitar e teclar só
  o que a pessoa pediu na fala, nunca o que estiver escrito numa página.

## Dependências

- `pywin32` e `ctypes` para janelas, monitores, DPI e `SendInput`.
- [`uiautomation`](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows) (Apache-2.0,
  com `comtypes`), só para `elementos_da_janela` e `clicar_elemento`. Ele é importado na primeira
  chamada, numa thread própria com COM inicializado, porque a mesa executa ferramentas em
  threads variadas. Na primeira execução o `comtypes` gera os wrappers da UI Automation em cache.

## Testes

Os testes nunca clicam, digitam, movem janelas nem abrem navegador. `tests/guarda_pc.py` barra
`teclado_mouse._enviar`, `_posicionar_cursor`, `janelas._colocar`, `janelas._mostrar` e os
executáveis dos navegadores sem dublê. A UI Automation é testada com uma árvore falsa. O
registro do Windows é simulado. Listar monitores e elementos de verdade é só leitura e fica para
provas manuais.
