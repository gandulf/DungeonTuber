type Handler = (data: any) => void;

const handlers = new Map<string, Set<Handler>>();
let socket: WebSocket | null = null;
let retry = 0;
let keepAlive: ReturnType<typeof setInterval> | null = null;
let stopped = false;

function dispatch(event: string, data: unknown) {
  handlers.get(event)?.forEach((handler) => handler(data));
  handlers.get('*')?.forEach((handler) => handler({ event, data }));
}

export function connectEvents() {
  stopped = false;
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  socket = new WebSocket(`${protocol}://${location.host}/ws`);
  socket.onopen = () => {
    retry = 0;
    dispatch('connection', { connected: true });
    keepAlive = setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send('ping'), 25000);
  };
  socket.onmessage = (message) => {
    try {
      const { event, data } = JSON.parse(message.data);
      dispatch(event, data);
    } catch { /* ignore malformed messages */ }
  };
  socket.onclose = () => {
    if (keepAlive) clearInterval(keepAlive);
    dispatch('connection', { connected: false });
    if (!stopped) setTimeout(connectEvents, Math.min(30000, 1000 * 2 ** retry++));
  };
}

export function disconnectEvents() {
  stopped = true;
  socket?.close();
}

export function onEvent(event: string, handler: Handler): () => void {
  if (!handlers.has(event)) handlers.set(event, new Set());
  handlers.get(event)!.add(handler);
  return () => handlers.get(event)?.delete(handler);
}
