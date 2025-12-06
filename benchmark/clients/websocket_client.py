"""
WebSocket client for real-time communication with Open WebUI.

Provides async WebSocket connections for channel events and real-time messaging.
"""

import asyncio
import json
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
import socketio


@dataclass
class WebSocketMessage:
    """Represents a received WebSocket message."""
    event: str
    data: Dict[str, Any]
    timestamp: float = 0.0


class WebSocketClient:
    """
    WebSocket client for Open WebUI real-time features.
    
    Uses Socket.IO to connect to Open WebUI's WebSocket endpoint.
    """
    
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 60.0,
    ):
        """
        Initialize the WebSocket client.
        
        Args:
            base_url: Base URL of the Open WebUI instance
            token: Authentication token
            timeout: Connection timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.timeout = timeout
        
        self._sio: Optional[socketio.AsyncClient] = None
        self._connected = False
        self._messages: List[WebSocketMessage] = []
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._user_id: Optional[str] = None
        
    @property
    def connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._connected and self._sio is not None
    
    @property
    def messages(self) -> List[WebSocketMessage]:
        """Get all received messages."""
        return self._messages
    
    async def connect(self) -> bool:
        """
        Establish WebSocket connection.
        
        Returns:
            True if connected successfully
        """
        if self._connected:
            return True
        
        self._sio = socketio.AsyncClient(
            reconnection=True,
            reconnection_delay=1,
            reconnection_delay_max=5,
        )
        
        # Set up event handlers
        @self._sio.event
        async def connect():
            self._connected = True
            # Emit user-join event
            await self._sio.emit('user-join', {'auth': {'token': self.token}})
        
        @self._sio.event
        async def disconnect():
            self._connected = False
        
        @self._sio.event
        async def connect_error(data):
            self._connected = False
        
        @self._sio.on('events:channel')
        async def on_channel_event(data):
            import time
            message = WebSocketMessage(
                event='events:channel',
                data=data,
                timestamp=time.time(),
            )
            self._messages.append(message)
            
            # Call registered handlers
            for handler in self._event_handlers.get('events:channel', []):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception:
                    pass
        
        @self._sio.on('*')
        async def on_any_event(event, data):
            import time
            message = WebSocketMessage(
                event=event,
                data=data if isinstance(data, dict) else {'data': data},
                timestamp=time.time(),
            )
            self._messages.append(message)
        
        try:
            # Connect with authentication
            await self._sio.connect(
                self.base_url,
                socketio_path='/ws/socket.io',
                transports=['websocket'],
                auth={'token': self.token},
                wait_timeout=self.timeout,
            )
            
            # Wait for connection to be established
            await asyncio.sleep(0.5)
            return self._connected
            
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"Failed to connect WebSocket: {e}")
    
    async def disconnect(self) -> None:
        """Disconnect the WebSocket."""
        if self._sio:
            await self._sio.disconnect()
            self._connected = False
            self._sio = None
    
    async def join_channels(self) -> None:
        """Join all channels the user has access to."""
        if not self._connected:
            raise RuntimeError("Not connected")
        
        await self._sio.emit('join-channels', {'auth': {'token': self.token}})
    
    async def emit_typing(self, channel_id: str, message_id: Optional[str] = None) -> None:
        """
        Emit a typing indicator event.
        
        Args:
            channel_id: Channel ID
            message_id: Optional message ID if typing in a thread
        """
        if not self._connected:
            raise RuntimeError("Not connected")
        
        data = {
            'channel_id': channel_id,
            'data': {'type': 'typing'},
        }
        if message_id:
            data['message_id'] = message_id
        
        await self._sio.emit('events:channel', data)
    
    def on_event(self, event: str, handler: Callable) -> None:
        """
        Register an event handler.
        
        Args:
            event: Event name to handle
            handler: Callback function
        """
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)
    
    def clear_messages(self) -> None:
        """Clear all stored messages."""
        self._messages.clear()
    
    async def wait_for_event(
        self,
        event: str,
        timeout: float = 10.0,
        condition: Optional[Callable[[Dict], bool]] = None,
    ) -> Optional[WebSocketMessage]:
        """
        Wait for a specific event.
        
        Args:
            event: Event name to wait for
            timeout: Maximum time to wait
            condition: Optional condition function
            
        Returns:
            The matching message, or None if timeout
        """
        start_count = len(self._messages)
        elapsed = 0.0
        interval = 0.1
        
        while elapsed < timeout:
            # Check new messages
            for msg in self._messages[start_count:]:
                if msg.event == event:
                    if condition is None or condition(msg.data):
                        return msg
            
            await asyncio.sleep(interval)
            elapsed += interval
        
        return None


class WebSocketPool:
    """
    Pool of WebSocket clients for concurrent benchmark operations.
    
    Manages multiple WebSocket connections for simulating concurrent users.
    """
    
    def __init__(self, base_url: str, timeout: float = 60.0):
        """
        Initialize the WebSocket pool.
        
        Args:
            base_url: Base URL of the Open WebUI instance
            timeout: Connection timeout in seconds
        """
        self.base_url = base_url
        self.timeout = timeout
        self._clients: List[WebSocketClient] = []
    
    async def create_connections(self, tokens: List[str]) -> List[WebSocketClient]:
        """
        Create WebSocket connections for multiple users.
        
        Args:
            tokens: List of authentication tokens
            
        Returns:
            List of connected WebSocket clients
        """
        clients = []
        
        for token in tokens:
            client = WebSocketClient(self.base_url, token, self.timeout)
            try:
                await client.connect()
                await client.join_channels()
                clients.append(client)
            except Exception as e:
                # Continue with other clients even if one fails
                pass
        
        self._clients = clients
        return clients
    
    async def close_all(self) -> None:
        """Close all WebSocket connections."""
        for client in self._clients:
            try:
                await client.disconnect()
            except Exception:
                pass
        self._clients.clear()
    
    def __len__(self) -> int:
        """Get number of connected clients."""
        return len(self._clients)
    
    def __iter__(self):
        """Iterate over clients."""
        return iter(self._clients)
    
    def __getitem__(self, index: int) -> WebSocketClient:
        """Get client by index."""
        return self._clients[index]
