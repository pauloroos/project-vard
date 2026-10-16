"""WER do whisper do OpenJarvis no WAV da reunião (meta < 15 %). Só roda com o OpenJarvis no ar."""
import httpx
import pytest

import preflight

jiwer = pytest.importorskip("jiwer")


def _openjarvis_no_ar() -> bool:
    try:
        return httpx.get(f"{preflight.OPENJARVIS}/health", timeout=3, trust_env=False).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.pc_real


def test_wer_do_wav_da_reuniao_abaixo_de_15_por_cento():
    if not preflight.WAV_REUNIAO.exists() or not _openjarvis_no_ar():
        pytest.skip("prova real exige WAV controlado e OpenJarvis")
    texto, _ = preflight.transcrever_wav_reuniao()
    ref = preflight.normalizar_para_wer(preflight.TXT_REUNIAO.read_text(encoding="utf-8"))
    hip = preflight.normalizar_para_wer(texto)
    wer = jiwer.wer(ref, hip)
    print(f"\nWER = {wer:.3f} | ref: {ref} | hip: {hip}")
    assert wer < 0.15
