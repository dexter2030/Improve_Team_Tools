/**
 * Typed errors dla Riot API.
 *
 * Pozwala UI rozróżnić "klucz wygasł" (UnauthorizedError) od "gracz nie
 * istnieje" (NotFoundError) od "rate limit" (RateLimitError) bez parsowania
 * status code w callerze.
 */

export class RiotApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body?: unknown
  ) {
    super(message);
    this.name = "RiotApiError";
  }
}

export class UnauthorizedError extends RiotApiError {
  constructor(body?: unknown) {
    super(
      "Riot API key jest nieprawidłowy lub wygasł (401/403). Odśwież RIOT_API_KEY.",
      401,
      body
    );
    this.name = "UnauthorizedError";
  }
}

export class NotFoundError extends RiotApiError {
  constructor(message: string, body?: unknown) {
    super(message, 404, body);
    this.name = "NotFoundError";
  }
}

export class RateLimitError extends RiotApiError {
  constructor(
    public readonly retryAfterSeconds: number,
    body?: unknown
  ) {
    super(
      `Rate limit przekroczony, ponów za ${retryAfterSeconds}s.`,
      429,
      body
    );
    this.name = "RateLimitError";
  }
}
