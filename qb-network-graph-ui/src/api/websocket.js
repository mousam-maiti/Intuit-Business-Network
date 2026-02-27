import { config } from '@/config/env';

/**
 * WebSocket connection manager.
 * Dispatches real-time events from the CDC pipeline to subscribers.
 */
class WebSocketManager {
  constructor() {
    this.ws = null;
    this.listeners = new Map();
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 2000;
  }

  connect() {
    try {
      this.ws = new WebSocket(config.api.wsUrl);

      this.ws.onopen = () => {
        console.log('[WS] Connected');
        this.reconnectAttempts = 0;
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this._dispatch(data);
        } catch (e) {
          console.warn('[WS] Failed to parse message:', e);
        }
      };

      this.ws.onclose = () => {
        console.log('[WS] Disconnected');
        this._reconnect();
      };

      this.ws.onerror = (err) => {
        console.error('[WS] Error:', err);
      };
    } catch (err) {
      console.error('[WS] Connection failed:', err);
      this._reconnect();
    }
  }

  _reconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn('[WS] Max reconnect attempts reached');
      return;
    }
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    setTimeout(() => this.connect(), delay);
  }

  _dispatch(event) {
    const { type } = event;
    const handlers = this.listeners.get(type) || [];
    handlers.forEach((fn) => fn(event.payload));

    // Also dispatch to wildcard listeners
    const wildcards = this.listeners.get('*') || [];
    wildcards.forEach((fn) => fn(event));
  }

  /** Subscribe to a specific event type. Returns unsubscribe function. */
  on(eventType, handler) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, []);
    }
    this.listeners.get(eventType).push(handler);

    return () => {
      const handlers = this.listeners.get(eventType);
      const idx = handlers.indexOf(handler);
      if (idx !== -1) handlers.splice(idx, 1);
    };
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.listeners.clear();
  }
}

/** Singleton WebSocket manager */
export const wsManager = new WebSocketManager();
