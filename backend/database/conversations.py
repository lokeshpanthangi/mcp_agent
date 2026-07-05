from sqlmodel import Session, select

from database.models import Conversation, Message


def create_conversation(session: Session, user_id: int) -> Conversation:
    conv = Conversation(user_id=user_id)
    session.add(conv)
    session.commit()
    session.refresh(conv)
    return conv


def list_conversations_for_user(session: Session, user_id: int) -> list[Conversation]:
    return list(session.exec(select(Conversation).where(Conversation.user_id == user_id)).all())


def get_conversation(session: Session, conversation_id: int) -> Conversation | None:
    return session.get(Conversation, conversation_id)


def list_messages(session: Session, conversation_id: int) -> list[Message]:
    return list(
        session.exec(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
        ).all()
    )


def create_message(
    session: Session,
    conversation_id: int,
    role: str,
    content: str,
    reasoning: str | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id, role=role, content=content, reasoning=reasoning
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def set_conversation_title(session: Session, conversation: Conversation, title: str) -> None:
    conversation.title = title
    session.add(conversation)
    session.commit()
