import os
from typing import List
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from dotenv import load_dotenv

load_dotenv()

class InstructionStep(BaseModel):
    step_number: int = Field(description="The chronological step number (1-10)")
    title: str = Field(description="The title of this tutorial step")
    tutorial_content: str = Field(description="A detailed, beginner-friendly paragraph (3-5 sentences) explaining the 'how' and 'why' of this step, written in a tutorial style.")

class CoachableCurriculum(BaseModel):
    topic: str
    target_audience: str = "Complete Beginner"
    steps: List[InstructionStep]

def extract_milestones(transcript: str, video_title: str):
    """Extracts key learning milestones from a single transcript, excluding promotions."""
    print(f"[Terminal Log] Extracting milestones from: {video_title}...")
    llm = ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview", 
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        safety_settings={
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }
    )
    parser = PydanticOutputParser(pydantic_object=VideoMilestones)
    
    prompt = ChatPromptTemplate.from_template(
        "Identify the primary learning milestones in this tutorial transcript for '{video_title}'.\n"
        "CRITICAL: Exclude any promotional content, sponsor segments, channel intros/outros, or irrelevant 'housekeeping' talk.\n"
        "Focus ONLY on atomic educational concepts that a beginner must learn to master the topic.\n"
        "TRANSCRIPT:\n{transcript}\n"
        "{format_instructions}"
    )
    
    chain = prompt | llm | parser
    return chain.invoke({
        "video_title": video_title,
        "transcript": transcript[:40000], 
        "format_instructions": parser.get_format_instructions()
    })

class Milestone(BaseModel):
    topic: str = Field(description="The specific concept or feature being taught")
    timecode: str = Field(description="Approximate timestamp in the video")

class VideoMilestones(BaseModel):
    video_title: str
    milestones: List[Milestone]

def generate_coachable_curriculum(topic: str, video_data: List[dict]):
    """Generates a structured 10-step curriculum by cross-referencing multiple sources."""
    print(f"[Terminal Log] Synthesizing 10-step curriculum for: {topic}...")
    
    # Map Phase (Milestone Extraction)
    all_milestones = []
    for data in video_data:
        milestones = extract_milestones(data['transcript'], data['title'])
        all_milestones.append(milestones)
    
    # Reduce Phase (Curriculum Synthesis)
    llm = ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview", 
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        safety_settings={
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }
    )
    parser = PydanticOutputParser(pydantic_object=CoachableCurriculum)
    
    # Create Source Mapping (V1, V2...) to match AICoach logic
    source_mapping = ""
    for i, data in enumerate(video_data):
        source_mapping += f"V{i+1}: {data['title']}\n"
    
    prompt = ChatPromptTemplate.from_template(
        "You are an expert tutor writing a complete, beginner-friendly online course for '{topic}'.\n"
        "You have been provided with milestones from multiple tutorial videos (Sources V1, V2, etc.). Your task is to:\n"
        "1. CROSS-REFERENCE these sources. Identify common themes and design a cohesive 10-step curriculum.\n"
        "2. CONTENTS: For each step, write a 'tutorial_content' paragraph (3-5 sentences).\n"
        "3. CITATIONS: You MUST cite your sources in the 'tutorial_content' using the format `[V# - MM:SS]`.\n"
        "   - Example: \"First, create an account [V1 - 01:30]. Then click Dashboard [V2 - 02:45].\"\n"
        "   - FORBIDDEN: Do NOT combine citations like `[V1 - 00:00, V2 - 00:00]`. Use `[V1 - 00:00] [V2 - 00:00]` instead.\n"
        "   - Every specific instruction must have a citation.\n"
        "4. Exactly 10 steps.\n\n"
        "### AVAILABLE SOURCES:\n{source_mapping}\n\n"
        "MILESTONES BY VIDEO:\n{milestone_data}\n"
        "{format_instructions}"
    )
    
    milestone_text = ""
    for i, vm in enumerate(all_milestones):
        milestone_text += f"\nVideo V{i+1}: {vm.video_title}\n"
        for m in vm.milestones:
            milestone_text += f"- {m.timecode}: {m.topic}\n"
    
    print(f"[Terminal Log] Synthesis Input Length: {len(milestone_text)} chars")
            
    chain = prompt | llm 
    try:
        raw_output = chain.invoke({
            "topic": topic,
            "source_mapping": source_mapping,
            "milestone_data": milestone_text,
            "format_instructions": parser.get_format_instructions()
        })
        
        # Log a snippet of the raw output for debugging
        print(f"[Terminal Log] Synthesis Raw Output Header: {str(raw_output.content)[:200]}...")
        
        return parser.parse(raw_output.content)
    except Exception as e:
        print(f"[Terminal Log] Synthesis Error: {str(e)}")
        raise e

def format_manual_as_markdown(curriculum: CoachableCurriculum):
    """Formats the CoachableCurriculum object as a clean tutorial manual."""
    md = f"# Tutorial: {curriculum.topic} - Step-by-Step Guide\n\n"
    for step in curriculum.steps:
        md += f"### {step.step_number}. {step.title}\n"
        md += f"{step.tutorial_content}\n\n"
    return md
