import os
import sys
from youtube_utils import search_youtube_videos, get_transcript
from synthesis import generate_coachable_curriculum, format_manual_as_markdown
from coach import AICoach
from dotenv import load_dotenv

load_dotenv()

def run_pipeline(topic):
    print(f"--- Starting Pipeline for Topic: {topic} ---")
    
    # 1. Search for videos
    print("Searching for top tutorial videos...")
    videos = search_youtube_videos(topic)
    if not videos:
        print("No videos found.")
        return
    
    # 2. Extract transcripts
    print(f"Extracting transcripts for {len(videos)} videos...")
    video_data = []
    for v in videos:
        print(f"Processing: {v['title']}")
        transcript = get_transcript(v['video_id'])
        if transcript:
            video_data.append({
                "title": v['title'],
                "transcript": transcript,
                "video_id": v['video_id']
            })
    
    if not video_data:
        print("Could not retrieve any transcripts.")
        return
    
    # 3. Synthesize manual (Using Map-Reduce for long content)
    print("Synthesizing instruction manual via Gemini 1.5 Map-Reduce...")
    try:
        manual = generate_instruction_manual_map_reduce(topic, video_data)
        
        # 4. Format and Save
        markdown_content = format_manual_as_markdown(manual)
        
        output_file = f"{topic.lower().replace(' ', '_')}_manual.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        
        print(f"Success! Manual saved to: {output_file}")
        return output_file
        
    except Exception as e:
        print(f"Error during synthesis: {e}")

def run_coach_pipeline(topic):
    print(f"--- Launching AI Coach for: {topic} ---")
    videos = search_youtube_videos(topic)
    video_data = []
    for v in videos:
        t = get_transcript(v['video_id'])
        if t:
            video_data.append({"title": v['title'], "transcript": t})
            
    if not video_data:
        print("No knowledge base found.")
        return

    curriculum = generate_coachable_curriculum(topic, video_data)
    transcripts = [d['transcript'] for d in video_data]
    
    coach = AICoach(topic, curriculum, transcripts)
    print("\n" + coach.start_session() + "\n")
    
    while True:
        try:
            user_msg = input("You: ")
            if user_msg.lower() in ['exit', 'quit', 'bye']:
                print("Coach: Goodbye! Keep practicing!")
                break
            
            response = coach.chat(user_msg)
            print(f"\nCoach: {response}\n")
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    mode = "coach" # Defaulting to the new coach mode
    topic = "Gamma AI"
    
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
        
    run_coach_pipeline(topic)
