"""Sessão de reunião: captura -> VAD por trilha -> fila de transcrição -> disco. Uma por vez."""
from __future__ import annotations

import datetime as dt
import logging
import os
import shutil
import threading
from pathlib import Path

import httpx
import numpy as np

from . import armazenamento as arm
from .armazenamento import Fala, Gravador, Reuniao, Transcricao, mmss, nome_pasta
from .config import Conf
from .texto import e_encerramento, eco
from .transcricao import Fila, limpar
from .vad import Segmentador

log = logging.getLogger("vard_reuniao.sessao")
TAXA = 16000
LACUNA_MIN_S = 0.05            # abaixo disso é jitter de relógio, não silêncio sem quadros
LACUNA_MAX_S = 3600.0          # trava de segurança: no máximo 1 h de zeros por lacuna


def ponte_url() -> str:
    return os.environ.get("VARD_PONTE", "http://127.0.0.1:4700").rstrip("/")


def publicar_na_ponte(ev: dict) -> None:
    """POST na ponte; nunca levanta (a ponte pode estar fora do ar ou ainda não aceitar o tipo)."""
    try:
        r = httpx.post(f"{ponte_url()}/events/publicar", json=ev, timeout=3, trust_env=False)
        if r.status_code >= 400:
            log.warning("ponte recusou o evento %s: HTTP %s", ev.get("estado"), r.status_code)
        else:
            log.info("evento %s publicado", ev.get("estado"))
    except httpx.HTTPError as e:
        log.warning("ponte fora do ar: %s", str(e)[:80])


class _CapturaReal:
    """Captura WASAPI de produção: abre um PyAudio novo (a lista de dispositivos é lida na criação)."""

    def __init__(self, ao_bloco):
        import pyaudiowpatch

        from .audio import Captura, dispositivos_padrao

        self.pa = pyaudiowpatch.PyAudio()
        self.dispositivos = dispositivos_padrao(self.pa)
        self._cap = Captura(self.pa, self.dispositivos, ao_bloco)
        self._fechada = False

    def abrir(self) -> None:
        self._cap.abrir()

    def fechar(self) -> None:
        if getattr(self, "_fechada", False):
            return
        self._fechada = True
        try:
            self._cap.fechar()
        finally:
            self.pa.terminate()


class Sessao:
    def __init__(self, conf: Conf, *, raiz: Path = arm.RAIZ, transcritor=None, prob=None, captura_factory=None,
                 publicar=None, agora=None, diarizar=None, diarizacao_estado=None):
        self.conf, self.raiz = conf, Path(raiz)
        self.transcritor = transcritor          # callable seg -> (texto, confianca); None = OpenJarvis
        self._prob = prob
        self._par_probs = None
        self.captura_factory = captura_factory or _CapturaReal
        self.publicar = publicar or publicar_na_ponte
        self.agora = agora or dt.datetime.now
        self.diarizar_fn = diarizar              # callable pasta -> dict; None = diarizacao.diarizar_pasta
        self._dia_estado = diarizacao_estado     # callable -> dict; None = diarizacao.estado
        self._trava_dia = threading.Lock()
        self.diarizando = False
        self._trava_estado = threading.RLock()
        self._trava_t = threading.Lock()
        self._ativa = False
        self._encerrando = False
        self._reset_estado()

    def _reset_estado(self) -> None:
        self.pasta: Path | None = None
        self.reuniao: Reuniao | None = None
        self.transcricao: Transcricao | None = None
        self.gravador: Gravador | None = None
        self.segmentadores: dict[str, Segmentador] = {}
        self.fila: Fila | None = None
        self.captura = None
        self._inicio: dt.datetime | None = None
        self._t_inicio: float | None = None
        self._t_ultimo = 0.0            # t relativo do último bloco recebido
        self._falas = 0
        self._nao_transcritos = 0
        self._ids: tuple = ()

    # ---------- ciclo de vida ----------
    def _transcrever(self, seg):
        if self.transcritor is None:
            from .transcricao import Transcritor
            t = Transcritor()
            self.transcritor = lambda s: t.transcrever(s.pcm)
        return self.transcritor(seg)

    def _probs(self):
        """Um prob por trilha (modelo com estado). Cache entre reuniões; reset ao reaproveitar."""
        if self._prob is not None:
            return self._prob, self._prob
        if self._par_probs is None:
            from .vad import carregar_silero
            self._par_probs = (carregar_silero(), carregar_silero())
        for p in self._par_probs:
            if hasattr(p, "reset"):
                p.reset()
        return self._par_probs

    def precarregar(self) -> None:
        """Carrega o silero (CPU) antes da primeira reunião."""
        self._probs()

    def _segmentador(self, trilha: str, prob) -> Segmentador:
        c = self.conf
        return Segmentador(trilha, prob, limiar=c.vad_limiar, min_silencio_ms=c.min_silencio_ms,
                           min_fala_ms=c.min_fala_ms, max_fala_s=c.max_fala_s)

    def iniciar(self) -> dict:
        with self._trava_estado:
            if self._ativa:
                return {"ok": False, "erro": "ja_ativa"}
            self._reset_estado()
            agora = self.agora()
            pasta = self.raiz / nome_pasta(agora)
            n = 2
            while pasta.exists():
                pasta = self.raiz / f"{nome_pasta(agora)}-{n}"
                n += 1
            etapa = "vad"
            try:
                prob_eu, prob_outros = self._probs()
                etapa = "disco"
                self.pasta = pasta
                reu = Reuniao(pasta=pasta.name, inicio=agora.isoformat(timespec="seconds"))
                reu.salvar(pasta)
                self.reuniao, self._inicio = reu, agora
                self.transcricao = Transcricao(pasta)
                self.gravador = Gravador(pasta)
                self.segmentadores = {"eu": self._segmentador("eu", prob_eu),
                                      "outros": self._segmentador("outros", prob_outros)}
                self.fila = Fila(self._transcrever, self.ao_texto)
                self.fila.iniciar()
                self._ativa = True          # antes de abrir: os primeiros blocos já podem chegar
                etapa = "captura"
                self.captura = self.captura_factory(self.ao_bloco)
                self.captura.abrir()
                d = self.captura.dispositivos
                self._ids = (d.eu_id, d.outros_id)
                reu.dispositivos = d.como_dict()
                etapa = "disco"
                reu.salvar(pasta)
            except Exception as e:  # noqa: BLE001
                log.exception("falha ao iniciar a reunião (%s)", etapa)
                self._desfazer()
                return {"ok": False, "erro": etapa, "detalhe": str(e)[:200]}
            log.info("reunião iniciada: %s (%s)", pasta.name, reu.dispositivos)
        self._publicar("iniciou", "Acompanhando a reunião.")
        return {"ok": True, "pasta": pasta.name, "inicio": reu.inicio}

    def _desfazer(self) -> None:
        self._ativa = False
        for fecha in (lambda: self.captura and self.captura.fechar(), lambda: self.fila and self.fila.parar(),
                      lambda: self.gravador and self.gravador.fechar()):
            try:
                fecha()
            except Exception:  # noqa: BLE001
                log.exception("desfazer")
        if self.pasta:
            shutil.rmtree(self.pasta, ignore_errors=True)
        self._reset_estado()

    def _passo(self, nome: str, fn) -> None:
        try:
            fn()
        except Exception:  # noqa: BLE001
            log.exception("falha em %s", nome)

    def _fechar_segmentos(self) -> None:
        """Fecha o segmento aberto de cada trilha e o enfileira (se houver fila)."""
        for trilha, segmentador in self.segmentadores.items():
            def um(segmentador=segmentador):
                s = segmentador.fechar()
                if s and self.fila:
                    self.fila.por(s)
            self._passo(f"segmentador {trilha}", um)

    def _esvaziar_fila(self) -> None:
        if not self.fila.esvaziar(30):
            log.warning("fila não esvaziou em 30 s")

    def encerrar(self, motivo: str = "pedido") -> dict:
        with self._trava_estado:
            if not self._ativa:
                return {"ok": False, "erro": "inativa"}
            self._encerrando = True
            pasta, reu, inicio = self.pasta, self.reuniao, self._inicio
            nao_transcritos = 0
            duracao, erro = 0, None
            try:
                if self.captura:
                    self._passo("fechar captura", self.captura.fechar)       # despacha a sobra do lote via ao_bloco
                self._fechar_segmentos()
                if self.fila:
                    self._passo("esvaziar fila", self._esvaziar_fila)
                    self._passo("parar fila", self.fila.parar)
                if self.gravador:
                    self._passo("fechar gravador", self.gravador.fechar)
                fim = self.agora()
                duracao = max(0, int((fim - inicio).total_seconds()))
                reu.fim, reu.duracao_s, reu.guardar_audio = fim.isoformat(timespec="seconds"), duracao, self.conf.guardar_audio
                reu.apagar_audio_em = "" if self.conf.guardar_audio else (
                    fim + dt.timedelta(hours=self.conf.apagar_audio_horas)).isoformat(timespec="seconds")
                reu.salvar(pasta)
            except Exception:  # noqa: BLE001
                log.exception("encerrar: falha ao salvar reuniao.json")
                erro = "salvar"
            finally:
                nao_transcritos = self._nao_transcritos
                res = {"ok": erro is None, "pasta": pasta.name, "duracao_s": duracao, "falas": self._falas, "motivo": motivo}
                if erro:
                    res["erro"] = erro
                log.info("reunião encerrada (%s): %s", motivo, res)
                self._ativa = self._encerrando = False
                self._reset_estado()
        resumo = f"Reunião encerrada: {mmss(duracao)} de duração, {res['falas']} falas."
        if nao_transcritos > 0:
            resumo += f" {nao_transcritos} trecho não transcrito." if nao_transcritos == 1 else f" {nao_transcritos} trechos não transcritos."
        self._publicar("encerrou", resumo, duracao, res["pasta"])
        if erro is None and self.conf.diarizacao:
            self._diarizar_depois(res["pasta"], duracao, resumo)
        return res

    # ---------- diarização (depois do encerrou, em thread) ----------
    def _estado_dia(self) -> dict:
        if self._dia_estado:
            return self._dia_estado()
        from . import diarizacao
        return diarizacao.estado()

    def _diarizar_depois(self, nome: str, duracao: int, resumo: str) -> None:
        try:
            est = self._estado_dia()
        except Exception:  # noqa: BLE001
            log.exception("estado da diarização")
            return
        if not est.get("pronta"):
            log.info("diarização ligada na config, mas o modelo não está pronto: %s", est.get("motivo"))
            return
        self.diarizar_pasta_em_thread(nome, duracao, resumo)

    def diarizar_pasta_em_thread(self, nome: str, duracao: int = 0, resumo: str = "") -> dict:
        """Uma diarização por vez. Publica `diarizando` e, ao fim, `encerrou` de novo (ou `erro`)."""
        with self._trava_dia:
            if self.diarizando:
                return {"ok": False, "erro": "rodando"}
            self.diarizando = True
        self._publicar("diarizando", "Separando os falantes da reunião.", duracao, nome)
        threading.Thread(target=self._trabalho_diarizacao, args=(nome, duracao, resumo), daemon=True, name="diarizacao").start()
        return {"ok": True}

    def _trabalho_diarizacao(self, nome: str, duracao: int, resumo: str) -> None:
        try:
            fn = self.diarizar_fn
            if fn is None:
                from . import diarizacao
                fn = diarizacao.diarizar_pasta
            r = fn(self.raiz / nome)
            if r and r.get("ok"):
                n = int(r.get("falantes", 0))
                frase = f"{n} falante identificado." if n == 1 else f"{n} falantes identificados."
                self._publicar("encerrou", f"{resumo} {frase}".strip() if resumo else f"Falantes separados: {frase}", duracao, nome)
            elif (r or {}).get("erro") == "sem_fala":
                self._publicar("encerrou", f"{resumo} Nenhum falante identificado.".strip() if resumo
                               else "Falantes separados: nenhum falante identificado.", duracao, nome)
            else:
                erro = (r or {}).get("erro", "falha")
                self._publicar("erro", f"Não consegui separar os falantes ({erro}).", duracao, nome)
        except Exception:  # noqa: BLE001
            log.exception("diarização")
            self._publicar("erro", "Não consegui separar os falantes (falha).", duracao, nome)
        finally:
            self.diarizando = False

    def _publicar(self, estado: str, resumo: str, duracao: int | None = None, pasta: str | None = None) -> None:
        try:
            self.publicar({"tipo": "reuniao", "estado": estado,
                           "duracao_s": self._duracao() if duracao is None else duracao,
                           "pasta": pasta or (self.pasta.name if self.pasta else ""), "resumo": resumo})
        except Exception:  # noqa: BLE001
            log.exception("publicar")

    def _duracao(self) -> int:
        return max(0, int((self.agora() - self._inicio).total_seconds())) if self._inicio else 0

    def status(self) -> dict:
        ativa, reu, fila = self._ativa, self.reuniao, self.fila
        return {"ativa": ativa, "pasta": reu.pasta if ativa and reu else None,
                "inicio": reu.inicio if ativa and reu else None,
                "duracao_s": self._duracao() if ativa else 0, "falas": self._falas if ativa else 0,
                "fila": fila.tamanho if ativa and fila else 0,
                "dispositivos": reu.dispositivos if ativa and reu else {}}

    # ---------- fluxo de áudio ----------
    def ao_bloco(self, trilha: str, pcm, t: float) -> None:
        if not self._ativa:
            return
        try:
            with self._trava_t:
                if self._t_inicio is None:
                    self._t_inicio = t
                rel = max(0.0, t - self._t_inicio)
                self._t_ultimo = rel
            self._preencher_lacuna(trilha, rel)
            self.gravador.escrever(trilha, pcm)
            for seg in self.segmentadores[trilha].alimentar(pcm, rel):
                self.fila.por(seg)
        except Exception:  # noqa: BLE001
            log.exception("ao_bloco %s", trilha)

    def _preencher_lacuna(self, trilha: str, rel: float) -> None:
        """O loopback não entrega quadros no silêncio: completa o FLAC com zeros para ele seguir o relógio das falas."""
        gravadas = self.gravador.amostras(trilha)
        lacuna = rel - gravadas / TAXA
        if lacuna <= LACUNA_MIN_S:
            return
        faltam = max(0, round(rel * TAXA) - gravadas) if lacuna <= LACUNA_MAX_S else int(LACUNA_MAX_S * TAXA)
        log.info("trilha %s: lacuna de %.1f s preenchida com silêncio%s", trilha, lacuna,
                 f" (limitada a {LACUNA_MAX_S:.0f} s)" if lacuna > LACUNA_MAX_S else "")
        while faltam > 0:
            n = min(faltam, TAXA)
            self.gravador.escrever(trilha, np.zeros(n, dtype=np.int16))
            faltam -= n

    def ao_texto(self, seg, texto: str, conf: float) -> None:
        if conf < 0 and self.transcricao is not None:       # o transcritor falhou: deixa rastro em vez de sumir
            self._nao_transcritos += 1
            self.transcricao.acrescentar(Fala(round(seg.t0, 2), round(seg.t1, 2), "sistema", "trecho não transcrito"))
            return
        texto = limpar(texto, self.conf.bloqueio, conf, self.conf.confianca_minima, bloqueio_exato=self.conf.bloqueio_exato)
        transcricao = self.transcricao
        if not texto or transcricao is None:
            return
        fala = Fala(round(seg.t0, 2), round(seg.t1, 2), seg.trilha, texto)
        if seg.trilha == "eu":
            outros = [f for f in transcricao.falas() if f.trilha == "outros" and f.t1 >= fala.t0 - 30]
            if eco(fala, outros, self.conf.eco_limiar):
                log.info("eco descartado")
                return
        transcricao.acrescentar(fala)
        self._falas += 1
        if seg.trilha == "eu" and e_encerramento(texto):
            threading.Thread(target=self.encerrar, args=("voz",), daemon=True, name="encerrar-voz").start()

    # ---------- dispositivos ----------
    def _ids_padrao(self) -> tuple:
        import pyaudiowpatch

        from .audio import dispositivos_padrao
        pa = pyaudiowpatch.PyAudio()        # novo a cada checagem: o PortAudio só relê os dispositivos ao iniciar
        try:
            d = dispositivos_padrao(pa)
            return (d.eu_id, d.outros_id)
        finally:
            pa.terminate()

    def verificar_dispositivos(self) -> None:
        if not self._ativa or self._encerrando:
            return
        ids = self._ids_padrao()
        with self._trava_estado:
            if not self._ativa or self._encerrando or ids == self._ids:
                return
            log.info("dispositivo padrão trocou: %s -> %s", self._ids, ids)
            antiga, self.captura = self.captura, None
            if antiga:
                self._passo("fechar captura antiga", antiga.fechar)
            self._fechar_segmentos()
            probs = {id(p): p for p in (self._prob, *(self._par_probs or ())) if p is not None}
            for prob in probs.values():
                if hasattr(prob, "reset"):
                    self._passo("reset do VAD", prob.reset)
            nova = None
            try:
                nova = self.captura_factory(self.ao_bloco)
                nova.abrir()
            except Exception:  # noqa: BLE001
                log.exception("falha ao reabrir a captura; tenta de novo no próximo ciclo")
                self._ids = ()          # sem captura: qualquer leitura de ids é diferente e tenta reabrir
                if nova is not None:
                    self._passo("fechar captura nova", nova.fechar)
                return
            self.captura = nova
            self._ids = ids
            t = self._t_ultimo if self._t_inicio is not None else self._duracao()
            self.transcricao.marcador(t, "dispositivo trocou")
            self.reuniao.dispositivos = nova.dispositivos.como_dict()
            self.reuniao.salvar(self.pasta)
