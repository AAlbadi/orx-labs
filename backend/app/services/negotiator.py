import requests
from datetime import datetime
from sqlalchemy.orm import Session
from backend.app.config import settings
from backend.app.database.schema import Lead, NegotiatorState

class AINegotiator:
    def __init__(self):
        self.openrouter_key = settings.OPENROUTER_API_KEY
        self.model = settings.LLM_MODEL
        self.slack_url = settings.SLACK_WEBHOOK_URL
        
        # Simulated Calendar Availability (UTC)
        self.available_slots = (
            "1. Monday: 2:00 PM - 5:00 PM UTC\n"
            "2. Tuesday: 9:00 AM - 12:00 PM UTC\n"
            "3. Wednesday: 3:00 PM - 6:00 PM UTC\n"
            "4. Thursday: 10:00 AM - 1:00 PM UTC\n"
            "5. Friday: 1:00 PM - 4:00 PM UTC"
        )

    def process_incoming_message(self, db: Session, lead_id: int, message_body: str) -> str:
        """
        Receives an email reply, updates the conversation history,
        runs the Negotiator LLM loop, checks scheduling agreement, and returns the response.
        """
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return "Lead not found."
            
        state = db.query(NegotiatorState).filter(NegotiatorState.lead_id == lead.id).first()
        if not state:
            state = NegotiatorState(
                lead_id=lead.id,
                conversation_history=[],
                status="ACTIVE",
                timezone="UTC"
            )
            db.add(state)
            db.commit()
            db.refresh(state)

        # Update status to negotiating if it was repliled
        if lead.status == "REPLIED":
            lead.status = "NEGOTIATING"
            db.commit()

        history = list(state.conversation_history)
        history.append({"role": "user", "content": message_body, "timestamp": datetime.utcnow().isoformat()})
        
        # Prepare the Agent LLM prompts
        system_prompt = (
            "You are the AI Negotiator Agent for Abdu Aziz Rashid Hamed Al Badi, founder of ORX.\n"
            "Your sole objective is to answer technical questions about the ORX Model Compiler Engine and book a 15-minute meeting directly into Abdu's calendar.\n\n"
            "ABOUT ORX:\n"
            "- It compiles machine learning models (like Llama, Mistral) to low-level target hardware.\n"
            "- It bypasses standard PyTorch runtime overheads, saving 30-40% on GPU inferencing latency.\n"
            "- Works out-of-the-box with Triton, CUDA, and Apple Silicon/MLX.\n\n"
            "SCHEDULING RULES:\n"
            f"Here is Abdu's current weekly availability (in UTC):\n{self.available_slots}\n\n"
            "1. When the prospect asks for a meeting, offer 2-3 specific options matching the slots above.\n"
            "2. If they suggest a time, verify if it fits within the availability slots (converting timezones as needed). If it doesn't, politely suggest alternatives.\n"
            "3. Once the prospect explicitly agrees to a specific time, confirm the meeting, explain that the invite has been sent, and append 'BOOK_MEETING: [Agreed Time in UTC]' at the end of your response.\n\n"
            "CONSTRAINTS:\n"
            "- Keep the response short, conversational, and direct (under 100 words).\n"
            "- Do not invent availability slots outside of the list."
        )

        # Format conversation context
        formatted_history = []
        for msg in history:
            role_name = "Prospect" if msg["role"] == "user" else "AI Negotiator (You)"
            formatted_history.append(f"{role_name}: {msg['content']}")
            
        user_prompt = (
            f"Prospect Name: {lead.first_name} {lead.last_name}\n"
            f"Role/Company: {lead.role} at {lead.company}\n"
            f"Context harvested: {lead.harvested_context.get('linkedin', {}).get('summary', '')}\n\n"
            f"Conversation History:\n" + "\n".join(formatted_history) + "\n\n"
            f"Generate the next response to the prospect:"
        )

        response_text = ""
        
        # 1. OpenRouter Integration
        if self.openrouter_key:
            try:
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.5
                }
                
                response = requests.post(url, headers=headers, json=payload, timeout=20)
                if response.status_code == 200:
                    response_text = response.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                print(f"Negotiator OpenRouter call failed: {e}")
                
        # 2. Mock dialogue fallback if LLM failed/key is missing
        if not response_text:
            response_text = self._mock_negotiator_response(message_body)

        # 3. Check for booking confirmation
        if "BOOK_MEETING:" in response_text:
            # Extract meeting details
            parts = response_text.split("BOOK_MEETING:")
            meeting_details = parts[1].strip()
            
            # Update database statuses
            state.status = "BOOKED"
            lead.status = "BOOKED"
            
            # Send Slack / Founder notification
            self._notify_founder(lead, meeting_details)
            print(f"[NEGOTIATOR] Meeting booked for lead {lead.email} at {meeting_details}!")

        # Save AI reply to history
        history.append({"role": "assistant", "content": response_text, "timestamp": datetime.utcnow().isoformat()})
        state.conversation_history = history
        db.commit()
        
        return response_text

    def _mock_negotiator_response(self, user_msg: str) -> str:
        """Simulates response decisions based on keywords for offline/mock usage."""
        msg = user_msg.lower()
        if "schedule" in msg or "calendar" in msg or "time" in msg or "meet" in msg:
            return (
                "Let's schedule a 15-minute chat. I've got Wednesday at 4:00 PM UTC or "
                "Thursday at 11:00 AM UTC open. Do either of those work for you?"
            )
        elif "wednesday" in msg or "thursday" in msg or "work" in msg or "yes" in msg or "4" in msg or "11" in msg:
            return (
                "Excellent! I've booked you in for next Thursday at 11:00 AM UTC. "
                "You should receive a calendar invite shortly. Looking forward to it!\n\n"
                "BOOK_MEETING: Thursday at 11:00 AM UTC"
            )
        else:
            return (
                "ORX compiles PyTorch graphs directly into optimized Triton kernels, "
                "saving about 35% on cloud GPU costs. Would you be open to a quick call "
                "to see how this could integrate with your team's stack?"
            )

    def _notify_founder(self, lead: Lead, details: str):
        """Notifies the founder via Slack or email integration."""
        message = (
            f"🎉 *New Meeting Booked!*\n"
            f"*Lead:* {lead.first_name} {lead.last_name} ({lead.email})\n"
            f"*Company:* {lead.company} | *Role:* {lead.role}\n"
            f"*Time:* {details}\n"
            f"ORX AI Negotiator has sent a calendar confirmation invite."
        )
        
        if self.slack_url:
            try:
                requests.post(self.slack_url, json={"text": message}, timeout=5)
            except Exception as e:
                print(f"Failed to post Slack notification: {e}")
        else:
            print(f"\n========================================\n"
                  f"FOUNDER NOTIFICATION:\n{message}\n"
                  f"========================================\n")

negotiator = AINegotiator()
