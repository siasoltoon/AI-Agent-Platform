import { useEffect, useState } from 'react';
import { createEventConnection } from '../services/websocket';

export function useAgentData(url) {
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!url) return;
    const socket = createEventConnection(url, setData);
    return () => socket.close();
  }, [url]);

  return data;
}
