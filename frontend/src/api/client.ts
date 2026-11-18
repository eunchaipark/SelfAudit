// API 부르기는 여기서만 한다 (eslint가 다른 곳의 fetch를 막는다). 같은 출처의 /api/v1만 부른다.
import type { components } from './schema';

export type Schemas = components['schemas'];

// 서버의 CSRF 방어(NFR-08)가 요구하는 머리말
const CLIENT_HEADER = { 'X-SelfAudit-Client': '1' } as const;
const API_PREFIX = '/api/v1/';
const FALLBACK_MESSAGE = '서버 오류가 났습니다';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'DELETE';
  json?: unknown;
  body?: Blob;
  headers?: Record<string, string>;
};

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  if (!path.startsWith(API_PREFIX)) {
    throw new Error(`API 경로가 아닙니다: ${path}`);
  }
  const headers: Record<string, string> = { ...CLIENT_HEADER, ...options.headers };
  let body: BodyInit | undefined = options.body;
  if (options.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(options.json);
  }
  const res = await fetch(path, {
    method: options.method ?? 'GET',
    headers,
    body,
    credentials: 'same-origin',
  });
  if (!res.ok) {
    throw await toApiError(res);
  }
  return (await res.json()) as T;
}

async function toApiError(res: Response): Promise<ApiError> {
  try {
    const data = (await res.json()) as Partial<Schemas['ErrorOut']>;
    return new ApiError(res.status, data.code ?? 'UNKNOWN', data.message ?? FALLBACK_MESSAGE);
  } catch {
    return new ApiError(res.status, 'UNKNOWN', FALLBACK_MESSAGE);
  }
}
