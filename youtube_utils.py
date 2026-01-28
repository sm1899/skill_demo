import os
import subprocess
import glob
from googleapiclient.discovery import build
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

def generate_search_query_with_agent(raw_topic: str) -> str:
    """
    Lightweight search-query agent using Gemini to transform a natural-language
    user request into a focused YouTube tutorial query.

    Examples:
      - "hey can you teach me how to use claude cowork?" -> "claude cowork tutorial for beginners"
      - "I want to learn Gamma AI from scratch" -> "gamma ai beginner tutorial"
    """
    # Fallback: if no topic, return empty string
    if not raw_topic or not raw_topic.strip():
        return ""

    try:
        system_prompt = (
            "You are a search query assistant for YouTube.\n"
            "Your job is to convert a casual user question into a short, focused search query "
            "that will find high-quality tutorial videos for learning that skill from scratch.\n\n"
            "Rules:\n"
            "- Keep it under 8 words.\n"
            "- Remove filler like 'hey', 'can you', 'please', 'teach me', 'how do I', etc.\n"
            "- Include the key product / tool / concept name.\n"
            "- Add words like 'tutorial', 'guide', or 'for beginners' if helpful.\n"
            "- Do NOT answer the question. Only return the search query.\n"
            "- Output only the search query text, no quotes, no extra explanation."
        )

        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatGoogleGenerativeAI(
            model="gemini-3-flash-preview",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            safety_settings={
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
            },
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"User question: {raw_topic}"),
        ]
        response = llm.invoke(messages)
        # Handle both string and list-style outputs
        content = response.content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    parts.append(part["text"])
                elif isinstance(part, str):
                    parts.append(part)
            content = "".join(parts)

        query = str(content).strip()
        # Simple safety fallback: if the model returns something empty, reuse the raw topic
        if not query:
            return raw_topic.strip()
        return query
    except Exception as e:
        print(f"[Terminal Log] Search Agent Error, falling back to raw topic: {e}")
        return raw_topic.strip()

def search_youtube_videos(query, max_results=3, candidate_pool_size=20):
    """Searches for tutorial videos on YouTube, returning a larger candidate pool for evaluation."""
    search_query = generate_search_query_with_agent(query)
    print(f"[Terminal Log] Searching YouTube for: {query}...")
    print(f"[Terminal Log] Search Agent query: {search_query}")
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    
    request = youtube.search().list(
        q=f"{search_query}",
        part="snippet",
        maxResults=candidate_pool_size,
        type="video",
        order="relevance",  # prioritize relevance instead of pure popularity
        videoDuration="medium", 
        publishedAfter="2024-01-01T00:00:00Z"
    )
    response = request.execute()
    
    videos = []
    topic_words = query.lower().split()
    for item in response.get("items", []):
        title = item["snippet"]["title"].lower()
        
        # Basic relevance check on title
        if not any(word in title for word in topic_words):
            print(f"[Terminal Log] Skipping irrelevant result: {item['snippet']['title']}")
            continue
            
        if "short" in title and "tutorial" not in title:
            continue
        
        # Note: View count not available in search results, will use 0
        # Videos are already ordered by viewCount, so higher views come first
            
        videos.append({
            "video_id": item["id"]["videoId"],
            "title": item["snippet"]["title"],
            "published_at": item["snippet"]["publishedAt"],
            "view_count": 0  # Not available from search API, but videos are sorted by viewCount
        })
            
    print(f"[Terminal Log] Found {len(videos)} candidate videos for evaluation.")
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

def score_transcript(content: str, topic: str = None, view_count: int = 0, position: int = 0) -> float:
    """Scores a transcript based on quality, relevance, and video popularity. Returns 0 if invalid."""
    if not content or len(content) < 500:
        return 0.0
    
    content_lower = content.lower()
    score = 0.0
    
    # Base score from transcript length (longer = better, up to a point)
    length_score = min(len(content) / 5000.0, 1.0) * 30  # Max 30 points
    score += length_score
    
    # Topic relevance score (most important)
    if topic:
        topic_keywords = topic.lower().split()
        keyword_matches = sum(content_lower.count(k) for k in topic_keywords)
        relevance_score = min(keyword_matches / 20.0, 1.0) * 40  # Max 40 points
        score += relevance_score
    
    # Quality score (fewer low-content indicators = better)
    low_content_indicators = ["[Music]", "[Laughter]", "[Applause]", "inaudible", "foreign"]
    tag_count = sum(content_lower.count(tag.lower()) for tag in low_content_indicators)
    tag_ratio = tag_count / max(len(content_lower) / 50, 1)
    quality_score = max(0, (1.0 - min(tag_ratio, 1.0))) * 20  # Max 20 points
    score += quality_score
    
    # Vocabulary diversity score
    words = set(content_lower.split())
    vocab_score = min(len(words) / 200.0, 1.0) * 10  # Max 10 points
    score += vocab_score
    
    # Position bonus (earlier in search results = more popular, max 10 points)
    # First video gets 10, second gets 8, third gets 6, etc.
    if position < 10:
        position_score = max(0, 10 - position * 0.5)
        score += position_score
    
    return score

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

def get_transcript(video_id, topic: str = None, view_count: int = 0, position: int = 0):
    """Retrieves, cleans, and validates the transcript using yt-dlp. Returns (transcript, score) or (None, 0)."""
    output_filename = f"temp_{video_id}"
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        # Run yt-dlp to get auto-generated subtitles
        result = subprocess.run([
            "yt-dlp", "--write-auto-subs", "--sub-lang", "en", 
            "--skip-download", "--output", output_filename, url
        ], check=True, capture_output=True, text=True)
        
        files = glob.glob(f"{output_filename}*")
        if not files:
            print(f"[Terminal Log] No subtitle files for {video_id}")
            return None, 0.0
        
        transcript_file = files[0]
        with open(transcript_file, "r", encoding="utf-8") as f:
            raw_content = f.read()
        
        # Clean up files
        for f in files:
            os.remove(f)
            
        # Transform VTT to clean timestamped text
        content = vtt_to_clean_text(raw_content)
        
        # Score the transcript
        score = score_transcript(content, topic, view_count, position)
        
        if score > 0:  # Valid transcript
            return content, score
        else:
            print(f"[Terminal Log] Transcript for {video_id} failed validation (low quality or irrelevant).")
            return None, 0.0
            
    except subprocess.CalledProcessError as e:
        # With text=True, stderr is already a string, not bytes
        error_msg = e.stderr if e.stderr else (e.stdout if e.stdout else str(e))
        error_display = error_msg[:200] if error_msg else str(e)
        print(f"[Terminal Log] Error retrieving transcript via yt-dlp for {video_id}: {error_display}")
        return None, 0.0
    except Exception as e:
        print(f"[Terminal Log] Error retrieving transcript via yt-dlp for {video_id}: {e}")
        return None, 0.0
