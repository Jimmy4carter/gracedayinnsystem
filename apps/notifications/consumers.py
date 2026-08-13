import asyncio
import json
import uuid
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .chat import can_access_conversation, send_chat_message
from .models import ChatConversation


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.reference = self.scope['url_route']['kwargs']['reference']
        params = parse_qs(self.scope.get('query_string', b'').decode())
        session_tokens = self.scope.get('session', {}).get('chat_tokens', {})
        self.visitor_token = params.get('token', [''])[0] or session_tokens.get(str(self.reference), '')
        self.conversation = await self._get_authorized_conversation()
        if not self.conversation:
            await self.close(code=4403)
            return
        self.group_name = f'chat_{str(self.reference).replace("-", "")}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        self._last_typing_at = 0
        await self.channel_layer.group_send(self.group_name, {
            'type': 'chat.presence', 'state': 'joined',
            'participant': self._participant_kind(), 'sender_channel': self.channel_name,
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_send(self.group_name, {
                'type': 'chat.presence', 'state': 'left',
                'participant': self._participant_kind(), 'sender_channel': self.channel_name,
            })
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data or '{}')
            if payload.get('type') == 'typing':
                now = asyncio.get_running_loop().time()
                if now - self._last_typing_at >= 0.5:
                    self._last_typing_at = now
                    await self.channel_layer.group_send(self.group_name, {
                        'type': 'chat.typing', 'is_typing': bool(payload.get('is_typing')),
                        'participant': self._participant_kind(), 'sender_channel': self.channel_name,
                    })
                return
            client_id = uuid.UUID(payload['client_message_id']) if payload.get('client_message_id') else uuid.uuid4()
            message, created = await self._save_message(
                payload.get('body', ''), client_id, bool(payload.get('internal'))
            )
        except Exception as exc:
            messages = getattr(exc, 'messages', [str(exc)])
            await self.send(text_data=json.dumps({'type': 'error', 'errors': messages}))
            return
        event = {
            'type': 'chat.message', 'id': message.id, 'body': message.body,
            'sender_type': message.sender_type, 'created_at': message.created_at.isoformat(),
            'client_message_id': str(message.client_message_id or ''), 'created': created,
        }
        if message.sender_type == 'internal':
            await self.send(text_data=json.dumps({**event, 'type': 'message'}))
        else:
            await self.channel_layer.group_send(self.group_name, event)

    async def chat_message(self, event):
        event = {**event, 'type': 'message'}
        await self.send(text_data=json.dumps(event))

    async def chat_typing(self, event):
        if event.get('sender_channel') != self.channel_name:
            await self.send(text_data=json.dumps({
                'type': 'typing', 'is_typing': event['is_typing'],
                'participant': event['participant'],
            }))

    async def chat_presence(self, event):
        if event.get('sender_channel') != self.channel_name:
            await self.send(text_data=json.dumps({
                'type': 'presence', 'state': event['state'],
                'participant': event['participant'],
            }))

    def _participant_kind(self):
        user = self.scope.get('user')
        if user and user.is_authenticated:
            return 'agent' if user.is_superuser or user.role in {'admin', 'manager', 'receptionist'} else 'guest'
        return 'visitor'

    @database_sync_to_async
    def _get_authorized_conversation(self):
        conversation = ChatConversation.objects.filter(reference=self.reference).first()
        if conversation and can_access_conversation(
            self.scope.get('user'), conversation, self.visitor_token
        ):
            return conversation
        return None

    @database_sync_to_async
    def _save_message(self, body, client_id, internal):
        return send_chat_message(
            conversation=self.conversation, actor=self.scope.get('user'),
            visitor_token=self.visitor_token, body=body,
            client_message_id=client_id, internal=internal,
        )
