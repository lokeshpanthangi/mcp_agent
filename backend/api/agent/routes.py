from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session

from api.agent.logic import (
    chat_stream,
    get_conversation_messages,
    list_conversations,
    start_conversation,
)
from api.auth.database import User
from database import get_session
from security.auth import get_current_user

router = APIRouter(tags=["agent"])


class ConversationResponse(BaseModel):
    id: int
    title: str


class MessageResponse(BaseModel):
    role: str
    content: str
    reasoning: str | None = None


class ChatRequest(BaseModel):
    conversation_id: int
    message: str


@router.post("/conversations", response_model=ConversationResponse)
def create_conversation_route(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ConversationResponse:
    conv = start_conversation(session, user.id)
    return ConversationResponse(id=conv.id, title=conv.title)


@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations_route(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ConversationResponse]:
    convs = list_conversations(session, user.id)
    return [ConversationResponse(id=c.id, title=c.title) for c in convs]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
def get_messages_route(
    conversation_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[MessageResponse]:
    messages = get_conversation_messages(session, user.id, conversation_id)
    return [
        MessageResponse(role=m.role, content=m.content, reasoning=m.reasoning) for m in messages
    ]


@router.post("/chat")
async def chat_route(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    stream = await chat_stream(session, user.id, body.conversation_id, body.message)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
