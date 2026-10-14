"""Prova do modo reunião de ponta a ponta. Com o serviço 4720 no ar (vard-modo sobe) e o OpenJarvis no ar:

    uv run python scripts/provas/prova-reuniao.py [--ata] [--ponte]

1. R1: o 4720 responde e recusa Host externo e Origin.
2. R2: abre uma reunião de teste, toca tests/preflight-reuniao.wav na saída padrão (só áudio; nada de teclado nem
   mouse), mede o tempo da 1ª fala depois do fim do áudio e confere a trilha "outros" contra o texto do WAV.
3. R3: latência de um segmento de ~8 s direto no whisper do OpenJarvis.
4. --ata: gera a ata da transcrição da própria prova (curta, então 1 bloco só) no Gemma local e confere que o PDF
   existe e que o Resumo está presente (uma fala de ~8 s não tem decisões nem pendências, então as outras seções não
   são exigidas); imprime o tamanho e se a pasta tmp sumiu. A pasta de teste é apagada ao fim.
5. --ponte: no passo 2, em vez de chamar o 4720, pede pela Vard (POST 4700/ask "Vard, acompanha a reunião" e
   "Vard, encerra a reunião"). Só funciona depois de a ponte e o OpenJarvis recarregarem com o código da reunião;
   antes disso o /ask não acha a ferramenta e a prova falha neste passo.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]   # raiz do repositório
sys.path.insert(0, str(RAIZ / "nucleo"))     # pacote vard (e preflight), para rodar fora do venv do uv

import preflight  # noqa: E402
from vard import reuniao as reuniao_mod  # noqa: E402


def virgula(x: float, casas: int = 1) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


def passo(nome: str, resultado: preflight.Check) -> bool:
    ok, detalhe = resultado
    aviso = ok and "AVISO" in detalhe
    print(f"{'!' if aviso else ('OK ' if ok else 'FALHOU')} {nome}: {detalhe}")
    return ok


def pedir(texto: str) -> str:
    r = httpx.post(f"{preflight.PONTE}/ask", json={"texto": texto}, timeout=120, trust_env=False)
    return str(r.json().get("resposta", ""))


def loopback_pela_ponte(esperar_s: float = 15) -> dict:
    """Mesma prova do loopback, mas o início e o fim vêm da Vard (ponte -> OpenJarvis -> ferramenta MCP).
    O `finally` encerra a reunião pela ponte (`POST /reuniao/encerrar`) se ela ficou ativa; o nome da pasta fica em
    `preflight.LOOPBACK["pasta"]` para o `main` apagá-la mesmo com exceção."""
    if preflight._reuniao_no_ar() is None:
        return {"aviso": preflight.AVISO_SEM_REUNIAO}
    saida: dict = {}
    preflight.LOOPBACK["pasta"] = None
    erro: Exception | None = None
    interrompido = True
    resultado = "ok"
    try:
        print("Vard:", pedir("Vard, acompanha a reunião")[:120])
        st = preflight._reuniao_no_ar() or {}
        if not st.get("ativa"):
            raise RuntimeError("a Vard não iniciou a reunião (a ponte/OpenJarvis já recarregaram com a reunião?)")
        saida["pasta"] = preflight.LOOPBACK["pasta"] = st.get("pasta")
        time.sleep(1.0)
        ini = time.monotonic()
        preflight._tocar_wav(preflight.WAV_REUNIAO).wait(timeout=60)
        saida["tocou_s"] = time.monotonic() - ini
        fim_audio = time.monotonic()
        while time.monotonic() - fim_audio < esperar_s:
            if int((preflight._reuniao_no_ar() or {}).get("falas", 0)) >= 1:
                saida["primeira_fala_s"] = time.monotonic() - fim_audio
                break
            time.sleep(0.25)
        print("Vard:", pedir("Vard, encerra a reunião")[:120])
        interrompido = False
    except Exception as exc:  # noqa: BLE001
        erro, interrompido = exc, False
    finally:
        atual = preflight._reuniao_no_ar()
        if atual is None or atual.get("ativa"):                      # ativa ou status desconhecido: encerra pela ponte
            if atual and not preflight.LOOPBACK["pasta"]:
                preflight.LOOPBACK["pasta"] = saida["pasta"] = atual.get("pasta")
            resultado, _ = preflight.encerrar_reuniao_de_teste(f"{preflight.PONTE}/reuniao/encerrar")
        if resultado == "salvar":
            SALVAR_FALHOU.append(True)
        if resultado != "ok" and interrompido:
            print("AVISO: " + (preflight.MSG_ATIVA if resultado == "ativa" else preflight.MSG_SALVAR))
        if saida.get("pasta"):
            try:
                pasta = reuniao_mod.caminho_pasta(saida["pasta"])
                saida["falas"] = reuniao_mod.carregar_falas(pasta)
                saida["caminho"] = pasta
            except Exception:  # noqa: BLE001
                saida.setdefault("falas", [])
    if resultado != "ok":
        msg = preflight.MSG_ATIVA if resultado == "ativa" else preflight.MSG_SALVAR
        raise RuntimeError(f"{erro}; {msg}" if erro else msg) from erro
    if erro:
        raise erro
    return saida


SALVAR_FALHOU: list[bool] = []


def apagar_pasta_de_teste() -> None:
    """Apaga a pasta da reunião de teste só quando o 4720 confirma `ativa: false` e o encerramento salvou.
    Status desconhecido, reunião ativa ou "salvar" falhou: deixa a pasta e avisa."""
    nome = preflight.LOOPBACK.get("pasta")
    if not nome:
        return
    st = preflight._reuniao_no_ar()
    if st is None or st.get("ativa") or SALVAR_FALHOU or preflight.LOOPBACK.get("salvar_falhou"):
        print(f"AVISO: pasta de teste {nome} mantida (status do 4720 desconhecido, reunião ativa ou encerramento sem salvar)")
        return
    try:
        shutil.rmtree(reuniao_mod.caminho_pasta(nome), ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass
    preflight.LOOPBACK["pasta"] = None


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        fluxo.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ata", action="store_true", help="gera a ata da transcrição da própria prova")
    ap.add_argument("--ponte", action="store_true", help="pede pela Vard (POST /ask) em vez de chamar o 4720")
    a = ap.parse_args()
    falhou = False

    falhou |= not passo("R1 serviço 4720", preflight.reuniao_servico_no_ar())

    pasta: Path | None = None
    try:
        saida = loopback_pela_ponte() if a.ponte else preflight.executar_loopback(apagar=False)
        pasta = saida.get("caminho")
        if "aviso" in saida:
            print("!", "R2 loopback:", saida["aviso"])
        else:
            ok, detalhe = preflight.avaliar_transcricao_reuniao(saida["falas"], preflight.TXT_REUNIAO.read_text(encoding="utf-8"))
            if "primeira_fala_s" in saida:
                detalhe += f"; áudio {virgula(saida['tocou_s'])} s; 1ª fala {virgula(saida['primeira_fala_s'], 2)} s depois do fim"
            else:
                ok, detalhe = False, "nenhuma fala em 15 s; " + detalhe
            falhou |= not passo("R2 loopback -> whisper", (ok, detalhe))
            if a.ata and ok and pasta:
                ini = time.monotonic()
                md = reuniao_mod.gerar_ata(pasta, "ata")
                seg = time.monotonic() - ini
                texto = md.read_text(encoding="utf-8")
                pdf = (pasta / "ata.pdf").read_bytes()
                print(f"  ata da própria prova: {virgula(seg)} s, {len(texto)} caracteres, PDF {len(pdf) // 1000} kB, "
                      f"tmp {'sobrou' if (pasta / 'tmp').exists() else 'apagada'}")
                print("  " + (texto.split("## Resumo", 1)[-1].strip().splitlines() or [""])[0][:140])
                # Transcrição de ~8 s não tem decisões nem pendências: confere só o essencial (PDF e Resumo).
                falhou |= not passo("ata", (pdf.startswith(b"%PDF") and "## Resumo" in texto, "PDF e Resumo presentes"))
    except Exception as exc:  # noqa: BLE001
        falhou = True
        print(f"FALHOU R2 loopback: {type(exc).__name__}: {exc}"[:200])
    finally:
        apagar_pasta_de_teste()

    try:
        texto, seg = preflight.transcrever_wav_reuniao()
        falhou |= not passo("R3 latência", preflight.avaliar_latencia_reuniao(texto, seg))
    except Exception as exc:  # noqa: BLE001
        falhou = True
        print(f"FALHOU R3 latência: {type(exc).__name__}: {exc}"[:200])
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
