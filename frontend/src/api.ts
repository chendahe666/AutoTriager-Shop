export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.name = 'ApiError'; this.status = status; }
}

export async function request<T>(base: string, path: string, signal?: AbortSignal, body?: unknown): Promise<T> {
  const response = await fetch(`${base.replace(/\/$/, '')}${path}`, {
    signal,
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: 'same-origin',
  });
  const value: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const message = value && typeof value === 'object' && 'error' in value ? String(value.error) : `${response.status} ${response.statusText}`;
    throw new ApiError(response.status, message);
  }
  if (value === null) throw new Error('The service returned an invalid JSON response.');
  return value as T;
}

// Telemetry is untrusted text. Source links never execute local file or script URLs.
export function safeSource(url: string): string | null {
  try {
    const parsed = new URL(url);
    return (parsed.protocol === 'http:' || parsed.protocol === 'https:') && !parsed.username && !parsed.password ? parsed.href : null;
  } catch { return null; }
}
