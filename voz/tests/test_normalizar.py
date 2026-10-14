import pytest

from vard_voz.normalizar import normalizar


@pytest.mark.parametrize("entrada,esperado", [
    # pontuação final
    ("Oi, usuário.", "Oi, usuário"),
    ("Pronto, usuário. O YouTube já está aberto.", "Pronto, usuário. O YouTube já está aberto"),
    ("Já está aberto!", "Já está aberto"),
    ("Você quer que eu abra?", "Você quer que eu abra?"),
    ("Abra?!", "Abra?"),
    ("Espera... já vou…", "Espera, já vou"),
    ("Deixa... eu vejo.", "Deixa, eu vejo"),
    ('"Oi, usuário."', "Oi, usuário"),
    # Markdown
    ("**Pronto!** Já está aberto.", "Pronto! Já está aberto"),
    ("Veja *isto* e _aquilo_.", "Veja isto e aquilo"),
    ("Rode `ls` agora.", "Rode ls agora"),
    ("## Título", "Título"),
    ("- primeiro\n- segundo", "primeiro, segundo"),
    ("• item um", "item um"),
    ("Abra [o site](https://exemplo.com/x) já.", "Abra o site já"),
    # horas
    ("São 18h05.", "São dezoito e cinco"),
    ("São 18h.", "São dezoito horas"),
    ("São 18:05.", "São dezoito e cinco"),
    ("São 18:05:30.", "São dezoito e cinco e trinta segundos"),
    ("É 1h.", "É uma hora"),
    ("É 1:05.", "É uma e cinco"),
    ("Meio-dia: 12h.", "Meio-dia: doze horas"),
    ("Dr. usuário chegou às 7h30!", "doutor usuário chegou às sete e trinta"),
    # números
    ("Tenho 3,5 litros.", "Tenho três vírgula cinco litros"),
    ("Tenho 1.200 itens.", "Tenho mil e duzentos itens"),
    ("Custa 1.200,50 no total.", "Custa mil e duzentos vírgula cinquenta no total"),
    ("Estamos em 2026.", "Estamos em dois mil e vinte e seis"),
    ("Faltam 21 dias.", "Faltam vinte e um dias"),
    ("Fez -3 hoje.", "Fez menos três hoje"),
    ("Deu 0,05.", "Deu zero vírgula zero cinco"),
    ("É o 1º lugar e a 2ª vez.", "É o primeiro lugar e a segunda vez"),
    ("Subiu 25%.", "Subiu vinte e cinco por cento"),
    # valores
    ("Custa R$ 12,50.", "Custa doze reais e cinquenta centavos"),
    ("Custa R$ 1,00.", "Custa um real"),
    ("Custa R$ 0,50.", "Custa cinquenta centavos"),
    ("Custa R$ 1.200,50, uns 25% a mais.", "Custa mil e duzentos reais e cinquenta centavos, uns vinte e cinco por cento a mais"),
    ("Custa R$ 3.", "Custa três reais"),
    # unidades
    ("Andei 5 km.", "Andei cinco quilômetros"),
    ("Andei 1 km.", "Andei um quilômetro"),
    ("Pesa 70 kg.", "Pesa setenta quilos"),
    ("Faz 25°C.", "Faz vinte e cinco graus"),
    ("Faz -3,5 °C.", "Faz menos três vírgula cinco graus"),
    ("Vai a 80 km/h.", "Vai a oitenta quilômetros por hora"),
    # datas
    ("Dia 13/10/2026.", "Dia treze de outubro de dois mil e vinte e seis"),
    ("Dia 01/01/2027.", "Dia primeiro de janeiro de dois mil e vinte e sete"),
    ("A reunião é dia 13/10/2026 às 9h.", "A reunião é dia treze de outubro de dois mil e vinte e seis às nove horas"),
    # URLs e e-mails
    ("Abri o youtube.com pra você.", "Abri o youtube ponto com pra você"),
    ("Abri https://www.exemplo.com.br agora.", "Abri exemplo ponto com ponto br agora"),
    ("Escreva para a@b.com.", "Escreva para a arroba b ponto com"),
    # abreviações
    ("Dr. Silva e Sra. Ana.", "doutor Silva e senhora Ana"),
    ("Frutas, etc. e tal.", "Frutas, etcétera e tal"),
    ("Isso, p. ex. aquilo.", "Isso, por exemplo aquilo"),
    ("Corra a 10 km/h.", "Corra a dez quilômetros por hora"),
    # espaços
    ("  muito    espaço   aqui  ", "muito espaço aqui"),
])
def test_normalizar(entrada, esperado):
    assert normalizar(entrada) == esperado


@pytest.mark.parametrize("entrada", ["...", "!!!", "**", "?"])
def test_nunca_vazio(entrada):
    assert normalizar(entrada) != ""


def test_sem_digitos_nem_ponto_final():
    r = normalizar("São 18h05. Custa R$ 1.200,50 em 13/10/2026.")
    assert not any(ch.isdigit() for ch in r) and not r.endswith(".")
