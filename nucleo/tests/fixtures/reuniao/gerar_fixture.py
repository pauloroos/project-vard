"""Gera a transcrição sintética de 40 min usada nos testes e na prova viva da ata (determinística).

Rodar: uv run python tests/fixtures/reuniao/gerar_fixture.py
Saídas: transcricao-40min.jsonl e transcricao-40min.esperado.json (palavras-chave que a ata precisa conter).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

AQUI = Path(__file__).resolve().parent
TOTAL_S = 2400
N_FALAS = 240
ABERTURAS = ["", "", "Então, ", "Olha, ", "Veja bem, ", "Pois é, ", "Na real, ", "Acho que ", "Sinceramente, "]

# (tema, falas de enchimento). Cada tema ocupa um quarto da reunião.
TEMAS = [
    ("orçamento", [
        "o orçamento do trimestre está apertado porque o custo com infraestrutura subiu bem mais do que a gente previa",
        "eu abri a planilha ontem à noite e as despesas de marketing passaram do limite que combinamos no começo do mês",
        "se a gente não segurar os gastos com ferramentas, vai faltar verba para a campanha de novembro",
        "o financeiro pediu que a gente justifique cada linha acima de dois mil reais antes de aprovar o próximo repasse",
        "comparando com o trimestre passado, a diferença maior está nas assinaturas de software que ninguém revisou",
        "eu prefiro cortar agora do que pedir complemento de verba daqui a dois meses e ouvir um não",
        "a previsão de receita ainda é conservadora, então não dá para contar com sobra no fim do período",
        "alguns contratos renovam sozinhos e a gente só descobre quando a cobrança aparece no cartão da empresa",
        "vale separar o que é gasto fixo do que é gasto de projeto, senão a planilha fica impossível de ler",
        "o diretor quer ver um número fechado até o fim da reunião, nada de faixa de valores ou estimativa vaga",
        "a gente já cortou o que dava nas viagens, agora o corte tem que vir de ferramentas e de serviço terceirizado",
        "eu entendo a preocupação, mas qualidade não pode cair só porque a conta apertou neste trimestre",
    ]),
    ("paginação", [
        "a paginação da listagem de clientes está lenta porque ela ainda carrega todos os registros antes de cortar a página",
        "no ambiente de teste, a tela com dez mil clientes leva mais de oito segundos para abrir, o que é inaceitável",
        "a ideia é paginar no servidor e devolver só vinte itens por vez, com o total calculado numa consulta separada",
        "o desenho novo prevê rolagem infinita no celular e botões de página no computador, o que complica um pouco",
        "eu testei a consulta com índice e o tempo caiu para trezentos milissegundos, então o gargalo era mesmo o banco",
        "o problema é que o filtro por data quebra a contagem total quando o usuário troca de página depressa",
        "precisamos combinar o formato da resposta da API com o pessoal do aplicativo, senão eles refazem tudo depois",
        "se a gente entregar a paginação incompleta, o cliente grande vai continuar reclamando da lentidão toda semana",
        "eu pensei em reaproveitar o componente de tabela que já existe, só trocando a fonte dos dados por uma chamada paginada",
        "a ordenação por coluna também precisa ir para o servidor, porque ordenar só a página atual confunde o usuário",
        "o time de suporte já recebeu onze reclamações por causa dessa tela só nesta semana, vale priorizar mesmo",
        "depois de pronto, a gente mede de novo com o volume real de produção antes de dar o trabalho por encerrado",
    ]),
    ("bug do login", [
        "o bug do login aparece quando a pessoa deixa a aba aberta por mais de uma hora e tenta salvar alguma coisa",
        "a sessão expira no servidor, mas a tela continua parecendo logada, e o usuário perde o que digitou",
        "eu consegui reproduzir três vezes no meu computador, sempre depois de a sessão ficar parada por bastante tempo",
        "nos registros de erro aparece um token vencido sendo reenviado, e o servidor responde com erro de autorização",
        "a correção provável é renovar o token de forma silenciosa um pouco antes de vencer, sem deslogar ninguém",
        "outra opção seria avisar o usuário que a sessão acabou e guardar o rascunho localmente para ele não perder nada",
        "isso afeta principalmente quem usa o sistema o dia inteiro, que é justamente o nosso cliente mais importante",
        "já tem gente pedindo para aumentar o tempo da sessão, mas isso só esconde o problema e piora a segurança",
        "eu não queria mexer em autenticação perto de uma entrega grande, o risco de quebrar o acesso de todo mundo é real",
        "vamos precisar de um teste automático para esse cenário, senão o bug volta na próxima refatoração sem ninguém notar",
        "o pessoal do suporte disse que a maioria dos chamados vem de segunda de manhã, quando as sessões do fim de semana vencem",
        "enquanto não corrige, dá para orientar o suporte a pedir que o cliente recarregue a página antes de salvar",
    ]),
    ("contratação", [
        "sobre a contratação, o time está sobrecarregado e a gente precisa decidir que perfil falta mais agora",
        "eu sinto que o gargalo não é escrever código novo, é garantir que o que a gente já escreve funcione direito",
        "o último ciclo teve muito retrabalho porque os erros só apareciam depois que o cliente já tinha usado a funcionalidade",
        "contratar alguém sênior demora, em média, dois meses entre abrir a vaga e a pessoa começar a trabalhar",
        "a faixa salarial que o financeiro liberou cobre uma pessoa pleno, não duas, então a escolha precisa ser cuidadosa",
        "eu conversei com dois candidatos indicados e ambos têm experiência com automação de testes, o que ajudaria bastante",
        "se a gente trouxer mais um desenvolvedor, ele vai gastar o primeiro mês só aprendendo o sistema com a gente ao lado",
        "o processo seletivo precisa ser curto, no máximo três etapas, senão perdemos bons candidatos para empresas maiores",
        "a vaga pode ser remota, o que amplia bastante o número de candidatos e ajuda a fechar mais rápido",
        "vale combinar com o pessoal de recursos humanos quem participa das entrevistas técnicas para não repetir perguntas",
        "eu gostaria de que a pessoa nova começasse antes do fim do ano, para pegar o planejamento do próximo trimestre desde o início",
        "no fim das contas, o que importa é reduzir o retrabalho e ganhar previsibilidade nas entregas do time",
    ]),
]

# (índice da fala, trilha, texto, palavras-chave alternativas). Decisões ditas por Carlos.
DECISOES = [
    (22, "eu", "Então fica decidido: o orçamento do trimestre fecha em R$ 45 mil, sem complemento, e a gente vive com isso.",
     ["45 mil", "45.000", "45000"]),
    (48, "eu", "Decidido também: a gente cancela a licença extra do Figma, porque ninguém está usando aquela vaga.",
     ["figma", "licença"]),
    (82, "eu", "Fechado então, a paginação da listagem de clientes vai ser entregue até 30 de outubro, sem exceção.",
     ["30/10", "30 de outubro", "outubro"]),
    (112, "eu", "Decisão tomada: a reunião semanal passa para terça-feira às 10h, porque segunda de manhã ninguém consegue.",
     ["terça"]),
    (142, "eu", "Combinado, o bug de sessão expirando entra antes de qualquer funcionalidade nova no próximo ciclo.",
     ["sessão", "sessao"]),
    (200, "eu", "Então a decisão é contratar uma pessoa de QA, e não mais um desenvolvedor, para reduzir o retrabalho.",
     ["qa"]),
]
# (índice, trilha, falante, texto, palavras-chave, responsável). Ditas por quem assume.
PENDENCIAS = [
    (30, "outros", 1, "Ana, a planilha do orçamento revisada fica comigo, entrego até sexta-feira. Pode anotar o meu nome.",
     ["planilha"], "Ana"),
    (92, "outros", 2, "Eu fico com o protótipo da paginação e mostro para todo mundo até 25 de outubro, pode anotar.",
     ["protótipo", "prototipo"], "Bruno"),
    (150, "eu", None, "Eu mesmo vou reproduzir o bug do login em produção até quarta-feira e trago os registros.",
     ["reproduzir", "login"], "Carlos"),
    (205, "outros", 1, "Eu abro a vaga de QA no LinkedIn amanhã e já deixo o roteiro de entrevista combinado.",
     ["vaga"], "Ana"),
    (225, "outros", 2, "Eu peço a cotação do Figma ao financeiro até o fim da semana, para a gente comparar os planos.",
     ["cotação", "cotacao"], "Bruno"),
]


def gerar() -> tuple[list[dict], dict]:
    rng = random.Random(13)
    fixas: dict[int, tuple] = {}
    for i, quem, texto, _ in DECISOES:
        fixas[i] = (quem, None, texto)
    for i, quem, falante, texto, _, _ in PENDENCIAS:
        fixas[i] = (quem, falante, texto)

    duracoes = [rng.randint(4, 12) for _ in range(N_FALAS)]
    folga = (TOTAL_S - sum(duracoes)) / N_FALAS
    falas, t = [], 0.0
    for i in range(N_FALAS):
        if i in fixas:
            quem, falante, texto = fixas[i]
        else:
            tema = TEMAS[min(i * len(TEMAS) // N_FALAS, len(TEMAS) - 1)][1]
            texto = rng.choice(ABERTURAS) + rng.choice(tema)
            texto = texto[0].upper() + texto[1:] + rng.choice([".", ".", ".", ", entende?", ", né?"])
            quem = "eu" if rng.random() < 0.4 else "outros"
            falante = None if quem == "eu" else rng.choice([1, 2])
        falas.append({"t0": round(t, 1), "t1": round(t + duracoes[i], 1), "trilha": quem, "falante": falante, "texto": texto})
        t += duracoes[i] + folga
    inicio = {"t0": 0.0, "t1": 0.0, "trilha": "sistema", "falante": None, "texto": "reunião iniciada"}
    fim = {"t0": float(TOTAL_S), "t1": float(TOTAL_S), "trilha": "sistema", "falante": None, "texto": "reunião encerrada"}
    esperado = {
        "decisoes": [{"texto": d[2], "palavras_chave": d[3]} for d in DECISOES],
        "pendencias": [{"texto": p[3], "responsavel": p[5], "palavras_chave": p[4]} for p in PENDENCIAS],
    }
    return [inicio, *falas, fim], esperado


if __name__ == "__main__":
    falas, esperado = gerar()
    with (AQUI / "transcricao-40min.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for fala in falas:
            f.write(json.dumps(fala, ensure_ascii=False) + "\n")
    (AQUI / "transcricao-40min.esperado.json").write_text(
        json.dumps(esperado, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
