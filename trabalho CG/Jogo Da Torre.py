import ctypes
import math
from collections import namedtuple

import glfw
import numpy as np
from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader
from PIL import Image, ImageDraw, ImageFont

# ---------------- configuração de câmera ----------------

Camera_pos = np.array([0.0, 1.7, 5.0], dtype=np.float32)

camera_horizontal = -90.0
camera_vertical = 0.0

velocidade = 10.0
sensibilidade = 0.1

ultimoX = None
ultimoY = None

LARGURA, ALTURA = 1920, 1080
UP = np.array([0.0, 1.0, 0.0], dtype=np.float32)

# ---------------- colisão e limites do quarto ----------------

RAIO_JOGADOR = 0.3
ALTURA_OLHOS = 1.7
LIMITE_QUARTO = 9.9
ALTURA_QUARTO = 5.0
GRADE = 0.1
ALCANCE_INTERACAO = 8.0
GRAUS_SCROLL = 15
MAX_LUZES = 8

caixas = []

# ---------------- estado do modo de posicionamento ----------------

janela = None
modo_posicao = False
indice = 0
rot_fantasma = 0.0
fantasma = None
fantasma_valido = False

itens = []
cena = []
cena_topo = []
luzes_ativas = []

# ---------------- catálogo ----------------

catalogo_aberto = False
categoria_ativa = 0

# ---------------- vista de cima (modo de posicionamento) ----------------

ALTURA_TOPO = 30.0
ZOOM_TOPO = 11.0
VELOCIDADE_PAN = 8.0
foco = np.array([0.0, 0.0], dtype=np.float32)

# ---------------- programas e buffers de UI ----------------

programa_3d = None
programa_ui = None
ui_loc = {}
ui_vao = None
ui_vbo = None

# ---------------- shaders ----------------

VERTEX_SHADER = """
#version 330 core
layout (location = 0) in vec3 aPos;
layout (location = 1) in vec3 aNormal;

uniform mat4 uModel;
uniform mat4 uView;
uniform mat4 uProjection;
uniform mat3 uNormalMatrix;

out vec3 vNormal;
out vec3 vPos;

void main()
{
    vec4 mundo = uModel * vec4(aPos, 1.0);
    vPos = mundo.xyz;
    gl_Position = uProjection * uView * mundo;
    vNormal = uNormalMatrix * aNormal;
}
"""

FRAGMENT_SHADER = """
#version 330 core
#define MAX_LUZES 8

in vec3 vNormal;
in vec3 vPos;

uniform vec3 uCor;
uniform vec3 uDirLuz;
uniform float uEmissivo;
uniform float uFantasma;
uniform vec3 uTom;

uniform int uNumLuzes;
uniform vec3 uLuzPos[MAX_LUZES];
uniform vec3 uLuzCor[MAX_LUZES];
uniform float uLuzRaio[MAX_LUZES];

out vec4 FragColor;

void main()
{
    vec3 n = normalize(vNormal);

    vec3 lum = vec3(0.12 + 0.4 * max(dot(n, uDirLuz), 0.0));

    for (int i = 0; i < uNumLuzes; i++) {
        vec3 d = uLuzPos[i] - vPos;
        float dist = length(d);
        float att = max(1.0 - dist / uLuzRaio[i], 0.0);
        att *= att;
        lum += uLuzCor[i] * att * max(dot(n, d / max(dist, 1e-4)), 0.0);
    }

    vec3 cor = mix(uCor * lum, uCor, uEmissivo);

    if (uFantasma > 0.5) {
        FragColor = vec4(mix(cor, uTom, 0.5), 0.5);
    } else {
        FragColor = vec4(cor, 1.0);
    }
}
"""

UI_VERTEX = """
#version 330 core
layout (location = 0) in vec2 aPos;
layout (location = 1) in vec2 aUV;

uniform vec2 uTela;

out vec2 vUV;

void main()
{
    vec2 ndc = vec2(aPos.x / uTela.x * 2.0 - 1.0, 1.0 - aPos.y / uTela.y * 2.0);
    gl_Position = vec4(ndc, 0.0, 1.0);
    vUV = aUV;
}
"""

UI_FRAGMENT = """
#version 330 core
in vec2 vUV;

uniform vec4 uCor;
uniform sampler2D uTex;
uniform int uUsaTex;

out vec4 FragColor;

void main()
{
    vec4 c = uCor;
    if (uUsaTex == 1) {
        c *= texture(uTex, vUV);
    }
    FragColor = c;
}
"""

# ---------------- matrizes ----------------

def perspectiva(fov_graus, aspecto, perto, longe):
    f = 1.0 / math.tan(math.radians(fov_graus) / 2.0)
    return np.array([
        [f / aspecto, 0, 0, 0],
        [0, f, 0, 0],
        [0, 0, (longe + perto) / (perto - longe), (2 * longe * perto) / (perto - longe)],
        [0, 0, -1, 0],
    ], dtype=np.float32)


def ortho(esq, dir_, baixo, topo, perto, longe):
    m = np.identity(4, dtype=np.float32)
    m[0, 0] = 2 / (dir_ - esq)
    m[0, 3] = -(dir_ + esq) / (dir_ - esq)
    m[1, 1] = 2 / (topo - baixo)
    m[1, 3] = -(topo + baixo) / (topo - baixo)
    m[2, 2] = -2 / (longe - perto)
    m[2, 3] = -(longe + perto) / (longe - perto)
    return m


def look_at(olho, alvo, cima):
    f = alvo - olho
    f = f / np.linalg.norm(f)
    s = np.cross(f, cima)
    s = s / np.linalg.norm(s)
    u = np.cross(s, f)

    m = np.identity(4, dtype=np.float32)
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -np.dot(s, olho)
    m[1, 3] = -np.dot(u, olho)
    m[2, 3] = np.dot(f, olho)
    return m


def matriz_translacao(pos):
    m = np.identity(4, dtype=np.float32)
    m[:3, 3] = pos
    return m


def matriz_modelo(pos, escala):
    m = np.identity(4, dtype=np.float32)
    m[0, 0], m[1, 1], m[2, 2] = escala
    m[:3, 3] = pos
    return m


def rotacao_y(graus):
    a = math.radians(graus)
    c, s = math.cos(a), math.sin(a)
    m = np.identity(4, dtype=np.float32)
    m[0, 0] = c
    m[0, 2] = s
    m[2, 0] = -s
    m[2, 2] = c
    return m


def projecao_atual():
    w, h = tamanho_janela()
    aspecto = w / h
    if modo_posicao:
        return ortho(-ZOOM_TOPO * aspecto, ZOOM_TOPO * aspecto, -ZOOM_TOPO, ZOOM_TOPO, 0.1, 100)
    return perspectiva(60, aspecto, 0.1, 100)

# ---------------- malhas ----------------

class Malha:
    def __init__(self, vertices):
        self.count = len(vertices) // 6
        self.vao = glGenVertexArrays(1)
        vbo = glGenBuffers(1)

        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)

        stride = 6 * 4
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(12))

        glBindVertexArray(0)

    def desenhar(self):
        glBindVertexArray(self.vao)
        glDrawArrays(GL_TRIANGLES, 0, self.count)


def dados_cubo():
    faces = [
        (( 0, 0, 1), ( 1, 0, 0), ( 0, 1, 0)),
        (( 0, 0,-1), ( 1, 0, 0), ( 0, 1, 0)),
        (( 1, 0, 0), ( 0, 0, 1), ( 0, 1, 0)),
        ((-1, 0, 0), ( 0, 0, 1), ( 0, 1, 0)),
        (( 0, 1, 0), ( 1, 0, 0), ( 0, 0, 1)),
        (( 0,-1, 0), ( 1, 0, 0), ( 0, 0, 1)),
    ]
    cantos = [(-1, -1), (1, -1), (1, 1), (-1, 1)]

    verts = []
    for n, u, v in faces:
        n = np.array(n, dtype=np.float32)
        u = np.array(u, dtype=np.float32)
        v = np.array(v, dtype=np.float32)
        pontos = [n * 0.5 + (sx * u + sy * v) * 0.5 for sx, sy in cantos]
        for i in (0, 1, 2, 0, 2, 3):
            verts.extend(pontos[i].tolist())
            verts.extend(n.tolist())
    return np.array(verts, dtype=np.float32)


def dados_piso(tam=10.0):
    n = (0.0, 1.0, 0.0)
    pontos = [(-tam, 0, -tam), (tam, 0, -tam), (tam, 0, tam), (-tam, 0, tam)]
    verts = []
    for i in (0, 1, 2, 0, 2, 3):
        verts.extend(pontos[i])
        verts.extend(n)
    return np.array(verts, dtype=np.float32)


def dados_cilindro(seg=24, r=0.5, h=0.5):
    verts = []

    def v(p, n):
        verts.extend(p)
        verts.extend(n)

    for i in range(seg):
        a0 = 2 * math.pi * i / seg
        a1 = 2 * math.pi * (i + 1) / seg
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)

        n0 = (c0, 0, s0)
        n1 = (c1, 0, s1)
        b0 = (r * c0, -h, r * s0)
        b1 = (r * c1, -h, r * s1)
        t0 = (r * c0, h, r * s0)
        t1 = (r * c1, h, r * s1)

        v(b0, n0); v(b1, n1); v(t1, n1)
        v(b0, n0); v(t1, n1); v(t0, n0)

        v((0, h, 0), (0, 1, 0)); v(t0, (0, 1, 0)); v(t1, (0, 1, 0))
        v((0, -h, 0), (0, -1, 0)); v(b1, (0, -1, 0)); v(b0, (0, -1, 0))

    return np.array(verts, dtype=np.float32)


def dados_esfera(stacks=16, slices=24, r=0.5):
    def ponto(i, j):
        t = math.pi * i / stacks
        f = 2 * math.pi * j / slices
        n = np.array([math.sin(t) * math.cos(f), math.cos(t), math.sin(t) * math.sin(f)],
                     dtype=np.float32)
        return n * r, n

    verts = []
    for i in range(stacks):
        for j in range(slices):
            a = ponto(i, j)
            b = ponto(i + 1, j)
            c = ponto(i + 1, j + 1)
            d = ponto(i, j + 1)
            for p, n in (a, b, c, a, c, d):
                verts.extend(p.tolist())
                verts.extend(n.tolist())
    return np.array(verts, dtype=np.float32)


MALHAS = {}
MEIO_MALHA = {"cubo": 0.5, "cilindro": 0.5, "esfera": 0.5, "piso": 10.0}

# ---------------- definição dos móveis ----------------

Peca = namedtuple("Peca", "malha cor pos escala emissivo solido")


def P(malha, cor, pos, escala, emissivo=0.0, solido=True):
    return Peca(malha, cor, pos, escala, emissivo, solido)


def pernas(cor, pontos, y=0.45, altura=0.9):
    return [P("cubo", cor, (x, y, z), (0.15, altura, 0.15)) for x, z in pontos]


def luz(pos, cor, intensidade=1.0, raio=5.0):
    return (pos, cor, intensidade, raio)


def peca_parede(eixo, fixo, s0, s1, y0, y1, esp, cor, emissivo=0.0, solido=True):
    sc = (s0 + s1) / 2
    yc = (y0 + y1) / 2
    sl = s1 - s0
    yl = y1 - y0
    if eixo == "x":
        return P("cubo", cor, (sc, yc, fixo), (sl, yl, esp), emissivo, solido)
    return P("cubo", cor, (fixo, yc, sc), (esp, yl, sl), emissivo, solido)


def parede(eixo, fixo, inicio, fim, janelas=(), altura=ALTURA_QUARTO, esp=0.2, cor=(0.5, 0.5, 0.5)):
    pecas = []
    pontos = sorted({inicio, fim, *[v for jan in janelas for v in jan[:2]]})
    for a, b in zip(pontos, pontos[1:]):
        meio = (a + b) / 2
        jan = next((j for j in janelas if j[0] <= meio <= j[1]), None)
        if jan is None:
            pecas.append(peca_parede(eixo, fixo, a, b, 0, altura, esp, cor))
        else:
            _, _, y0, y1 = jan
            if y0 > 0:
                pecas.append(peca_parede(eixo, fixo, a, b, 0, y0, esp, cor))
            if y1 < altura:
                pecas.append(peca_parede(eixo, fixo, a, b, y1, altura, esp, cor))
    return pecas


def teto(cor=(0.42, 0.40, 0.38)):
    return [P("cubo", cor, (0, ALTURA_QUARTO + 0.1, 0), (20, 0.2, 20), solido=False)]


def criar_janela(eixo, fixo, s0, s1, y0, y1, esp=0.2):
    borda = 0.08
    madeira = (0.3, 0.18, 0.08)
    vidro = (0.55, 0.78, 0.95)
    return [
        peca_parede(eixo, fixo, s0, s1, y1 - borda, y1, esp, madeira, solido=False),
        peca_parede(eixo, fixo, s0, s1, y0, y0 + borda, esp, madeira, solido=False),
        peca_parede(eixo, fixo, s0, s0 + borda, y0 + borda, y1 - borda, esp, madeira, solido=False),
        peca_parede(eixo, fixo, s1 - borda, s1, y0 + borda, y1 - borda, esp, madeira, solido=False),
        peca_parede(eixo, fixo, s0 + borda, s1 - borda, y0 + borda, y1 - borda,
                    esp * 0.25, vidro, emissivo=0.4, solido=True),
    ]


MADEIRA = (0.4, 0.2, 0.1)
MADEIRA_ESCURA = (0.35, 0.18, 0.08)
PAREDE = (0.5, 0.5, 0.5)
PRETO = (0.0, 0.0, 0.0)

JANELAS_ESQ = [(-6, -4, 0.5, 3.5), (4, 6, 0.5, 3.5)]

MOVEIS = {}
LUZES_MODELO = {}


def definir_movel(nome, pecas, luzes=()):
    MOVEIS[nome] = pecas
    LUZES_MODELO[nome] = list(luzes)


definir_movel("chao", [
    P("piso", (0.2, 0.2, 0.1), (0, 0, 0), (1, 1, 1), solido=False),
])

definir_movel("quarto", [
    *parede("x", -10, -10, 10),
    *parede("x", 10, -10, 10),
    *parede("z", 10, -10, 10),
    *parede("z", -10, -10, 10, janelas=JANELAS_ESQ),
    *criar_janela("z", -10, -6, -4, 0.5, 3.5),
    *criar_janela("z", -10, 4, 6, 0.5, 3.5),
    *teto(),
])

definir_movel("tapete", [
    P("cubo", (0.45, 0.1, 0.1), (0, 0.01, 0), (4, 0.02, 3), solido=False),
])

definir_movel("mesa", [
    P("cubo", MADEIRA, (0, 1.0, 0), (2, 0.3, 1.5)),
    *pernas(MADEIRA, [(-0.85, -0.6), (0.85, -0.6), (-0.85, 0.6), (0.85, 0.6)]),
])

definir_movel("cadeira", [
    P("cubo", MADEIRA, (0, 1.0, 0), (1.5, 0.2, 1.4)),
    *pernas(MADEIRA, [(-0.6, -0.55), (0.6, -0.55), (-0.6, 0.55), (0.6, 0.55)], y=0.5),
    P("cubo", MADEIRA, (0, 1.8, -0.6), (1.5, 1.4, 0.2)),
])

definir_movel("estante", [
    P("cubo", MADEIRA_ESCURA, (-1.0, 1.5, 0), (0.2, 3.0, 0.6)),
    P("cubo", MADEIRA_ESCURA, (1.0, 1.5, 0), (0.2, 3.0, 0.6)),
    P("cubo", MADEIRA_ESCURA, (0, 0.1, 0), (2.2, 0.2, 0.7)),
    P("cubo", MADEIRA_ESCURA, (0, 3.0, 0), (2.2, 0.2, 0.7)),
    P("cubo", MADEIRA_ESCURA, (0, 1.1, 0), (1.8, 0.15, 0.65)),
    P("cubo", MADEIRA_ESCURA, (0, 2.0, 0), (1.8, 0.15, 0.65)),
    P("cubo", (0.35, 0.38, 0.38), (0, 1.6, -0.3), (2, 2.8, 0.1), solido=False),
])

definir_movel("cama", [
    P("cubo", (0.45, 0.25, 0.12), (0, 0.35, 0), (1.8, 0.7, 3.2)),
    P("cubo", (0.85, 0.82, 0.75), (0, 0.825, 0), (1.7, 0.25, 3.0), solido=False),
    P("cubo", (0.5, 0.1, 0.15), (0, 0.97, 0.4), (1.75, 0.04, 1.9), solido=False),
    P("cubo", (0.95, 0.95, 0.95), (0, 1.0, -1.0), (1.2, 0.2, 0.5), solido=False),
    P("cubo", (0.45, 0.25, 0.12), (0, 0.95, -1.7), (1.9, 1.9, 0.2)),
])

TOPO_ESCRIVANINHA = 1.075
_livros = [((0.6, 0.1, 0.1), 0.30, -0.7), ((0.1, 0.3, 0.6), 0.25, -0.4), ((0.2, 0.5, 0.2), 0.35, -0.1)]
_escrivaninha = [
    P("cubo", MADEIRA, (0, 1.0, 0), (2.2, 0.15, 0.9)),
    P("cubo", MADEIRA, (-1.0, 0.5, 0), (0.1, 1.0, 0.8)),
    P("cubo", MADEIRA, (1.0, 0.5, 0), (0.1, 1.0, 0.8)),
]
for _cor, _h, _dx in _livros:
    _escrivaninha.append(P("cubo", _cor, (_dx, TOPO_ESCRIVANINHA + _h / 2, 0), (0.25, _h, 0.6), solido=False))
_escrivaninha.append(P("cilindro", (0.95, 0.92, 0.8), (0.6, TOPO_ESCRIVANINHA + 0.15, 0), (0.12, 0.3, 0.12), solido=False))
_escrivaninha.append(P("esfera", (1.0, 0.6, 0.1), (0.6, TOPO_ESCRIVANINHA + 0.37, 0), (0.1, 0.16, 0.1), emissivo=1.0, solido=False))
definir_movel("escrivaninha", _escrivaninha)

definir_movel("bau", [
    P("cubo", (0.45, 0.28, 0.12), (0, 0.3, 0), (1.2, 0.6, 0.8)),
    P("cubo", (0.5, 0.33, 0.15), (0, 0.7, 0), (1.2, 0.2, 0.8), solido=False),
    P("cubo", (0.85, 0.7, 0.2), (0, 0.55, 0.42), (0.15, 0.2, 0.05), solido=False),
])

CALDEIRAO_CORPO = (0.12, 0.12, 0.14)
FERRO = (0.25, 0.25, 0.28)
FERRO_ESCURO = (0.15, 0.15, 0.17)
LENHA = (0.35, 0.18, 0.08)

definir_movel("caldeirao", [
    P("esfera", CALDEIRAO_CORPO, (0, 0.75, 0), (1.0, 0.8, 1.0)),
    P("cilindro", FERRO_ESCURO, (0, 1.13, 0), (1.1, 0.08, 1.1), solido=False),
    P("cilindro", (0.2, 0.85, 0.3), (0, 1.1, 0), (0.85, 0.02, 0.85), emissivo=0.6, solido=False),
    P("cubo", FERRO, (-0.55, 1.08, 0), (0.12, 0.1, 0.25), solido=False),
    P("cubo", FERRO, (0.55, 1.08, 0), (0.12, 0.1, 0.25), solido=False),
    *[P("cubo", FERRO_ESCURO, (x, 0.2, z), (0.12, 0.4, 0.12), solido=False)
      for x, z in [(-0.35, -0.35), (0.35, -0.35), (-0.35, 0.35), (0.35, 0.35)]],
    P("cubo", LENHA, (0, 0.02, 0), (0.7, 0.05, 0.12), solido=False),
    P("cubo", LENHA, (0, 0.02, 0), (0.12, 0.05, 0.7), solido=False),
    P("esfera", (1.0, 0.45, 0.1), (0, 0.12, 0), (0.3, 0.3, 0.3), emissivo=1.0, solido=False),
])

definir_movel("pedestal", [
    P("cilindro", (0.5, 0.5, 0.55), (0, 0.5, 0), (0.6, 1.0, 0.6)),
    P("esfera", (0.3, 0.8, 1.0), (0, 1.4, 0), (0.45, 0.6, 0.45), emissivo=0.7, solido=False),
], luzes=[
    luz((0, 1.4, 0), (0.3, 0.8, 1.0), intensidade=1.4, raio=5.0),
])

# Móveis que o jogador pode colocar (os fixos ficam de fora)
DISPONIVEIS = [n for n in MOVEIS if n not in ("chao", "quarto")]

# ---------------- catálogo: categorias e informações ----------------
# (título, categoria, cor de exibição, descrição curta)

CATEGORIAS = ["Todos", "Dormir", "Estudar", "Guardar", "Sentar", "Magia", "Decorar"]

CATALOGO = {
    "mesa":         ("Mesa",          "Sentar",   MADEIRA,              "Mesa de madeira, quatro pernas"),
    "cadeira":      ("Cadeira",       "Sentar",   MADEIRA,              "Cadeira com encosto"),
    "estante":      ("Estante",       "Guardar",  MADEIRA_ESCURA,       "Prateleiras para livros"),
    "cama":         ("Cama",          "Dormir",   (0.45, 0.25, 0.12),   "Cama com cabeceira e cobertor"),
    "escrivaninha": ("Escrivaninha",  "Estudar",  MADEIRA,              "Mesa de estudo com vela"),
    "bau":          ("Baú",           "Guardar",  (0.45, 0.28, 0.12),   "Baú com fecho dourado"),
    "caldeirao":    ("Caldeirão",     "Magia",    (0.35, 0.35, 0.40),   "Caldeirão com caldo e chama"),
    "pedestal":     ("Pedestal",      "Magia",    (0.3, 0.8, 1.0),      "Pedestal que ilumina o quarto"),
    "tapete":       ("Tapete",        "Decorar",  (0.45, 0.1, 0.1),     "Tapete sem bloquear passagem"),
}


def info_catalogo(nome):
    return CATALOGO.get(nome, (nome, "Outros", (0.5, 0.5, 0.5), ""))


def nomes_filtrados():
    cat = CATEGORIAS[categoria_ativa]
    if cat == "Todos":
        return list(DISPONIVEIS)
    return [n for n in DISPONIVEIS if info_catalogo(n)[1] == cat]


# Disposição inicial do quarto: (nome, x, z, rotação)
MOVEIS_INICIAIS = [
    ("tapete", 0, 2, 0),
    ("mesa", 0, 0, 0),
    ("cadeira", 0, -2, 0),
    ("estante", 3, 9.5, 180),
    ("cama", 8.2, -6, 0),
    ("escrivaninha", 5, -9.1, 0),
    ("bau", 6, 4, 0),
    ("caldeirao", -4, 3, 0),
    ("pedestal", -4, -5, 0),
]

# ---------------- construção de itens ----------------

def caixa_de(m, meio):
    centro = m[:3, 3]
    extensao = np.abs(m[:3, :3]) @ np.full(3, meio, dtype=np.float64)
    return centro - extensao, centro + extensao


def construir_item(nome, x, z, rot, fixo=False):
    base = matriz_translacao((x, 0.0, z)) @ rotacao_y(rot)
    draw = []
    solidas = []
    bmin = np.full(3, np.inf)
    bmax = np.full(3, -np.inf)

    for peca in MOVEIS[nome]:
        m = base @ matriz_modelo(peca.pos, peca.escala)
        normal = np.linalg.inv(m[:3, :3]).T
        draw.append((
            MALHAS[peca.malha],
            peca.cor,
            m.astype(np.float32),
            normal.astype(np.float32),
            peca.emissivo,
        ))
        mn, mx = caixa_de(m, MEIO_MALHA[peca.malha])
        bmin = np.minimum(bmin, mn)
        bmax = np.maximum(bmax, mx)
        if peca.solido:
            solidas.append((mn, mx))

    luzes_item = []
    for lpos, lcor, intens, raio in LUZES_MODELO.get(nome, []):
        pos_mundo = (base @ np.array([*lpos, 1.0], dtype=np.float64))[:3]
        luzes_item.append({
            "pos": pos_mundo.astype(np.float32),
            "cor": np.array(lcor, dtype=np.float32) * intens,
            "raio": float(raio),
        })

    return {
        "nome": nome,
        "x": x,
        "z": z,
        "rot": rot,
        "fixo": fixo,
        "draw": draw,
        "caixas": solidas,
        "bbox": (bmin, bmax),
        "luzes": luzes_item,
    }


def reconstruir_mundo():
    global cena, cena_topo, caixas, luzes_ativas
    cena = []
    cena_topo = []
    caixas = []
    luzes_ativas = []
    for item in itens:
        cena.extend(item["draw"])
        caixas.extend(item["caixas"])
        luzes_ativas.extend(item["luzes"])
    cena_topo = [d for d in cena if d[2][1, 3] < ALTURA_QUARTO - 0.5 or d[2][1, 3] > ALTURA_QUARTO + 0.5]


def construir_cena():
    itens.clear()
    itens.append(construir_item("chao", 0, 0, 0, fixo=True))
    itens.append(construir_item("quarto", 0, 0, 0, fixo=True))
    for nome, x, z, rot in MOVEIS_INICIAIS:
        itens.append(construir_item(nome, x, z, rot))
    reconstruir_mundo()

# ---------------- validação de posição ----------------

def sobrepoe(a_min, a_max, b_min, b_max):
    return all(a_min[i] < b_max[i] and a_max[i] > b_min[i] for i in range(3))


def posicao_valida(item):
    bmin, bmax = item["bbox"]

    if (bmin[0] < -LIMITE_QUARTO or bmax[0] > LIMITE_QUARTO or
            bmin[2] < -LIMITE_QUARTO or bmax[2] > LIMITE_QUARTO):
        return False
    if bmin[1] < -0.01:
        return False

    for cmin, cmax in caixas:
        if sobrepoe(bmin, bmax, cmin, cmax):
            return False

    pmin = np.array([Camera_pos[0] - RAIO_JOGADOR, 0.0, Camera_pos[2] - RAIO_JOGADOR])
    pmax = np.array([Camera_pos[0] + RAIO_JOGADOR, ALTURA_OLHOS, Camera_pos[2] + RAIO_JOGADOR])
    if sobrepoe(bmin, bmax, pmin, pmax):
        return False

    return True

# ---------------- mira ----------------

def tamanho_janela():
    w, h = glfw.get_window_size(janela)
    return max(w, 1), max(h, 1)


def vetor_olhar():
    if modo_posicao:
        olho = np.array([foco[0], ALTURA_TOPO, foco[1]], dtype=np.float64)
        return olho, np.array([0.0, -1.0, 0.0])

    h = math.radians(camera_horizontal)
    v = math.radians(camera_vertical)
    frente = np.array([
        math.cos(h) * math.cos(v),
        math.sin(v),
        math.sin(h) * math.cos(v),
    ], dtype=np.float64)
    olho = np.array([Camera_pos[0], ALTURA_OLHOS, Camera_pos[2]], dtype=np.float64)
    return olho, frente


def vetor_cima():
    return np.array([0, 0, -1], dtype=np.float32) if modo_posicao else UP


def raio_mira():
    if not modo_posicao:
        return vetor_olhar()

    mx, my = glfw.get_cursor_pos(janela)
    w, h = tamanho_janela()
    aspecto = w / h
    ndc_x = 2 * mx / w - 1
    ndc_y = 1 - 2 * my / h
    x = foco[0] + ndc_x * ZOOM_TOPO * aspecto
    z = foco[1] - ndc_y * ZOOM_TOPO
    return np.array([x, ALTURA_TOPO, z]), np.array([0.0, -1.0, 0.0])


def alcance_atual():
    return 100.0 if modo_posicao else ALCANCE_INTERACAO


def calcular_alvo():
    origem, frente = raio_mira()
    if frente[1] > -0.05:
        return None
    t = -origem[1] / frente[1]
    if t > alcance_atual():
        return None
    p = origem + frente * t
    x = round(float(p[0]) / GRADE) * GRADE
    z = round(float(p[2]) / GRADE) * GRADE
    return x, z


def intersecta_caixa(origem, direcao, bmin, bmax, alcance):
    tmin, tmax = 0.0, alcance
    for i in range(3):
        o = float(origem[i])
        d = float(direcao[i])
        lo = float(bmin[i])
        hi = float(bmax[i])
        if abs(d) < 1e-9:
            if o < lo or o > hi:
                return None
            continue
        t1 = (lo - o) / d
        t2 = (hi - o) / d
        if t1 > t2:
            t1, t2 = t2, t1
        tmin = max(tmin, t1)
        tmax = min(tmax, t2)
        if tmin > tmax:
            return None
    return tmin


def atualizar_fantasma():
    global fantasma, fantasma_valido
    fantasma = None
    fantasma_valido = False
    if not modo_posicao or catalogo_aberto:
        return
    alvo = calcular_alvo()
    if alvo is None:
        return
    fantasma = construir_item(DISPONIVEIS[indice], alvo[0], alvo[1], rot_fantasma)
    fantasma_valido = posicao_valida(fantasma)

# ---------------- textos e retângulos da interface ----------------

def criar_buffers_ui():
    global ui_vao, ui_vbo
    ui_vao = glGenVertexArrays(1)
    ui_vbo = glGenBuffers(1)
    glBindVertexArray(ui_vao)
    glBindBuffer(GL_ARRAY_BUFFER, ui_vbo)
    glBufferData(GL_ARRAY_BUFFER, 6 * 4 * 4, None, GL_DYNAMIC_DRAW)
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 16, ctypes.c_void_p(0))
    glEnableVertexAttribArray(1)
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 16, ctypes.c_void_p(8))
    glBindVertexArray(0)


def fonte(tam):
    for nome in ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(nome, tam)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:
        return ImageFont.load_default()


_cache_texto = {}


def textura_texto(texto, tam):
    chave = (texto, tam)
    if chave in _cache_texto:
        return _cache_texto[chave]

    f = fonte(tam)
    bbox = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), texto, font=f)
    w = max(bbox[2] - bbox[0], 1) + 2
    h = max(bbox[3] - bbox[1], 1) + 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((1 - bbox[0], 1 - bbox[1]), texto, font=f, fill=(255, 255, 255, 255))
    dados = img.tobytes()

    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, dados)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

    _cache_texto[chave] = (tex, w, h)
    return _cache_texto[chave]


def desenhar_retangulo_ui(x, y, w, h, cor, textura=None):
    verts = np.array([
        x,     y,     0, 0,
        x + w, y,     1, 0,
        x + w, y + h, 1, 1,
        x,     y,     0, 0,
        x + w, y + h, 1, 1,
        x,     y + h, 0, 1,
    ], dtype=np.float32)

    glBindVertexArray(ui_vao)
    glBindBuffer(GL_ARRAY_BUFFER, ui_vbo)
    glBufferSubData(GL_ARRAY_BUFFER, 0, verts.nbytes, verts)

    glUniform4f(ui_loc["uCor"], *cor)
    if textura is not None:
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, textura)
        glUniform1i(ui_loc["uUsaTex"], 1)
    else:
        glUniform1i(ui_loc["uUsaTex"], 0)

    glDrawArrays(GL_TRIANGLES, 0, 6)


def desenhar_texto(texto, x, y, cor, tam=16):
    tex, w, h = textura_texto(texto, tam)
    desenhar_retangulo_ui(x, y, w, h, cor, tex)


def desenhar_texto_centro(texto, rect, cor, tam=16):
    rx, ry, rw, rh = rect
    tex, w, h = textura_texto(texto, tam)
    desenhar_retangulo_ui(rx + (rw - w) / 2, ry + (rh - h) / 2, w, h, cor, tex)


def ponto_em(rect, px, py):
    x, y, w, h = rect
    return x <= px <= x + w and y <= py <= y + h

# ---------------- catálogo ----------------

CATALOGO_X, CATALOGO_Y, CATALOGO_W = 40, 40, 660
CARD_H, CARD_GAP = 104, 12


def layout_catalogo():
    filtrados = nomes_filtrados()
    linhas = max(1, math.ceil(len(filtrados) / 2))
    x0, y0, w = CATALOGO_X, CATALOGO_Y, CATALOGO_W

    n_abas = len(CATEGORIAS)
    gap_aba = 4
    aba_w = (w - 24 - gap_aba * (n_abas - 1)) / n_abas
    abas = [(x0 + 12 + i * (aba_w + gap_aba), y0 + 56, aba_w, 36) for i in range(n_abas)]

    card_w = (w - 24 - 12) / 2
    cards = []
    for i, nome in enumerate(filtrados):
        col, row = i % 2, i // 2
        x = x0 + 12 + col * (card_w + 12)
        y = y0 + 104 + row * (CARD_H + CARD_GAP)
        cards.append((nome, (x, y, card_w, CARD_H)))

    altura = 104 + linhas * (CARD_H + CARD_GAP) + 4
    return {"painel": (x0, y0, w, altura), "abas": abas, "cards": cards}


def clicar_catalogo(px, py):
    global categoria_ativa, catalogo_aberto, indice

    lay = layout_catalogo()
    for i, r in enumerate(lay["abas"]):
        if ponto_em(r, px, py):
            categoria_ativa = i
            return

    for nome, r in lay["cards"]:
        if ponto_em(r, px, py):
            indice = DISPONIVEIS.index(nome)
            catalogo_aberto = False
            atualizar_titulo()
            print(f"Selecionado: {info_catalogo(nome)[0]}")
            return


def render_catalogo(prog_3d):
    mx, my = glfw.get_cursor_pos(janela)
    lay = layout_catalogo()

    glDisable(GL_DEPTH_TEST)
    glUseProgram(programa_ui)
    w, h = tamanho_janela()
    glUniform2f(ui_loc["uTela"], w, h)

    px, py, pw, ph = lay["painel"]
    desenhar_retangulo_ui(px, py, pw, ph, (0.08, 0.08, 0.11, 0.94))
    desenhar_texto("Catálogo de móveis", px + 16, py + 10, (1, 1, 1, 1), 22)
    desenhar_texto("Clique para escolher  ·  C ou ESC fecha", px + 16, py + 34, (0.6, 0.6, 0.66, 1), 14)

    for i, (nome_aba, r) in enumerate(zip(CATEGORIAS, lay["abas"])):
        ativa = i == categoria_ativa
        fundo = (0.85, 0.6, 0.2, 1) if ativa else (0.2, 0.22, 0.28, 1)
        txt = (0.1, 0.08, 0.05, 1) if ativa else (0.9, 0.9, 0.95, 1)
        desenhar_retangulo_ui(*r, fundo)
        desenhar_texto_centro(nome_aba, r, txt, 15)

    for nome, (x, y, cw, ch) in lay["cards"]:
        titulo, cat, cor, desc = info_catalogo(nome)
        selecionado = nome == DISPONIVEIS[indice]
        sobre = ponto_em((x, y, cw, ch), mx, my)

        if selecionado:
            desenhar_retangulo_ui(x - 3, y - 3, cw + 6, ch + 6, (0.85, 0.6, 0.2, 1))
        fundo = (0.22, 0.24, 0.3, 1) if sobre else (0.16, 0.17, 0.22, 1)
        desenhar_retangulo_ui(x, y, cw, ch, fundo)

        desenhar_retangulo_ui(x + 14, y + 22, 60, 60, (*cor, 1.0))
        desenhar_texto(titulo, x + 90, y + 14, (1, 1, 1, 1), 20)
        desenhar_texto(cat, x + 90, y + 42, (0.85, 0.7, 0.4, 1), 15)
        desenhar_texto(desc, x + 90, y + 66, (0.65, 0.65, 0.7, 1), 14)

    glUseProgram(prog_3d)
    glEnable(GL_DEPTH_TEST)


def nomes_do_catalogo_visiveis():
    return nomes_filtrados()

# ---------------- ações do modo de posicionamento ----------------

def atualizar_titulo():
    if modo_posicao:
        titulo = (f"Torre Magica | POSICIONAR: {info_catalogo(DISPONIVEIS[indice])[0]} ({rot_fantasma:.0f}°) | "
                  f"Clique: colocar  Dir.: remover  Q/E: trocar  C: catálogo  R: girar 90°  TAB: sair")
    else:
        titulo = "Torre Magica | TAB: modo de posicionamento"
    glfw.set_window_title(janela, titulo)


def tentar_colocar():
    if fantasma is None:
        return
    if not fantasma_valido:
        print("Posição inválida: fora do quarto, sobre outro móvel ou sobre você.")
        return
    itens.append(fantasma)
    reconstruir_mundo()
    print(f"Colocado: {fantasma['nome']}")


def tentar_remover():
    origem, frente = raio_mira()
    melhor_i = None
    melhor_t = alcance_atual()

    for i, item in enumerate(itens):
        if item["fixo"]:
            continue
        bmin, bmax = item["bbox"]
        t = intersecta_caixa(origem, frente, bmin, bmax, alcance_atual())
        if t is not None and t < melhor_t:
            melhor_i = i
            melhor_t = t

    if melhor_i is None:
        print("Nenhum móvel na mira.")
        return

    removido = itens.pop(melhor_i)
    reconstruir_mundo()
    print(f"Removido: {removido['nome']}")

# ---------------- colisão do jogador ----------------

def colide(pos):
    px, pz = pos[0], pos[2]
    for mn, mx in caixas:
        if mx[1] < 0.0 or mn[1] > ALTURA_OLHOS:
            continue
        if (px + RAIO_JOGADOR > mn[0] and px - RAIO_JOGADOR < mx[0] and
                pz + RAIO_JOGADOR > mn[2] and pz - RAIO_JOGADOR < mx[2]):
            return True
    return False


def mover_com_colisao(delta):
    global Camera_pos

    nova = Camera_pos.copy()
    nova[0] += delta[0]
    if not colide(nova):
        Camera_pos[0] = nova[0]

    nova = Camera_pos.copy()
    nova[2] += delta[2]
    if not colide(nova):
        Camera_pos[2] = nova[2]

# ---------------- controles ----------------

def mouse(window, xpos, ypos):
    global ultimoX, ultimoY
    global camera_vertical, camera_horizontal

    if modo_posicao:
        return

    if ultimoX is None:
        ultimoX = xpos
        ultimoY = ypos
        return

    dx = xpos - ultimoX
    dy = ultimoY - ypos

    ultimoX = xpos
    ultimoY = ypos

    camera_horizontal += dx * sensibilidade
    camera_vertical += dy * sensibilidade

    camera_vertical = max(-89, min(89, camera_vertical))


def tecla(window, key, scancode, action, mods):
    global modo_posicao, indice, rot_fantasma, ultimoX, catalogo_aberto

    if action != glfw.PRESS:
        return

    if key == glfw.KEY_TAB:
        modo_posicao = not modo_posicao
        catalogo_aberto = False
        ultimoX = None
        if modo_posicao:
            foco[:] = (Camera_pos[0], Camera_pos[2])
            glfw.set_input_mode(janela, glfw.CURSOR, glfw.CURSOR_NORMAL)
        else:
            glfw.set_input_mode(janela, glfw.CURSOR, glfw.CURSOR_DISABLED)
    elif modo_posicao:
        if key == glfw.KEY_C:
            catalogo_aberto = not catalogo_aberto
        elif key == glfw.KEY_ESCAPE and catalogo_aberto:
            catalogo_aberto = False
        elif key == glfw.KEY_E:
            indice = (indice + 1) % len(DISPONIVEIS)
        elif key == glfw.KEY_Q:
            indice = (indice - 1) % len(DISPONIVEIS)
        elif key == glfw.KEY_R:
            rot_fantasma = (rot_fantasma + 90) % 360
        elif key in (glfw.KEY_DELETE, glfw.KEY_BACKSPACE):
            tentar_remover()
        elif glfw.KEY_1 <= key <= glfw.KEY_9:
            n = key - glfw.KEY_1
            if n < len(DISPONIVEIS):
                indice = n

    atualizar_titulo()


def clique(window, button, action, mods):
    if action != glfw.PRESS or not modo_posicao:
        return

    if catalogo_aberto:
        if button == glfw.MOUSE_BUTTON_LEFT:
            px, py = glfw.get_cursor_pos(window)
            clicar_catalogo(px, py)
        return

    if button == glfw.MOUSE_BUTTON_LEFT:
        tentar_colocar()
    elif button == glfw.MOUSE_BUTTON_RIGHT:
        tentar_remover()


def rolagem(window, xoffset, yoffset):
    global rot_fantasma

    if modo_posicao and not catalogo_aberto:
        rot_fantasma = (rot_fantasma + yoffset * GRAUS_SCROLL) % 360
        atualizar_titulo()


def movimento(window, delta_time):
    if modo_posicao:
        d = VELOCIDADE_PAN * delta_time
        if glfw.get_key(window, glfw.KEY_W) == glfw.PRESS:
            foco[1] -= d
        if glfw.get_key(window, glfw.KEY_S) == glfw.PRESS:
            foco[1] += d
        if glfw.get_key(window, glfw.KEY_D) == glfw.PRESS:
            foco[0] += d
        if glfw.get_key(window, glfw.KEY_A) == glfw.PRESS:
            foco[0] -= d
        foco[:] = np.clip(foco, -LIMITE_QUARTO, LIMITE_QUARTO)
        return

    angulo = math.radians(camera_horizontal)

    FrenteX = math.cos(angulo)
    FrenteZ = math.sin(angulo)

    DireitaX = -FrenteZ
    DireitaZ = FrenteX

    d = velocidade * delta_time
    delta = np.zeros(3, dtype=np.float32)

    if glfw.get_key(window, glfw.KEY_W) == glfw.PRESS:
        delta[0] += FrenteX * d
        delta[2] += FrenteZ * d
    if glfw.get_key(window, glfw.KEY_S) == glfw.PRESS:
        delta[0] -= FrenteX * d
        delta[2] -= FrenteZ * d
    if glfw.get_key(window, glfw.KEY_D) == glfw.PRESS:
        delta[0] += DireitaX * d
        delta[2] += DireitaZ * d
    if glfw.get_key(window, glfw.KEY_A) == glfw.PRESS:
        delta[0] -= DireitaX * d
        delta[2] -= DireitaZ * d

    mover_com_colisao(delta)

# ---------------- render ----------------

def enviar_luzes(loc):
    n = min(len(luzes_ativas), MAX_LUZES)
    glUniform1i(loc["uNumLuzes"], n)
    if n == 0:
        return
    pos = np.ascontiguousarray([l["pos"] for l in luzes_ativas[:n]], dtype=np.float32)
    cor = np.ascontiguousarray([l["cor"] for l in luzes_ativas[:n]], dtype=np.float32)
    raio = np.ascontiguousarray([l["raio"] for l in luzes_ativas[:n]], dtype=np.float32)
    glUniform3fv(loc["uLuzPos"], n, pos)
    glUniform3fv(loc["uLuzCor"], n, cor)
    glUniform1fv(loc["uLuzRaio"], n, raio)


def desenhar_lista(lista, loc):
    for malha, cor, m, normal, emissivo in lista:
        glUniformMatrix4fv(loc["uModel"], 1, GL_TRUE, m)
        glUniformMatrix3fv(loc["uNormalMatrix"], 1, GL_TRUE, normal)
        glUniform3f(loc["uCor"], *cor)
        glUniform1f(loc["uEmissivo"], emissivo)
        malha.desenhar()


def render(loc):
    olho, frente = vetor_olhar()
    view = look_at(olho.astype(np.float32),
                   (olho + frente).astype(np.float32),
                   vetor_cima())

    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glUniformMatrix4fv(loc["uProjection"], 1, GL_TRUE, projecao_atual())
    glUniformMatrix4fv(loc["uView"], 1, GL_TRUE, view)
    enviar_luzes(loc)

    glUniform1f(loc["uFantasma"], 0.0)
    desenhar_lista(cena_topo if modo_posicao else cena, loc)

    if modo_posicao:
        m = matriz_modelo((Camera_pos[0], 0.05, Camera_pos[2]), (0.6, 0.1, 0.6)).astype(np.float32)
        normal = np.linalg.inv(m[:3, :3]).T.astype(np.float32)
        desenhar_lista([(MALHAS["cilindro"], (0.9, 0.85, 0.3), m, normal, 1.0)], loc)

    if fantasma is not None:
        verde = (0.2, 1.0, 0.3)
        vermelho = (1.0, 0.2, 0.2)
        glUniform3f(loc["uTom"], *(verde if fantasma_valido else vermelho))
        glUniform1f(loc["uFantasma"], 1.0)
        glDepthMask(GL_FALSE)
        desenhar_lista(fantasma["draw"], loc)
        glDepthMask(GL_TRUE)
        glUniform1f(loc["uFantasma"], 0.0)

    if modo_posicao and catalogo_aberto:
        render_catalogo(programa_3d)


def main():
    global janela, programa_3d, programa_ui

    if not glfw.init():
        return

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, glfw.TRUE)

    janela = glfw.create_window(LARGURA, ALTURA, "Torre Magica", None, None)
    if not janela:
        glfw.terminate()
        return

    glfw.make_context_current(janela)

    glEnable(GL_DEPTH_TEST)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glClearColor(0.15, 0.15, 0.20, 1.0)

    programa_3d = compileProgram(
        compileShader(VERTEX_SHADER, GL_VERTEX_SHADER),
        compileShader(FRAGMENT_SHADER, GL_FRAGMENT_SHADER),
    )
    glUseProgram(programa_3d)

    loc = {nome: glGetUniformLocation(programa_3d, nome) for nome in
           ["uModel", "uView", "uProjection", "uNormalMatrix",
            "uCor", "uDirLuz", "uEmissivo", "uFantasma", "uTom", "uNumLuzes"]}
    for nome in ["uLuzPos", "uLuzCor", "uLuzRaio"]:
        loc[nome] = glGetUniformLocation(programa_3d, nome + "[0]")

    luz_dir = np.array([0.4, 1.0, 0.3], dtype=np.float32)
    luz_dir /= np.linalg.norm(luz_dir)
    glUniform3f(loc["uDirLuz"], *luz_dir)

    programa_ui = compileProgram(
        compileShader(UI_VERTEX, GL_VERTEX_SHADER),
        compileShader(UI_FRAGMENT, GL_FRAGMENT_SHADER),
    )
    global ui_loc
    ui_loc = {nome: glGetUniformLocation(programa_ui, nome) for nome in
              ["uTela", "uCor", "uTex", "uUsaTex"]}
    glUseProgram(programa_ui)
    glUniform1i(ui_loc["uTex"], 0)
    glUseProgram(programa_3d)
    criar_buffers_ui()

    MALHAS.update({
        "cubo": Malha(dados_cubo()),
        "piso": Malha(dados_piso()),
        "cilindro": Malha(dados_cilindro()),
        "esfera": Malha(dados_esfera()),
    })

    construir_cena()

    glfw.set_input_mode(janela, glfw.CURSOR, glfw.CURSOR_DISABLED)
    glfw.set_cursor_pos_callback(janela, mouse)
    glfw.set_key_callback(janela, tecla)
    glfw.set_mouse_button_callback(janela, clique)
    glfw.set_scroll_callback(janela, rolagem)

    atualizar_titulo()

    ultimo_tempo = glfw.get_time()

    while not glfw.window_should_close(janela):
        glfw.poll_events()

        tempo_atual = glfw.get_time()
        delta_time = tempo_atual - ultimo_tempo
        ultimo_tempo = tempo_atual

        movimento(janela, delta_time)
        atualizar_fantasma()
        render(loc)

        glfw.swap_buffers(janela)

    glfw.terminate()


if __name__ == '__main__':
    main()