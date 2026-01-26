import os
import subprocess
import glob
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

def search_youtube_videos(query, max_results=3):
    """Searches for tutorial videos on YouTube, excluding Shorts."""
    print(f"[Terminal Log] Searching YouTube for: {query}...")
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    
    # We add videoDuration='medium' or 'long' to avoid Shorts (< 4 mins or > 20 mins)
    # Actually 'any' is default. Let's use videoDuration='medium' or 'long'?
    # Or just 'short' is < 4 mins. Shorts are < 1 min.
    # To be safe, we'll fetch more and filter by duration if part='contentDetails' is used.
    # But for now, let's use videoDuration='medium' (4-20 mins) which is ideal for tutorials.
    
    request = youtube.search().list(
        q=f"'{query}' tutorial beginner guide -zapier -automation-only", # Strict quotes and negative matches
        part="snippet",
        maxResults=max_results + 7, # Fetch even more to filter better
        type="video",
        order="viewCount",
        videoDuration="medium", 
        publishedAfter="2024-01-01T00:00:00Z"
    )
    response = request.execute()
    
    videos = []
    topic_words = query.lower().split()
    for item in response.get("items", []):
        title = item["snippet"]["title"].lower()
        
        # Stricter relevance check on title
        if not any(word in title for word in topic_words):
            print(f"[Terminal Log] Skipping irrelevant result: {item['snippet']['title']}")
            continue
            
        if "short" in title and "tutorial" not in title:
            continue
            
        videos.append({
            "video_id": item["id"]["videoId"],
            "title": item["snippet"]["title"],
            "published_at": item["snippet"]["publishedAt"]
        })
        if len(videos) >= max_results:
            break
            
    print(f"[Terminal Log] Found {len(videos)} suitable tutorial videos.")
    return videos

def validate_transcript(content: str, topic: str = None) -> bool:
    """Validates if the transcript content is likely to be a useful tutorial for the specific topic."""
    if not content or len(content) < 500: # Increased minimum length
        return False
    
    content_lower = content.lower()
    
    # Topic relevance check
    if topic:
        topic_keywords = topic.lower().split()
        # Must contain at least one word from the topic more than once
        # to ensure it's not just a passing mention.
        if not any(content_lower.count(k) > 1 for k in topic_keywords):
            return False

    # Check for common "dead" transcript indicators
    low_content_indicators = ["[Music]", "[Laughter]", "[Applause]", "inaudible", "foreign"]
    
    # If more than 2% of the transcript is just music/inaudible tags, it's probably bad
    tag_count = sum(content_lower.count(tag.lower()) for tag in low_content_indicators)
    if tag_count > (len(content_lower) / 50): 
         words = set(content_lower.split())
         if len(words) < 50:
             return False
             
    return True

def vtt_to_clean_text(vtt_content: str) -> str:
    """Converts raw VTT content into a clean, LLM-friendly timestamped transcript."""
    lines = vtt_content.splitlines()
    clean_lines = []
    
    # Simple state machine to catch timestamps and text
    import re
    timestamp_pattern = re.compile(r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})")
    
    last_text = ""
    for line in lines:
        line = line.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
            
        ts_match = timestamp_pattern.match(line)
        if ts_match:
            # Extract just M:S or H:M:S
            start_ts = ts_match.group(1).split('.')[0]
            if start_ts.startswith("00:"): 
                start_ts = start_ts[3:] # Convert 00:01:23 to 01:23
            clean_lines.append(f"[{start_ts}]")
        else:
            # Remove HTML tags and repetitive auto-generated lines
            text = re.sub(r'<[^>]+>', '', line).strip()
            if text and text != last_text:
                if clean_lines and clean_lines[-1].startswith("["):
                    clean_lines[-1] = f"{clean_lines[-1]} {text}"
                else:
                    clean_lines.append(text)
                last_text = text
                
    return "\n".join(clean_lines)

def get_transcript(video_id, topic: str = None):
    """Retrieves, cleans, and validates the transcript using yt-dlp."""
    output_filename = f"temp_{video_id}"
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        # Run yt-dlp to get auto-generated subtitles
        subprocess.run([
            "yt-dlp", "--write-auto-subs", "--sub-lang", "en", 
            "--skip-download", "--output", output_filename, url
        ], check=True, capture_output=True)
        
        files = glob.glob(f"{output_filename}*")
        if not files:
            print(f"[Terminal Log] No subtitle files for {video_id}")
            return None
        
        transcript_file = files[0]
        with open(transcript_file, "r", encoding="utf-8") as f:
            raw_content = f.read()
        
        # Clean up files
        for f in files:
            os.remove(f)
            
        # Transform VTT to clean timestamped text
        content = vtt_to_clean_text(raw_content)
            
        if validate_transcript(content, topic):
            return content
        else:
            print(f"[Terminal Log] Transcript for {video_id} failed validation (low quality or irrelevant).")
            return None
            
    except Exception as e:
        print(f"[Terminal Log] Error retrieving transcript via yt-dlp for {video_id}: {e}")
        return None
