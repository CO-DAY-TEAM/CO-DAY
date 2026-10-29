export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
  csrf?: string,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
      ...options.headers,
    },
  })
  const body = await response.json().catch(() => null)
  if (!response.ok)
    throw new ApiError(
      response.status,
      body?.message ??
        '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.',
    )
  return body as T
}
