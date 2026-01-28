import gradio as gr
import os
import time
from typing import List, Tuple
from youtube_utils import search_youtube_videos, get_transcript
from synthesis import generate_coachable_curriculum, format_manual_as_markdown
from coach import AICoach
from dotenv import load_dotenv

load_dotenv()

def initialize_coach(topic: str, progress=gr.Progress()):
    if not topic:
        return None, "Please enter a topic.", gr.update(visible=False), [], "", "Enter a topic to see sources.", "⚠️ Please enter a topic."
    
    print(f"[Terminal Log] --- Starting Initialization for Topic: {topic} ---")
    try:
        progress(0, desc="🔍 Searching YouTube...")
        candidate_videos = search_youtube_videos(topic, max_results=3, candidate_pool_size=20)
        if not candidate_videos:
            return None, "No videos found.", gr.update(visible=False), [], "", "No sources.", "❌ No videos found for this topic."
        
        progress(0.1, desc=f"📽️ Evaluating {len(candidate_videos)} candidate videos...")
        scored_videos = []
        total_candidates = len(candidate_videos)
        
        for i, v in enumerate(candidate_videos):
            status = f"📄 Evaluating: {v['title'][:40]}... ({i+1}/{total_candidates})"
            progress(0.1 + (i / total_candidates) * 0.5, desc=status)
            
            transcript, score = get_transcript(v['video_id'], topic=topic, view_count=v.get('view_count', 0), position=i)
            if transcript and score > 0:
                scored_videos.append({
                    "title": v['title'],
                    "transcript": transcript,
                    "video_id": v['video_id'],
                    "score": score
                })
                print(f"[Terminal Log] ✓ {v['title'][:50]}: Score {score:.1f}")
        
        if not scored_videos:
            return None, "No valid transcripts.", gr.update(visible=False), [], "", "No data.", "❌ No valid tutorials found (failed validation)."
        
        # Sort by score (highest first) and take top 3
        scored_videos.sort(key=lambda x: x['score'], reverse=True)
        video_data = scored_videos[:3]
        
        print(f"[Terminal Log] Selected top {len(video_data)} videos:")
        for v in video_data:
            print(f"[Terminal Log]   • {v['title'][:60]} (Score: {v['score']:.1f})")
        
        # Remove score from final data structure
        for v in video_data:
            v.pop('score', None)
            
        progress(0.6, desc="🧠 Synthesizing 10-Step Guide...")
        curriculum = generate_coachable_curriculum(topic, video_data)
        
        progress(0.9, desc="🤖 Finalizing Coach...")
        coach = AICoach(topic, curriculum, video_data)
        
        # Format AND Linkify the manual
        full_manual_raw = format_manual_as_markdown(curriculum)
        full_manual_text, manual_refs, _ = linkify_citations(full_manual_raw, coach, existing_count=0)
        
        full_manual_display = f"{full_manual_text}\n\n### 📚 References\n{manual_refs}"
        
        coach.start_session()
        source_list = coach.get_source_list() # This is the generic list of videos
        
        # New format for type='messages'
        initial_history = [{"role": "assistant", "content": coach.chat_history[-1].content}]
        
        return coach, full_manual_display, gr.update(visible=True), initial_history, "", source_list, "✅ System Ready!"
    except Exception as e:
        print(f"[Terminal Log] Error: {str(e)}")
        return None, f"Error: {str(e)}", gr.update(visible=False), [], "", "Error.", f"❌ Error: {str(e)}"

def linkify_citations(text: str, coach: AICoach, existing_count: int = 0) -> Tuple[str, str, int]:
    """
    Transforms [V# - MM:SS] into [N] and generates a Markdown reference list.
    Returns: (text_with_markers, reference_list_markdown, next_count)
    """
    import re
    # Pattern matches [V1 - 12:34]
    pattern = r"\[V(\d+)\s*-\s*((?:\d{1,2}:)?\d{1,2}:\d{2})\]"
    
    citations_found = []
    
    def replace_match(match):
        nonlocal citations_found
        video_index = int(match.group(1)) - 1
        timestamp_str = match.group(2)
        
        if video_index < 0 or video_index >= len(coach.video_data):
            return "" # Invalid ID, remove tag
            
        # Store citation data
        citations_found.append({
            "video_index": video_index,
            "timestamp": timestamp_str
        })
        
        # We will replace carefully later to ensure sequential numbering
        return "||CITATION_PLACEHOLDER||"

    # First pass: identify all citations
    temp_text = re.sub(pattern, replace_match, text)
    
    # Second pass: assign numbers and build list
    final_text = temp_text
    ref_list = ""
    current_count = existing_count
    
    for cit in citations_found:
        current_count += 1
        video = coach.video_data[cit['video_index']]
        video_id = video.get('video_id')
        title = video.get('title', f"Video {cit['video_index']+1}")
        
        # Seconds conversion
        parts = list(map(int, cit['timestamp'].split(':')))
        seconds = parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1]
        
        url = f"https://youtube.com/watch?v={video_id}&t={seconds}"
        
        # Replace first placeholder
        final_text = final_text.replace("||CITATION_PLACEHOLDER||", f" **[{current_count}]**", 1)
        
        # Add to ref list
        ref_list += f"{current_count}. [{title} ({cit['timestamp']})]({url})\n"
        
    return final_text, ref_list, current_count

def respond(message: str, history: List[dict], coach: AICoach):
    if not coach:
        return history, "", "Please initialize first."
    
    answer, _ = coach.chat(message) # Ignore raw sources from coach
    
    # Linkify with numeric markers
    answer_display, references, _ = linkify_citations(answer, coach, existing_count=0)
    
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": answer_display})
    
    # Update sidebar with the references for THIS answer
    combined_sources = f"#### 📍 References for this answer:\n{references}\n"
    if not references:
        combined_sources = "No specific citations for this answer."
        
    return history, "", combined_sources

with gr.Blocks(title="AI Coach") as demo:
    coach_state = gr.State(None)
    
    with gr.Row():
        gr.Markdown("# 🎓 AI Coach: Master Any Topic")
    
    with gr.Row():
        with gr.Column(scale=4):
            topic_input = gr.Textbox(label="What do you want to learn?", placeholder="e.g. Gamma AI...")
        with gr.Column(scale=1):
            init_btn = gr.Button("🚀 Start Learning", variant="primary")
            
    status_display = gr.Markdown("**Status:** Ready.")
            
    with gr.Row():
        preset1 = gr.Button("Gamma AI", size="sm")
        preset2 = gr.Button("NotebookLM", size="sm")
        preset3 = gr.Button("Figma", size="sm")

    with gr.Row(visible=False) as main_area:
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(label="Chat", height=600)
            with gr.Row():
                msg_input = gr.Textbox(label="Message", scale=4)
                send_btn = gr.Button("Send", variant="primary", scale=1)
            clear_btn = gr.Button("🧹 Clear")
            
        with gr.Column(scale=1):
            with gr.Accordion("📋 Guide", open=True):
                manual_display = gr.Markdown()
            with gr.Accordion("🔗 Sources", open=True):
                citations_display = gr.Markdown("Sources will appear here.")

    init_outputs = [coach_state, manual_display, main_area, chatbot, msg_input, citations_display, status_display]

    init_btn.click(initialize_coach, inputs=[topic_input], outputs=init_outputs)
    preset1.click(lambda: "Gamma AI", None, topic_input).then(initialize_coach, [topic_input], init_outputs)
    preset2.click(lambda: "NotebookLM", None, topic_input).then(initialize_coach, [topic_input], init_outputs)
    preset3.click(lambda: "Figma", None, topic_input).then(initialize_coach, [topic_input], init_outputs)

    msg_input.submit(respond, [msg_input, chatbot, coach_state], [chatbot, msg_input, citations_display])
    send_btn.click(respond, [msg_input, chatbot, coach_state], [chatbot, msg_input, citations_display])
    clear_btn.click(lambda: [], None, chatbot, queue=False)

if __name__ == "__main__":
    demo.queue().launch(share=True, theme=gr.themes.Soft())
