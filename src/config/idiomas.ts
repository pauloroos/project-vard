// Códigos de idioma que o faster-whisper aceita (ISO 639-1, sem região).
// Os oito mais pedidos vêm primeiro, na ordem do painel; o resto em ordem alfabética do nome.

const DESTAQUES: [string, string][] = [
  ["pt", "Português"], ["en", "English"], ["es", "Español"], ["fr", "Français"],
  ["de", "Deutsch"], ["it", "Italiano"], ["ja", "日本語"], ["zh", "中文"],
];

const DEMAIS: [string, string][] = [
  ["af", "Africâner"], ["am", "Amárico"], ["ar", "Árabe"], ["as", "Assamês"], ["az", "Azeri"],
  ["ba", "Bascquir"], ["be", "Bielorrusso"], ["bg", "Búlgaro"], ["bn", "Bengalês"], ["bo", "Tibetano"], ["br", "Bretão"], ["bs", "Bósnio"],
  ["ca", "Catalão"], ["cs", "Tcheco"], ["cy", "Galês"], ["da", "Dinamarquês"], ["el", "Grego"],
  ["et", "Estoniano"], ["eu", "Basco"], ["fa", "Persa"], ["fi", "Finlandês"], ["fo", "Feroês"],
  ["gl", "Galego"], ["gu", "Gujarati"], ["ha", "Hausa"], ["haw", "Havaiano"], ["he", "Hebraico"], ["hi", "Hindi"], ["hr", "Croata"],
  ["ht", "Crioulo do Haiti"], ["hu", "Húngaro"], ["hy", "Armênio"], ["id", "Indonésio"], ["is", "Islandês"], ["jw", "Javanês"],
  ["ka", "Georgiano"], ["kk", "Cazaque"], ["km", "Khmer"], ["kn", "Canarês"], ["ko", "Coreano"],
  ["lb", "Luxemburguês"], ["ln", "Lingala"], ["lo", "Lao"], ["lt", "Lituano"], ["lv", "Letão"],
  ["mg", "Malgaxe"], ["mi", "Maori"], ["mk", "Macedônio"], ["ml", "Malaiala"], ["mn", "Mongol"], ["mr", "Marati"], ["ms", "Malaio"], ["mt", "Maltês"], ["my", "Birmanês"],
  ["ne", "Nepali"], ["nl", "Holandês"], ["nn", "Norueguês Nynorsk"], ["no", "Norueguês"], ["oc", "Occitano"],
  ["pa", "Panjabi"], ["pl", "Polonês"], ["ps", "Pashto"], ["ro", "Romeno"], ["ru", "Russo"],
  ["sa", "Sânscrito"], ["sd", "Sindhi"], ["si", "Sinhala"], ["sk", "Eslovaco"], ["sl", "Esloveno"], ["sn", "Shona"], ["so", "Somali"],
  ["sq", "Albanês"], ["sr", "Sérvio"], ["su", "Sundanês"], ["sv", "Sueco"], ["sw", "Suaíli"],
  ["ta", "Tâmil"], ["te", "Telugu"], ["tg", "Tadjique"], ["th", "Tailandês"], ["tk", "Turcomano"], ["tl", "Tagalo"], ["tr", "Turco"], ["tt", "Tatar"],
  ["uk", "Ucraniano"], ["ur", "Urdu"], ["uz", "Uzbeque"], ["vi", "Vietnamita"], ["yi", "Iídiche"], ["yo", "Iorubá"], ["yue", "Cantonês"],
];

const semAcento = (n: string) => n.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

/** Todos os idiomas do whisper: os destaques na ordem pedida, o resto em ordem alfabética do nome. */
export const IDIOMAS: [string, string][] = [
  ...DESTAQUES,
  ...[...DEMAIS].sort((a, b) => { const x = semAcento(a[1]); const y = semAcento(b[1]); return x < y ? -1 : x > y ? 1 : 0; }),
];

/** Opções do campo de idioma: automático primeiro, lista depois; valor salvo fora da lista continua valendo como "Outro:". */
export function opcoesIdioma(valorAtual: string): [string, string][] {
  const opcoes: [string, string][] = [["", "Detectar automaticamente"], ...IDIOMAS];
  if (valorAtual !== "" && !IDIOMAS.some(([codigo]) => codigo === valorAtual)) opcoes.push([valorAtual, `Outro: ${valorAtual}`]);
  return opcoes;
}

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/** O campo inteiro do painel (rótulo, lista e a linha de ajuda) para o valor dado. */
export function campoIdioma(valor: string): string {
  const opcoes = opcoesIdioma(valor)
    .map(([codigo, nome]) => `<option value="${esc(codigo)}" ${codigo === valor ? "selected" : ""}>${esc(nome)}</option>`)
    .join("");
  return `<label>Idioma do reconhecimento<select id="cfg-idioma">${opcoes}</select></label>
      <p class="nota">O reconhecimento usa o código do idioma, sem região: Português vale para Brasil e Portugal.</p>`;
}
