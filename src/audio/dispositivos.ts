/** Dispositivos de áudio: enumeração, seleção e persistência da preferência.
 *
 * Contrato da T9 (0.7):
 * - `microfone_id` / `saida_id`: string vazia = padrão do sistema.
 * - Rótulos são informativos; a seleção usa o `deviceId` exato.
 * - `devicechange` revalida a preferência quando dispositivo reaparece.
 * - A escolha é salva no HUD (`config.json`) e repassada à reunião via ponte.
 */

export interface DispositivoInfo {
  deviceId: string;
  label: string;
  kind: "audioinput" | "audiooutput";
}

export interface PreferenciaDispositivos {
  microfone_id: string;
  microfone_rotulo: string;
  saida_id: string;
  saida_rotulo: string;
}

const PADRAO: PreferenciaDispositivos = {
  microfone_id: "",
  microfone_rotulo: "",
  saida_id: "",
  saida_rotulo: "",
};

let preferenciaAtual: PreferenciaDispositivos = { ...PADRAO };
let ouvintesDeviceChange: Array<() => void> = [];

/** Normaliza rótulo para comparação (lowercase, trim, colapsa espaços). */
export function normalizarRotulo(rotulo: string): string {
  return rotulo.toLowerCase().trim().replace(/\s+/g, " ");
}

/** Lista dispositivos de entrada ou saída disponíveis. */
export async function listarDispositivos(
  kind: "audioinput" | "audiooutput",
): Promise<DispositivoInfo[]> {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices
      .filter((d) => d.kind === kind && d.deviceId)
      .map((d) => ({
        deviceId: d.deviceId,
        label: d.label || `Dispositivo ${d.deviceId.slice(0, 8)}`,
        kind: d.kind as "audioinput" | "audiooutput",
      }));
  } catch {
    return [];
  }
}

/** Resolve a preferência atual contra a lista real de dispositivos.
 * Retorna o deviceId se encontrado, ou "" (padrão) se ausente/ambíguo. */
export function resolverPreferencia(
  idSalvo: string,
  rotuloSalvo: string,
  disponiveis: DispositivoInfo[],
): { deviceId: string; aviso?: string } {
  if (!idSalvo && !rotuloSalvo) return { deviceId: "" };
  // Busca exata por deviceId primeiro
  const porId = disponiveis.find((d) => d.deviceId === idSalvo);
  if (porId) return { deviceId: porId.deviceId };
  // Fallback por rótulo normalizado (caso o deviceId mude entre sessões)
  const norm = normalizarRotulo(rotuloSalvo);
  if (norm) {
    const porRotulo = disponiveis.filter(
      (d) => normalizarRotulo(d.label) === norm,
    );
    if (porRotulo.length === 1) return { deviceId: porRotulo[0].deviceId };
    if (porRotulo.length > 1) {
      return {
        deviceId: "",
        aviso: `Ambíguo: ${porRotulo.length} dispositivos com nome "${rotuloSalvo}"`,
      };
    }
  }
  // Dispositivo salvo não encontrado: usa padrão sem apagar a preferência
  return {
    deviceId: "",
    aviso: idSalvo
      ? `Dispositivo "${rotuloSalvo || idSalvo}" não encontrado; usando padrão`
      : undefined,
  };
}

/** Aplica a preferência de microfone na captura. Retorna constraints atualizadas. */
export function constraintsComMicrofone(
  base: MediaStreamConstraints,
  pref: PreferenciaDispositivos,
): MediaStreamConstraints {
  if (!pref.microfone_id) return base;
  const audio =
    typeof base.audio === "object" && base.audio !== null
      ? { ...(base.audio as MediaTrackConstraints) }
      : {};
  audio.deviceId = { exact: pref.microfone_id };
  return { ...base, audio };
}

/** Aplica setSinkId na reprodução quando suportado.
 * Retorna true se aplicado, false se não suportado ou falhou. */
export async function aplicarSaida(
  elemento: HTMLAudioElement | AudioContext,
  saidaId: string,
): Promise<boolean> {
  if (!saidaId) return false;
  try {
    if ("setSinkId" in elemento) {
      await (elemento as HTMLAudioElement & { setSinkId: (id: string) => Promise<void> }).setSinkId(saidaId);
      return true;
    }
  } catch {
    // setSinkId pode falhar se o dispositivo sumiu; caller decide fallback
  }
  return false;
}

/** Obtém a preferência atual (cópia). */
export function obterPreferencia(): PreferenciaDispositivos {
  return { ...preferenciaAtual };
}

/** Atualiza a preferência em memória e notifica ouvintes de devicechange. */
export function definirPreferencia(pref: Partial<PreferenciaDispositivos>): void {
  preferenciaAtual = { ...preferenciaAtual, ...pref };
  for (const cb of ouvintesDeviceChange) {
    try {
      cb();
    } catch {
      // ouvinte não pode quebrar a cadeia
    }
  }
}

/** Assina mudanças de dispositivo (navigator.mediaDevices.ondevicechange).
 * Retorna função de cancelamento. */
export function onDeviceChange(cb: () => void): () => void {
  ouvintesDeviceChange.push(cb);
  const handler = () => cb();
  try {
    navigator.mediaDevices.addEventListener("devicechange", handler);
  } catch {
    // Alguns ambientes não suportam addEventListener em mediaDevices
  }
  return () => {
    ouvintesDeviceChange = ouvintesDeviceChange.filter((c) => c !== cb);
    try {
      navigator.mediaDevices.removeEventListener("devicechange", handler);
    } catch {
      // ignora
    }
  };
}

/** Serializa a preferência para salvar no config/HUD. */
export function preferenciaParaConfig(): PreferenciaDispositivos {
  return { ...preferenciaAtual };
}

/** Restaura a preferência do config/HUD. */
export function restaurarPreferencia(cfg: Partial<PreferenciaDispositivos>): void {
  preferenciaAtual = {
    microfone_id: cfg.microfone_id ?? "",
    microfone_rotulo: cfg.microfone_rotulo ?? "",
    saida_id: cfg.saida_id ?? "",
    saida_rotulo: cfg.saida_rotulo ?? "",
  };
}