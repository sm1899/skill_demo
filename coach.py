import os
import re
from typing import List, Tuple
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from synthesis import CoachableCurriculum, InstructionStep, format_manual_as_markdown
from youtube_utils import search_youtube_videos, get_transcript
from dotenv import load_dotenv

load_dotenv()

class AICoach:
    def __init__(self, topic: str, curriculum: CoachableCurriculum, video_data: List[dict]):
        self.topic = topic
        self.curriculum = curriculum
        self.video_data = video_data
        self.transcripts = "\n\n".join([f"VIDEO: {v['title']}\n{v['transcript']}" for v in video_data])
        self.current_step_index = 0
        self.chat_history = []
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-3-flash-preview", 
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            safety_settings={
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
            }
        )
        
        self.system_prompt = (
            f"You are a supportive and expert AI Coach teaching a student about '{topic}'.\n"
            f"You have access to tutorial transcripts which serve as your knowledge base.\n"
            f"KNOWLEDGE BASE:\n{self.transcripts}\n\n"
            f"CURRICULUM:\n{self.curriculum}\n\n"
            "COACHING RULES:\n"
            "1. Focus on the CURRENT STEP. Do not move to the next step unless the user is ready.\n"
            "2. Be concise and beginner-friendly.\n"
            "3. SOCIAL SKILLS: If the user says 'thank you', 'ok', or 'cool', acknowledge it warmly (e.g., 'You're welcome!'). Do NOT dump the full lesson content immediately unless they explicitly ask to start or say they are ready.\n"
            "4. Provide clear, actionable advice that helps the user complete the step.\n"
            "5. After explaining a concept, ask the user if they have questions or if they are ready to move to the next step."
        )

    def get_source_list(self) -> str:
        """Returns a formatted Markdown string of all source videos."""
        md = "### 📚 Reference Videos\n"
        for i, v in enumerate(self.video_data):
            url = f"https://youtube.com/watch?v={v.get('video_id', '')}"
            md += f"{i+1}. [{v['title']}]({url})\n"
        return md

    def get_current_step(self) -> InstructionStep:
        if self.current_step_index < len(self.curriculum.steps):
            return self.curriculum.steps[self.current_step_index]
        return None

    def start_session(self):
        full_manual = format_manual_as_markdown(self.curriculum)
        greeting = (
            f"Hello! I'm your AI Coach for {self.topic}. "
            "I've analyzed the best tutorials and prepared this complete 10-step guide for you:\n\n"
            "Take a look at the 'Step-by-Step Guide' tab to see the full path! What would you like to start with, or do you have any questions about this path?"
        )
        self.chat_history.append(AIMessage(content="[Full Manual Displayed]"))
        self.chat_history.append(AIMessage(content=greeting))
        return greeting

    def _get_citations(self, draft_answer: str) -> str:
        """The 'Citation Agent': Ground the draft answer in the transcripts and insert [V# - MM:SS] tags."""
        
        # Create a simplified list for the agent: "V1: Full encoded title\n V2: ..."
        source_mapping = ""
        for i, v in enumerate(self.video_data):
            source_mapping += f"V{i+1}: {v['title']}\n"
            
        grounding_prompt = (
            "### CITATION AGENT TASK\n"
            "You are a Citation Agent. I will provide a DRAFT ANSWER and a set of TRANSCRIPTS (labeled V1, V2, etc.).\n"
            "Your job is to insert simple citation tags `[V# - MM:SS]` into the draft answer to prove the claims.\n\n"
            "### INSTRUCTIONS:\n"
            "1. USE THIS FORMAT: `[V1 - 02:30]`. Use `[V1 - 02:30] [V2 - 14:05]` for multiple sources.\n"
            "2. FORBIDDEN: Do NOT combine citations like `[V1 - 00:00, V2 - 00:00]`. Always use separate brackets.\n"
            "3. PLACEMENT: Insert a citation AFTER every specific instruction or factual claim.\n"
            "4. ACCURACY: Use the timestamps exactly as they appear in the transcripts.\n"
            "5. NO NEW CONTENT: Do not rewrite the draft, just insert the tags.\n\n"
            "### AVAILABLE SOURCES:\n"
            f"{source_mapping}\n\n"
            "### TRANSCRIPTS:\n"
            f"{self.transcripts}\n\n"
            "### DRAFT ANSWER:\n"
            f"{draft_answer}\n\n"
            "### FINAL GROUNDED ANSWER:"
        )
        
        messages = [HumanMessage(content=grounding_prompt)]
        response = self.llm.invoke(messages)
        content = response.content
        print(f"[Terminal Log] 🔵 Stage 2 OUTPUT:\n{content}\n---")
        return content

    def chat(self, user_input: str) -> Tuple[str, str]:
        print(f"\n[Terminal Log] >>> CHAT INVOCATION: '{user_input}'")
        self.chat_history.append(HumanMessage(content=user_input))
        
        current_step = self.get_current_step()
        
        # Step 1: Response Agent (Drafting)
        print("[Terminal Log] 🟢 Stage 1: Drafting response...")
        context_prompt = (
            f"\n\nCURRENT STATUS: The student is on Step {self.current_step_index + 1}: {current_step.title if current_step else 'Finished'}.\n"
            "Generate a helpful, instructional response based on the Knowledge Base. Do NOT add citations yourself."
        )
        
        messages = [SystemMessage(content=self.system_prompt + context_prompt)] + self.chat_history
        draft_response = self.llm.invoke(messages)
        draft_content = draft_response.content
        print(f"[Terminal Log] 📜 Draft Length: {len(draft_content)} chars")
        
        # Step 2: Citation Agent (Grounding)
        print("[Terminal Log] 🔵 Stage 2: Grounding & Citing...")
        final_answer_with_citations = self._get_citations(draft_content)
        print(f"[Terminal Log] ✅ Grounded Result Preview: {final_answer_with_citations[:200]}...")
        
        # Step 3: Source List
        print("[Terminal Log] 🟡 Stage 3: Summary Citations...")
        sources_prompt = (
            "Summarize the specific videos and timecodes used in the following answer as a short bulleted list.\n"
            f"ANSWER: {final_answer_with_citations}"
        )
        # Using HumanMessage to prevent empty content error
        sources_response = self.llm.invoke([HumanMessage(content=sources_prompt)])
        sources = sources_response.content
        
        self.chat_history.append(AIMessage(content=draft_content))
        
        if "next step" in user_input.lower() or "ready" in user_input.lower():
            if self.current_step_index < len(self.curriculum.steps) - 1:
                self.current_step_index += 1
        
        return final_answer_with_citations, sources

def run_interactive_coach(topic: str):
    from youtube_utils import search_youtube_videos, get_transcript
    from synthesis import generate_coachable_curriculum
    
    videos = search_youtube_videos(topic)
    video_data = []
    for v in videos:
        t = get_transcript(v['video_id'], topic=topic)
        if t:
            video_data.append({"title": v['title'], "transcript": t, "video_id": v['video_id']})
            
    curriculum = generate_coachable_curriculum(topic, video_data)
    coach = AICoach(topic, curriculum, video_data)
    print("\n" + coach.start_session() + "\n")
    
    while True:
        user_msg = input("You: ")
        if user_msg.lower() in ['exit', 'quit', 'bye']:
            break
        answer, sources = coach.chat(user_msg)
        print(f"\nCoach: {answer}\n\nSources:\n{sources}\n")

if __name__ == "__main__":
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else "Gamma AI"
    run_interactive_coach(topic)
