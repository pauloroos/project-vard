"""Gera o icone (1024 px, fundo transparente) do nucleo ciano: aneis em arco e brilho central.

Uso: python scripts/gerar-icone.py [saida.png]   (precisa do Pillow)
Depois: npx tauri icon <saida.png>
"""
import math
import sys

from PIL import Image, ImageDraw, ImageFilter

N = 1024
C = N // 2
CIANO = (0, 240, 255)
AZUL = (0, 162, 255)


def camada():
    return Image.new("RGBA", (N, N), (0, 0, 0, 0))


def arco(d, raio, largura, ini, fim, cor, alfa):
    caixa = [C - raio, C - raio, C + raio, C + raio]
    d.arc(caixa, ini, fim, fill=cor + (alfa,), width=largura)


brilho = camada()
db = ImageDraw.Draw(brilho)
nitido = camada()
dn = ImageDraw.Draw(nitido)

# aneis em arco: raio, largura, giro, extensao, cor, alfa
aneis = [
    (430, 14, 20, 250, CIANO, 150),
    (370, 20, 140, 290, CIANO, 200),
    (305, 26, 260, 230, AZUL, 230),
    (240, 20, 40, 300, CIANO, 255),
    (180, 28, 200, 210, CIANO, 255),
    (125, 20, 320, 260, AZUL, 255),
]
for raio, larg, giro, ext, cor, alfa in aneis:
    arco(db, raio, larg + 18, giro, giro + ext, cor, alfa)
    arco(dn, raio, larg, giro, giro + ext, cor, alfa)

# vortice: pontos em espiral entre os aneis
for i in range(140):
    t = i / 140
    ang = t * 6 * math.pi
    r = 70 + t * 380
    x, y = C + r * math.cos(ang), C + r * math.sin(ang)
    s = 3 + 7 * (1 - t)
    dn.ellipse([x - s, y - s, x + s, y + s], fill=CIANO + (int(255 * (1 - t * 0.6)),))

# nucleo
for r, a in ((95, 70), (70, 120), (48, 200)):
    db.ellipse([C - r, C - r, C + r, C + r], fill=CIANO + (a,))
dn.ellipse([C - 34, C - 34, C + 34, C + 34], fill=(220, 255, 255, 255))

brilho = brilho.filter(ImageFilter.GaussianBlur(22))
img = Image.alpha_composite(brilho, nitido)
img.save(sys.argv[1] if len(sys.argv) > 1 else "icone-1024.png")
