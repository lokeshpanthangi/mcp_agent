from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.db import get_session
from app.models import Conversation, Message, User

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationResponse(BaseModel):
    id: int
    title: str


class MessageResponse(BaseModel):
    role: str
    content: str


@router.post("", response_model=ConversationResponse)
def create_conversation(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ConversationResponse:
    conv = Conversation(user_id=user.id)
    session.add(conv)
    session.commit()
    session.refresh(conv)
    return ConversationResponse(id=conv.id, title=conv.title)


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ConversationResponse]:
    convs = session.exec(select(Conversation).where(Conversation.user_id == user.id)).all()
    return [ConversationResponse(id=c.id, title=c.title) for c in convs]


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def get_messages(
    conversation_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[MessageResponse]:
    conv = session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    messages = session.exec(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    ).all()
    return [MessageResponse(role=m.role, content=m.content) for m in messages]
