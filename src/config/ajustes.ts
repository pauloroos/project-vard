/** Contrato de escrita usado pela tela e pelo MCP Python (fixtures compartilhadas). */
import { validarPaineis } from "./paineis";
import { validarPerfil } from "./perfil";
import { validarHabilidades } from "./habilidades";

export function validarDocumento(arquivo: string, valor: unknown): unknown {
  if (arquivo === "paineis") return validarPaineis(valor);
  if (arquivo === "perfil") return validarPerfil(valor);
  if (arquivo === "habilidades") return validarHabilidades(valor);
  if (!valor || typeof valor !== "object" || Array.isArray(valor)) throw new Error("A configuração deve ser um objeto");
  const obj = valor as Record<string, unknown>;
  if (arquivo === "programas") {
    for (const campo of ["apelidos", "sites"]) {
      const secao = campo in obj ? obj[campo] : {};
      if (!secao || typeof secao !== "object" || Array.isArray(secao) || Object.values(secao).some((v) => typeof v !== "string")) throw new Error("Destinos devem ser texto");
    }
  } else if (arquivo === "hud") {
    for (const campo of ["cor_elementos", "voz_motor", "voz_propria", "voz", "elevenlabs_voz", "gemini_voz", "voz_reserva_motor", "voz_reserva_id", "cerebro"]) {
      if (campo in obj && typeof obj[campo] !== "string") throw new Error("O ajuste deve ser texto");
    }
    if (obj.cor_elementos !== undefined && obj.cor_elementos !== "" && !/^#[0-9a-fA-F]{6}$/.test(obj.cor_elementos as string)) throw new Error("Cor inválida");
    const op = "opacidade_elementos" in obj ? obj.opacidade_elementos : 1;
    if (typeof op !== "number" || !Number.isFinite(op) || op < 0.2 || op > 1) throw new Error("Opacidade inválida");
    for (const [campo, validos] of [["voz_provedor", ["propria", "openjarvis", "elevenlabs", "gemini"]], ["voz_reserva_provedor", ["propria", "openjarvis", "elevenlabs", "gemini", "nenhuma"]], ["cerebro", ["openjarvis", "proprio"]]] as const) {
      if (campo in obj && !(validos as readonly unknown[]).includes(obj[campo])) throw new Error("Provedor ou cérebro inválido");
    }
  } else throw new Error("Arquivo de configuração desconhecido");
  return structuredClone(obj);
}
