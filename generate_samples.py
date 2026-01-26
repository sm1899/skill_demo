import os
import sys
from youtube_utils import search_youtube_videos, get_transcript
from synthesis import generate_coachable_curriculum, format_manual_as_markdown
from coach import AICoach
import re

# Re-implementing a simple linkify based on the app.py logic but without gradio dependencies
def linkify_citations_for_manual(text: str, video_data: list) -> str:
    """Transforms [V# - MM:SS] into [N] and generates a Markdown reference list."""
    # Pattern matches [V1 - 12:34]
    pattern = r"\[V(\d+)\s*-\s*((?:\d{1,2}:)?\d{1,2}:\d{2})\]"
    
    citations_found = []
    
    def replace_match(match):
        video_index = int(match.group(1)) - 1
        timestamp_str = match.group(2)
        
        if video_index < 0 or video_index >= len(video_data):
            return "" # Invalid ID, remove tag
            
        citations_found.append({
            "video_index": video_index,
            "timestamp": timestamp_str
        })
        return "||CITATION_PLACEHOLDER||"

    temp_text = re.sub(pattern, replace_match, text)
    
    final_text = temp_text
    ref_list = ""
    current_count = 0
    
    for cit in citations_found:
        current_count += 1
        video = video_data[cit['video_index']]
        video_id = video.get('video_id')
        title = video.get('title', f"Video {cit['video_index']+1}")
        
        # Seconds conversion
        parts = list(map(int, cit['timestamp'].split(':')))
        seconds = parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1]
        
        url = f"https://youtube.com/watch?v={video_id}&t={seconds}"
        
        final_text = final_text.replace("||CITATION_PLACEHOLDER||", f" **[{current_count}]**", 1)
        ref_list += f"{current_count}. [{title} ({cit['timestamp']})]({url})\n"
        
    return f"{final_text}\n\n### 📚 References\n{ref_list}"

def generate_manual(topic, filename):
    print(f"\n--- Generating Manual for: {topic} ---")
    videos = search_youtube_videos(topic)
    video_data = []
    
    # Get transcripts (limit to 3 for speed)
    for v in videos[:3]:
        t = get_transcript(v['video_id'], topic=topic)
        if t:
            video_data.append({"title": v['title'], "transcript": t, "video_id": v['video_id']})
    
    if not video_data:
        print(f"No suitable videos found for {topic}")
        return

    curriculum = generate_coachable_curriculum(topic, video_data)
    md_raw = format_manual_as_markdown(curriculum)
    
    # Linkify
    final_md = linkify_citations_for_manual(md_raw, video_data)
    
    # Save
    path = os.path.join("sample_manuals", filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(final_md)
    print(f"Saved manual to {path}")

if __name__ == "__main__":
    topics = [
        ("Gamma AI Presentation Creator", "Gamma_AI.md"),
        ("Figma for Beginners", "Figma.md"),
        ("Google NotebookLM Tutorial", "NotebookLM.md")
    ]
    
    for topic, fname in topics:
        try:
            generate_manual(topic, fname)
        except Exception as e:
            print(f"Error generating {topic}: {e}")
