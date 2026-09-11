from typing import Dict, Any, Optional
from support.models import ChatSession, ChatMessage
from support.services.faq import FAQService
from support.services.ticket import TicketService
from support.utils.llm_client import LLMClient
from django.contrib.auth import get_user_model

User = get_user_model()


class AIChatService:
    @staticmethod
    def get_or_create_session(
        session_id_str: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        user: Any = None,
        organization_id: Optional[int] = None
    ) -> ChatSession:
        """
        Retrieves or creates a ChatSession based on UUID string or Telegram chat ID.
        """
        # Resolve organization_id from user if not passed
        org_id = organization_id
        if not org_id and user and user.is_authenticated:
            org_id = getattr(user, 'organization_id', None)

        if not org_id:
            # Absolute fallback to first org for safe default, or raise error
            from organizations.models import Organization
            first_org = Organization.objects.first()
            org_id = first_org.id if first_org else 1

        if telegram_chat_id:
            session = ChatSession.objects.filter(
                telegram_chat_id=telegram_chat_id,
                organization_id=org_id
            ).first()
            if not session:
                session = ChatSession.objects.create(
                    telegram_chat_id=telegram_chat_id,
                    organization_id=org_id,
                    user=user if user and user.is_authenticated else None
                )
            return session

        if session_id_str:
            try:
                return ChatSession.objects.get(session_id=session_id_str, organization_id=org_id)
            except ChatSession.DoesNotExist:
                pass

        # Create new session if not found or not specified
        return ChatSession.objects.create(
            user=user if user and user.is_authenticated else None,
            organization_id=org_id
        )

    @classmethod
    def handle_chat_message(
        cls,
        session_id_str: Optional[str],
        message: str,
        user: Any = None,
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Main AI Chat pipeline:
        1. Fetch/Create Session
        2. Check FAQ matching
        3. Fallback to LLM if FAQ matching confidence is low
        4. Auto-generate support ticket if LLM confidence is low
        5. Save message logs
        """
        session = cls.get_or_create_session(
            session_id_str=session_id_str,
            user=user,
            organization_id=organization_id
        )

        org_id = session.organization_id

        # 1. Save user message to database
        ChatMessage.objects.create(
            session=session,
            sender='user',
            content=message
        )

        # 2. Check FAQ
        faq_item, faq_score = FAQService.search_matching_faq(message, org_id)
        if faq_item:
            answer = faq_item.answer
            
            # Save AI message referencing the matched FAQ
            ChatMessage.objects.create(
                session=session,
                sender='ai',
                content=answer,
                confidence_score=faq_score,
                matched_faq=faq_item
            )
            
            return {
                "session_id": str(session.session_id),
                "answer": answer,
                "confidence": float(faq_score),
                "source": "faq",
                "ticket_created": False,
                "ticket_id": None
            }

        # 3. Call LLM Client
        # Load conversation history for context
        history_msgs = ChatMessage.objects.filter(session=session).order_by('-created_at')[:10]
        history = [
            {"sender": msg.sender, "content": msg.content}
            for msg in reversed(history_msgs)
        ]

        ai_answer, confidence = LLMClient.ask_ai(message, history)

        # 4. Save AI response
        ChatMessage.objects.create(
            session=session,
            sender='ai',
            content=ai_answer,
            confidence_score=confidence
        )

        # 5. Check if we need to auto-create a ticket (Confidence low e.g. < 0.3)
        ticket_created = False
        ticket_id = None
        
        # Also check for explicit operator request in query
        msg_lower = message.lower()
        needs_ticket = (confidence < 0.3) or any(w in msg_lower for w in ('operator', 'bog\'lanish', 'inson', 'xodim', 'yordam berolmadi'))

        if needs_ticket:
            ticket = TicketService.auto_create_ticket(session, description=message)
            ticket_created = True
            ticket_id = ticket.id
            ai_answer += f"\n\n[Tizim]: Sizning so'rovingiz bo'yicha operatorlarimiz uchun yordam chiptasi ochildi (Chipta #{ticket.id}). Tez orada xodimlarimiz siz bilan bog'lanishadi."

        return {
            "session_id": str(session.session_id),
            "answer": ai_answer,
            "confidence": float(confidence),
            "source": "llm",
            "ticket_created": ticket_created,
            "ticket_id": ticket_id
        }

    @classmethod
    def handle_telegram_chat(cls, chat_id: str, message: str, organization_id: int) -> str:
        """
        Coordinates AI Chat for incoming Telegram updates.
        """
        session = cls.get_or_create_session(
            telegram_chat_id=chat_id,
            organization_id=organization_id
        )
        
        # Route to common chat pipeline
        res = cls.handle_chat_message(
            session_id_str=str(session.session_id),
            message=message,
            organization_id=organization_id
        )
        
        return res["answer"]
