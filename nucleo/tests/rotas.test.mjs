import test from "node:test";
import assert from "node:assert/strict";
import { extrairComando, classificar, ehInterrupcao, ehConfirmacao, proximoEstadoPorStatus, JanelaTermino } from "../viewer/rotas.js";
import { FALAS } from "../viewer/falas.js";

test("gatilho no começo, com vírgula e maiúsculas", () => {
  assert.equal(extrairComando("Vard, abre o YouTube"), "abre o YouTube");
  assert.equal(extrairComando("vard abre o youtube"), "abre o youtube");
});

test("pontuação antes do nome não corrompe o comando", () => {
  assert.equal(extrairComando(", vard abre o youtube"), "abre o youtube");
  assert.equal(extrairComando("... Vard, abre o YouTube"), "abre o YouTube");
  assert.equal(extrairComando("Vard"), "");
});

test("variantes do reconhecimento disparam", () => {
  assert.equal(extrairComando("Varde abre o youtube"), "abre o youtube");
  assert.equal(extrairComando("Ward, que horas são"), "que horas são");
});

test("nome no meio ou ausente não dispara", () => {
  assert.equal(extrairComando("abre o YouTube, Vard"), null);
  assert.equal(extrairComando("abre o youtube"), null);
  assert.equal(extrairComando("a varanda está suja"), null);
});

test("classificação de rota", () => {
  assert.equal(classificar("o que você está vendo"), "see");
  assert.equal(classificar("olha a tela e me diz o que é isso"), "see");
  assert.equal(classificar("lê isso pra mim"), "see");
  assert.equal(classificar("modo jogo"), "modo");
  assert.equal(classificar("abre o youtube"), "ask");
});

test("interrupções", () => {
  assert.equal(ehInterrupcao("para"), true);
  assert.equal(ehInterrupcao("Espera!"), true);
  assert.equal(ehInterrupcao("para de brincadeira e abre o chrome"), false);
});

test("janela de término junta pedaços e despacha uma vez", async () => {
  const despachados = [];
  const j = new JanelaTermino(30, (t) => despachados.push(t));
  j.receber("Vard, abre o");
  await new Promise((r) => setTimeout(r, 10));
  j.receber("youtube");
  await new Promise((r) => setTimeout(r, 60));
  assert.deepEqual(despachados, ["Vard, abre o youtube"]);
});

const espera = (ms) => new Promise((r) => setTimeout(r, ms));

test("conversa antes do Vard é ignorada", async () => {
  const d = [];
  const j = new JanelaTermino(20, (t) => d.push(t));
  j.receber("e aí ele falou que não vinha");
  await espera(50);
  assert.deepEqual(d, []);
  assert.equal(j.buffer, "");
});

test("Vard no meio do buffer recomeça a partir do gatilho", async () => {
  const d = [];
  const j = new JanelaTermino(20, (t) => d.push(t));
  j.receber("Vard, abre o");
  j.receber("aí ele falou Vard, abre o chrome");
  await espera(60);
  assert.deepEqual(d, ["Vard, abre o chrome"]);
});

test("Vard no meio de um final vazio-buffer começa dali", async () => {
  const d = [];
  const j = new JanelaTermino(20, (t) => d.push(t));
  j.receber("conversa qualquer vard que horas são");
  await espera(60);
  assert.deepEqual(d, ["vard que horas são"]);
});

test("teto de 5 s despacha o que tem mesmo com áudio contínuo", async () => {
  const d = [];
  const j = new JanelaTermino(40, (t) => d.push(t), { teto: 100 });
  j.receber("Vard, abre");
  for (let i = 0; i < 6; i++) { await espera(25); j.receber("barulho"); }
  await espera(60);
  assert.equal(d.length >= 1, true);
  assert.match(d[0], /^Vard, abre/);
});

test("cancelar limpa buffer e timer", async () => {
  const d = [];
  const j = new JanelaTermino(20, (t) => d.push(t));
  j.receber("Vard, abre o youtube");
  j.cancelar();
  await espera(50);
  assert.deepEqual(d, []);
  assert.equal(j.buffer, "");
});

test("resposta sem gatilho só entra quando a confirmação está ativa", async () => {
  const d = [];
  let confirmando = true;
  const j = new JanelaTermino(20, (t) => d.push(t), { semGatilho: () => confirmando });
  j.receber("sim");
  await espera(50);
  assert.deepEqual(d, ["sim"]);
});

test("variantes Vardi e Bard", () => {
  assert.equal(extrairComando("Vardi, abre o chrome"), "abre o chrome");
  assert.equal(extrairComando("Bard abre o chrome"), "abre o chrome");
});

test("classificar tolera acento torto em modo jogo", () => {
  assert.equal(classificar("módo jogo"), "modo");
});

test("FALAS tem as 8 chaves fixas", () => {
  for (const k of ["saudacao", "pensando", "telaNaoCompartilhada", "telaAindaCarregando", "erroModelo", "erroOuvido", "modoJogoConfirmar", "modoJogoAtivado"]) {
    assert.equal(typeof FALAS[k], "string", k);
  }
});

test("FALAS.erros cobre todos os códigos da ponte", () => {
  for (const k of ["modelo_fora", "modelo_demorou", "modelo_http", "modelo_vazio", "rede", "nao_json", "segredos"]) {
    assert.equal(typeof FALAS.erros[k], "string", k);
  }
});

test("Vard como última palavra é ignorado", async () => {
  const d = [];
  const j = new JanelaTermino(20, (t) => d.push(t));
  j.receber("abre o Chrome, Vard");
  await espera(50);
  assert.deepEqual(d, []);
});

test("conversa e depois Vard com comando despacha a partir do Vard", async () => {
  const d = [];
  const j = new JanelaTermino(20, (t) => d.push(t));
  j.receber("então Vard, abre o Chrome");
  await espera(50);
  assert.deepEqual(d, ["Vard, abre o Chrome"]);
  assert.equal(extrairComando(d[0]), "abre o Chrome");
});

test("só Vard no começo despacha (saudação)", async () => {
  const d = [];
  const j = new JanelaTermino(20, (t) => d.push(t));
  j.receber("Vard");
  await espera(50);
  assert.deepEqual(d, ["Vard"]);
});

test("confirmação do modo jogo só com sim ou confirmo", () => {
  for (const t of ["sim", "Sim!", "  sim.", "confirmo", "Confirmo!"]) assert.equal(ehConfirmacao(t), true, t);
  for (const t of ["simples não", "Simone", "pode ser", "pode", "sim, mas depois", "não", ""]) assert.equal(ehConfirmacao(t), false, t);
});

test("estado da aba pelo /status", () => {
  assert.equal(proximoEstadoPorStatus("ligado", { modo: "jogo" }), "jogo");
  assert.equal(proximoEstadoPorStatus("ligado", null), "ponte_fora");
  assert.equal(proximoEstadoPorStatus("jogo", null), "ponte_fora");
  assert.equal(proximoEstadoPorStatus("jogo", { modo: "ligando" }), "jogo");
  assert.equal(proximoEstadoPorStatus("ponte_fora", { modo: "ligando" }), "jogo");
  assert.equal(proximoEstadoPorStatus("jogo", { modo: "ligado" }), "ligado");
  assert.equal(proximoEstadoPorStatus("ponte_fora", { modo: "ligado" }), "ligado");
  assert.equal(proximoEstadoPorStatus("ligado", { modo: "desconhecido" }), "ligado");   // ponte subida à mão
  assert.equal(proximoEstadoPorStatus("ligado", { modo: "erro" }), "ligado");
});

test("FALAS.erros cobre os códigos do /modo", () => {
  for (const k of ["modo_script", "modo_falhou", "origem_recusada"]) assert.equal(typeof FALAS.erros[k], "string", k);
});
