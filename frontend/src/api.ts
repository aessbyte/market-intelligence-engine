import { webAnalysisSchema, type WebAnalysis, type Market, type ProgressUpdate, type ApiFailure } from './contracts';

export class ApiError extends Error {
  readonly code: string;
  constructor(error: ApiFailure) { super(error.message); this.name = 'ApiError'; this.code = error.code; }
}
async function request(path: string, init?: RequestInit): Promise<unknown> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15_000);
  try {
    const response = await fetch(`/api/v1${path}`, { ...init, signal: controller.signal, credentials: 'omit', headers: { 'Content-Type': 'application/json', ...init?.headers } });
    const body: unknown = await response.json();
    if (!response.ok) {
      const value = typeof body === 'object' && body !== null && 'error' in body ? (body as { error: unknown }).error : null;
      if (typeof value === 'object' && value !== null && 'message' in value && typeof value.message === 'string') {
        throw new ApiError({ code: 'code' in value && typeof value.code === 'string' ? value.code : 'API_ERROR', message: value.message });
      }
      throw new ApiError({ code: 'API_ERROR', message: `A consulta falhou (HTTP ${response.status}). Tente novamente.` });
    }
    return body;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError({ code: 'CONNECTION_ERROR', message: 'Não foi possível conectar ao serviço. Confira a conexão e tente novamente.' });
  } finally { window.clearTimeout(timeout); }
}
const labels: Record<string, string> = { queued: 'Consulta na fila', validating: 'Validando símbolo e mercado', fetching: 'Obtendo candles fechados da Binance', analyzing: 'Executando o motor de análise', preparing: 'Preparando gráficos e auditoria', completed: 'Análise concluída', failed: 'Consulta não concluída' };
export async function analyzeSymbol(symbol: string, market: Market = 'spot', onProgress?: (update: ProgressUpdate) => void): Promise<WebAnalysis> {
  const start = await request('/analyses', { method: 'POST', body: JSON.stringify({ symbol, market, bars: 250 }) });
  if (typeof start !== 'object' || start === null || !('job_id' in start) || typeof start.job_id !== 'string') {
    throw new ApiError({ code: 'CONTRACT_ERROR', message: 'O serviço retornou uma identificação de consulta inválida.' });
  }
  const began = Date.now();
  while (Date.now() - began < 120_000) {
    const result = await request(`/jobs/${encodeURIComponent(start.job_id)}`);
    if (typeof result !== 'object' || result === null || !('status' in result) || !('stage' in result) || typeof result.stage !== 'string') {
      throw new ApiError({ code: 'CONTRACT_ERROR', message: 'O progresso recebido é inválido.' });
    }
    const status = result.status;
    if (!['queued', 'running', 'completed', 'failed'].includes(String(status))) throw new ApiError({ code: 'CONTRACT_ERROR', message: 'Estado de consulta inválido.' });
    onProgress?.({ stage: result.stage, status: status as ProgressUpdate['status'], message: labels[result.stage] ?? 'Processando análise' });
    if (status === 'failed') {
      const detail = 'error' in result ? result.error : null;
      if (typeof detail === 'object' && detail !== null && 'message' in detail && typeof detail.message === 'string') {
        throw new ApiError({ code: 'code' in detail && typeof detail.code === 'string' ? detail.code : 'ANALYSIS_FAILED', message: detail.message });
      }
      throw new ApiError({ code: 'ANALYSIS_FAILED', message: 'A análise não pôde ser concluída. Nenhum dado substituto foi gerado.' });
    }
    if (status === 'completed' && 'result_id' in result && typeof result.result_id === 'string') {
      const data = await request(`/analyses/${encodeURIComponent(result.result_id)}`);
      const parsed = webAnalysisSchema.safeParse(data);
      if (!parsed.success) throw new ApiError({ code: 'CONTRACT_ERROR', message: 'A resposta não respeita o contrato de dados. Os resultados não serão exibidos.' });
      return parsed.data;
    }
    await new Promise(resolve => window.setTimeout(resolve, 900));
  }
  throw new ApiError({ code: 'TIMEOUT', message: 'A consulta ultrapassou o tempo esperado. Tente novamente mais tarde.' });
}
export async function discoverSymbol(symbol: string): Promise<unknown> { return request(`/symbols/${encodeURIComponent(symbol)}`); }
export async function getCapabilities(): Promise<unknown> { return request('/health'); }
export function engineDownloadUrl(analysisId: string): string { return `/api/v1/analyses/${encodeURIComponent(analysisId)}/engine`; }
