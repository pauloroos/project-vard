"""Testes da detecção local do primeiro uso (T1, 0.9).

Cobrem: PATH com espaços, caminho manual/configurado, LM Studio instalado e fechado,
`lms` ausente, os quatro CLIs e o Orca presentes/ausentes, executável quebrado, timeout,
GPU NVIDIA/AMD/Intel/CPU com VRAM desconhecida e a garantia de que nenhuma sonda faz login,
executa tarefa ou carrega modelo. Nenhum subprocesso real é disparado: o `Ambiente` é falso.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from vard.primeiro_uso import deteccao

#: Referência à função real, capturada antes de qualquer monkeypatch (os testes de rota trocam
#: `deteccao.detectar`; sem isto a troca chamaria a si mesma).
_DETECTAR = deteccao.detectar


# --- Ambiente falso -------------------------------------------------------------

def _norm(caminho) -> str:
    return str(Path(caminho)).replace("/", "\\").rstrip("\\").lower()


class FakeAmbiente:
    """Ambiente de detecção sem tocar no PC: which/existe/rodar/http registrados."""

    def __init__(
        self,
        *,
        env: dict[str, str] | None = None,
        no_path: dict[str, str] | None = None,
        existentes: list[str] | None = None,
        versoes: dict[str, tuple[int, str, str]] | None = None,
        gpu_json: str | None = None,
        nvidia_smi: str | None = None,
        lento: set[str] | None = None,
        http: dict[str, object] | None = None,
    ) -> None:
        self.env = {
            "LOCALAPPDATA": r"X:\\Fake\\LocalAppData",
            "APPDATA": r"X:\\Fake\\Roaming",
            "PROGRAMFILES": r"X:\\Fake\\Programs",
            "USERPROFILE": r"X:\\Fake\\User",
            **(env or {}),
        }
        self.no_path = {k: str(v) for k, v in (no_path or {}).items()}
        self.existentes = {_norm(c) for c in (existentes or [])}
        self.versoes = {k.lower(): v for k, v in (versoes or {}).items()}
        self.gpu_json = gpu_json
        self.nvidia_smi = nvidia_smi
        self.lento = {x.lower() for x in (lento or set())}
        self.http = dict(http or {})
        self.chamadas: list[list[str]] = []
        self.http_chamadas: list[str] = []

    def which(self, nome: str) -> str | None:
        return self.no_path.get(nome)

    def existe(self, caminho: Path) -> bool:
        return _norm(caminho) in self.existentes

    def rodar(self, args, timeout: float):
        self.chamadas.append([str(a) for a in args])
        nome = Path(str(args[0])).name.lower()
        if nome.startswith("powershell"):
            if self.gpu_json is None:
                return (1, "", "sem gpu")
            return (0, self.gpu_json, "")
        if nome.startswith("nvidia-smi"):
            if self.nvidia_smi is None:
                return (1, "", "sem nvidia-smi")
            return (0, self.nvidia_smi, "")
        chave = _norm(args[0])
        if chave in self.lento or nome in self.lento:
            raise subprocess.TimeoutExpired(list(args), timeout)
        return self.versoes.get(chave, (0, "", ""))

    def http_json(self, url: str, timeout: float):
        self.http_chamadas.append(url)
        return self.http.get(url)

    def como_ambiente(self) -> deteccao.Ambiente:
        return deteccao.Ambiente(
            env=self.env, which=self.which, existe=self.existe,
            rodar=self.rodar, http_json=self.http_json,
        )


def _item(resultado, id_: str) -> deteccao.Item:
    return next(i for i in resultado.itens if i.id == id_)


@pytest.fixture
def fake() -> FakeAmbiente:
    return FakeAmbiente()


# --- Resolução de caminhos ------------------------------------------------------

def test_encontra_cli_no_path_com_espacos():
    caminho = r"X:\Program Files\Ferramenta Nova\claude.exe"
    amb = FakeAmbiente(no_path={"claude": caminho}, existentes=[caminho],
                       versoes={caminho: (0, "1.2.3\n", "")})
    r = deteccao.detectar(amb.como_ambiente())
    claude = _item(r, "claude")
    assert claude.estado == "encontrado" and claude.versao == "1.2.3"
    # o caminho com espaços vai como UM argumento; nunca vira linha de shell
    probe = next(c for c in amb.chamadas if Path(c[0]).name.lower() == "claude.exe")
    assert probe[0] == caminho and probe[1] == "--version"


def test_caminho_manual_informado_vence():
    caminho = r"X:\Ferramentas\claude.exe"
    amb = FakeAmbiente(existentes=[caminho], versoes={caminho: (0, "9.9", "")})
    r = deteccao.detectar(amb.como_ambiente(), caminhos={"claude": caminho})
    claude = _item(r, "claude")
    assert claude.estado == "encontrado" and claude.versao == "9.9"


def test_caminho_manual_inexistente_cai_para_o_path():
    real = r"X:\bin\claude.exe"
    amb = FakeAmbiente(no_path={"claude": real}, existentes=[real],
                       versoes={real: (0, "2.0", "")})
    r = deteccao.detectar(amb.como_ambiente(), caminhos={"claude": r"X:\nao-existe\claude.exe"})
    assert _item(r, "claude").estado == "encontrado"


def test_executavel_quebrado_e_encontrado_sem_versao():
    caminho = r"X:\bin\codex.exe"
    amb = FakeAmbiente(no_path={"codex": caminho}, existentes=[caminho],
                       versoes={caminho: (1, "", "nao executa")})
    codex = _item(deteccao.detectar(amb.como_ambiente()), "codex")
    assert codex.estado == "encontrado"
    assert codex.versao == ""
    assert "verificada" in codex.detalhe


def test_sonda_de_versao_que_estoura_vira_sem_versao():
    caminho = r"X:\bin\opencode.exe"
    amb = FakeAmbiente(no_path={"opencode": caminho}, existentes=[caminho], lento={caminho})
    opencode = _item(deteccao.detectar(amb.como_ambiente()), "opencode")
    assert opencode.estado == "encontrado" and opencode.versao == ""


# --- LM Studio, CLIs e Orca -----------------------------------------------------

def test_lmstudio_instalado_e_fechado_e_lms_ausente():
    exe = r"X:\Fake\LocalAppData\Programs\LM Studio\LM Studio.exe"
    amb = FakeAmbiente(existentes=[exe])
    r = deteccao.detectar(amb.como_ambiente())
    lm = _item(r, "lmstudio")
    assert lm.estado == "encontrado"
    assert "fechado" in lm.detalhe.lower()
    assert _item(r, "lms").estado == "nao_encontrado"


def test_lmstudio_servidor_acessivel_mesmo_sem_exe():
    amb = FakeAmbiente(http={"http://127.0.0.1:1234/v1/models": {"data": []}})
    lm = _item(deteccao.detectar(amb.como_ambiente()), "lmstudio")
    assert lm.estado == "encontrado"
    assert "acess" in lm.detalhe.lower()


def test_lms_encontrado_no_caminho_conhecido():
    exe = r"X:\Fake\User\.lmstudio\bin\lms.exe"
    amb = FakeAmbiente(existentes=[exe], versoes={exe: (0, "0.3.5", "")})
    lms = _item(deteccao.detectar(amb.como_ambiente()), "lms")
    assert lms.estado == "encontrado" and lms.versao == "0.3.5"


def test_quatro_clis_e_orca_presentes():
    exes = {n: rf"X:\bin\{n}.exe" for n in ("claude", "codex", "opencode", "agy")}
    exes["orca"] = r"X:\Fake\LocalAppData\Programs\orca\resources\bin\orca.exe"
    amb = FakeAmbiente(no_path={n: p for n, p in exes.items() if n != "orca"},
                       existentes=list(exes.values()),
                       versoes={p: (0, "1.0", "") for n, p in exes.items() if n != "orca"})
    r = deteccao.detectar(amb.como_ambiente())
    for n in exes:
        assert _item(r, n).estado == "encontrado", n


def test_quatro_clis_e_orca_ausentes():
    r = deteccao.detectar(FakeAmbiente().como_ambiente())
    for n in ("claude", "codex", "opencode", "agy", "orca", "lmstudio", "lms"):
        assert _item(r, n).estado == "nao_encontrado", n


def test_orca_no_caminho_do_adaptador_sem_versao():
    exe = r"X:\Fake\LocalAppData\Programs\orca\resources\bin\orca.exe"
    amb = FakeAmbiente(existentes=[exe])
    orca = _item(deteccao.detectar(amb.como_ambiente()), "orca")
    assert orca.estado == "encontrado"


# --- GPU ------------------------------------------------------------------------

@pytest.mark.parametrize(
    "nome,esperado",
    [
        ("NVIDIA GeForce RTX 4090", "nvidia"),
        ("AMD Radeon RX 7900 XTX", "amd"),
        ("Intel(R) UHD Graphics 630", "intel"),
        ("Microsoft Basic Display Adapter", "cpu"),
    ],
)
def test_gpu_backend(nome, esperado):
    amb = FakeAmbiente(gpu_json=json.dumps([{"Name": nome, "AdapterRAM": 0}]))
    gpu = deteccao.detectar(amb.como_ambiente()).gpu
    assert gpu.backend == esperado
    if esperado == "cpu":
        assert gpu.estado == "nao_encontrado"
    else:
        assert gpu.estado == "encontrado"


def test_gpu_nvidia_com_vram_do_nvidia_smi():
    amb = FakeAmbiente(
        gpu_json=json.dumps([{"Name": "NVIDIA GeForce RTX 4090", "AdapterRAM": 0}]),
        no_path={"nvidia-smi": r"X:\Windows\System32\nvidia-smi.exe"},
        existentes=[r"X:\Windows\System32\nvidia-smi.exe"],
        nvidia_smi="24564\n",
    )
    gpu = deteccao.detectar(amb.como_ambiente()).gpu
    assert gpu.backend == "nvidia" and gpu.vram_mb == 24564


def test_gpu_vram_desconhecida():
    amb = FakeAmbiente(gpu_json=json.dumps([{"Name": "NVIDIA GeForce GTX 1650", "AdapterRAM": 0}]))
    gpu = deteccao.detectar(amb.como_ambiente()).gpu
    assert gpu.estado == "encontrado" and gpu.vram_mb is None


def test_gpu_indisponivel_vira_nao_verificado():
    gpu = deteccao.detectar(FakeAmbiente().como_ambiente()).gpu
    assert gpu.estado == "nao_verificado"


# --- Garantia de somente-leitura -----------------------------------------------

def test_nenhuma_sonda_faz_login_tarefa_ou_carga_de_modelo():
    exes = [rf"X:\bin\{n}.exe" for n in ("claude", "codex", "opencode", "agy", "lms")]
    amb = FakeAmbiente(
        no_path={n: rf"X:\bin\{n}.exe" for n in ("claude", "codex", "opencode", "agy", "lms")},
        existentes=exes,
        versoes={p: (0, "1.0", "") for p in exes},
        gpu_json=json.dumps([{"Name": "NVIDIA GeForce RTX 4090", "AdapterRAM": 0}]),
        http={"http://127.0.0.1:1234/v1/models": {"data": []}},
    )
    deteccao.detectar(amb.como_ambiente())
    proibidos = ("--login", " login", "exec", " run", "load", "chat/completions",
                 "server start", "--prompt", "-p ", "send", "message")
    for chamada in amb.chamadas:
        exe = Path(chamada[0]).name.lower()
        if exe in ("powershell", "nvidia-smi"):
            continue
        resto = " ".join(chamada[1:]).lower()
        assert not any(p in f" {resto}" for p in proibidos), chamada
    # a única requisição de rede é a leitura de modelos do servidor local
    assert all(u.endswith("/v1/models") for u in amb.http_chamadas)


def test_prazo_total_respeitado():
    # Sem prazo, nada de sonda: os itens achados ficam sem versão, mas a resposta é rápida.
    caminho = r"X:\bin\claude.exe"
    amb = FakeAmbiente(no_path={"claude": caminho}, existentes=[caminho])
    r = deteccao.detectar(amb.como_ambiente(), prazo_s=0.0)
    assert r.duracao_ms < 1000
    assert _item(r, "claude").estado == "encontrado"


# --- Contrato -------------------------------------------------------------------

def test_como_dict_respeita_contrato_e_nao_vaza_caminho():
    caminho = r"X:\bin\claude.exe"
    amb = FakeAmbiente(no_path={"claude": caminho}, existentes=[caminho],
                       versoes={caminho: (0, "1.0", "")})
    d = deteccao.detectar(amb.como_ambiente()).como_dict()
    assert set(d) == {"itens", "gpu"}
    assert set(d["gpu"]) == {"estado", "backend", "vram_mb"}
    for item in d["itens"]:
        assert set(item) == {"id", "estado", "versao", "detalhe"}
        assert "caminho" not in json.dumps(item).lower().replace("caminho-pessoal", "")
    texto = json.dumps(d)
    assert "X:" not in texto and "claude.exe" not in texto


def test_ids_estaveis():
    assert deteccao.IDS == ("lmstudio", "lms", "orca", "claude", "codex", "opencode", "agy")


# --- Diagnóstico -----------------------------------------------------------------

def test_diagnostico_inclui_deteccao_com_ausentes_como_aviso():
    from vard import diagnostico

    r = deteccao.detectar(FakeAmbiente().como_ambiente())
    checks = diagnostico.checagens_deteccao(r)
    assert checks
    assert all(c.estado in ("ok", "aviso") for c in checks)
    assert all(c.grupo == "Primeiro uso" for c in checks)


def test_rodar_diagnostico_nao_inclui_deteccao_por_padrao(monkeypatch):
    from vard import diagnostico

    # troca as checagens reais por uma falsa: nada de subprocesso no teste
    monkeypatch.setattr(diagnostico, "CHECAGENS_BASICAS", [("Teste", "Falso", lambda: ("ok", "ok"))])
    monkeypatch.setattr(diagnostico.deteccao, "detectar",
                        lambda *a, **k: pytest.fail("não deveria detectar no básico padrão"))
    resultado = diagnostico.rodar_diagnostico("basico", prazo_s=20.0)
    assert resultado.checagens
    assert all(c.grupo == "Teste" for c in resultado.checagens)


def test_rodar_diagnostico_tipo_deteccao(monkeypatch):
    from vard import diagnostico

    monkeypatch.setattr(diagnostico.deteccao, "detectar",
                        lambda *a, **k: _DETECTAR(FakeAmbiente().como_ambiente()))
    resultado = diagnostico.rodar_diagnostico("deteccao", prazo_s=20.0)
    assert resultado.checagens
    assert all(c.grupo == "Primeiro uso" for c in resultado.checagens)


# --- Rota HTTP ------------------------------------------------------------------

def test_rota_deteccao_devolve_contrato(monkeypatch):
    import server
    from fastapi.testclient import TestClient

    monkeypatch.setattr(deteccao, "detectar",
                        lambda *a, **k: _DETECTAR(FakeAmbiente().como_ambiente()))
    cliente = TestClient(server.app, base_url="http://127.0.0.1:4700")
    r = cliente.get("/primeiro-uso/deteccao")
    assert r.status_code == 200
    corpo = r.json()
    assert set(corpo) == {"itens", "gpu"}
    assert {i["id"] for i in corpo["itens"]} == set(deteccao.IDS)


def test_rota_deteccao_aceita_caminho_manual(monkeypatch):
    import server
    from fastapi.testclient import TestClient

    visto = {}

    def fake_detectar(*a, **k):
        visto.update(k)
        return _DETECTAR(FakeAmbiente().como_ambiente())

    monkeypatch.setattr(deteccao, "detectar", fake_detectar)
    cliente = TestClient(server.app, base_url="http://127.0.0.1:4700")
    assert cliente.get("/primeiro-uso/deteccao", params={"item": "claude",
                                                         "caminho": r"X:\bin\claude.exe"}).status_code == 200
    assert visto.get("caminhos", {}).get("claude") == r"X:\bin\claude.exe"
