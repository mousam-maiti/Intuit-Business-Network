import { ENTITIES } from './data';

/**
 * Mock WebSocket handler — simulates real-time events from the CDC pipeline.
 * Used when VITE_USE_MOCKS=true.
 */
export class MockWebSocket {
  constructor(onMessage) {
    this.onMessage = onMessage;
    this.intervals = [];
    this._start();
  }

  _start() {
    // Simulate a new auto-detected connection every 30s
    this.intervals.push(
      setInterval(() => {
        const entity = ENTITIES[Math.floor(Math.random() * ENTITIES.length)];
        this.onMessage({
          type: 'connection.detected',
          payload: {
            id: 'a-' + Date.now(),
            connType: Math.random() > 0.5 ? 'vendor' : 'client',
            source: 'Bill #' + (1050 + Math.floor(Math.random() * 100)),
            sourceDate: 'Feb ' + (1 + Math.floor(Math.random() * 28)),
            entity,
            tier: 1,
            confidence: 0.85 + Math.random() * 0.12,
            latency: Math.floor(20 + Math.random() * 40) + 'ms',
            time: 'Just now',
          },
        });
      }, 30000)
    );

    // Simulate edge weight update every 20s
    this.intervals.push(
      setInterval(() => {
        this.onMessage({
          type: 'edge.updated',
          payload: {
            source: 'e1',
            target: 'e' + (2 + Math.floor(Math.random() * 9)),
            volumeDelta: Math.floor(Math.random() * 10000),
          },
        });
      }, 20000)
    );

    // Simulate new pending match every 45s
    this.intervals.push(
      setInterval(() => {
        this.onMessage({
          type: 'match.pending',
          payload: {
            id: 'm-' + Date.now(),
            inputName: 'New Vendor ' + Math.floor(Math.random() * 100),
            confidence: 0.5 + Math.random() * 0.35,
          },
        });
      }, 45000)
    );
  }

  close() {
    this.intervals.forEach(clearInterval);
    this.intervals = [];
  }
}
