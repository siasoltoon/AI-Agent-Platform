export function createEventConnection(url, onMessage) {
  const socket = new WebSocket(url);

  socket.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch {
      onMessage(event.data);
    }
  };

  return socket;
}
