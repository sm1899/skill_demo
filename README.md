# AI Instruction Manual Generator 🎓

An intelligent system that converts unstructured YouTube tutorials into structured, verifiable, and interactive instruction manuals.

## 🚀 Key Features
*   **10-Step Chronological Guides**: Automatically synthesizes "from scratch" tutorials for beginners.
*   **Interactive AI Coach**: A chat interface that answers questions about the guide.
*   **Academic-Style Citations**: Every claim is backed by a verifiable source with a timestamped link (e.g., `[1]`, `[2]`).
*   **Multi-Agent Architecture**: Uses specialized agents for drafting content and grounding it in reality.

---

## 🏗️ System Architecture & Dataflow

The system operates in a linear pipeline to generate the manual, followed by a cyclic loop for the interactive coaching session.

### 1. Data Ingestion (Map Phase)
*   **Input**: User Topic (e.g., "Gamma AI").
*   **Search**: Identify top 3-5 "long-form" tutorials on YouTube (excluding Shorts/promos).
*   **Extraction**: Download valid transcripts (VTT) and clean them into timestamped chunks.
*   **Verify**: Filter out low-quality or irrelevant transcripts.

### 2. Curriculum Synthesis (Reduce Phase)
*   **Milestone Extraction**: An LLM agent extracts key "atomic concepts" from each video.
*   **Synthesis Agent**: Cross-references milestones to create a unified 10-step path.
*   **Citation Injection**: Identifying which video (`V1`, `V2`) supports which step.

### 3. Interactive Coaching (The "AI Coach")
When the user asks a question, a **Multi-Agent System** generates the response:

```mermaid
graph TD
    subgraph Dataflow
        User[User Input / Chat] -->|Question| AICoach
        
        AICoach[AI COACH<br/>Orchestrator] <--> KnowledgeBase[(Knowledge Base<br/>Cleaned Transcripts)]
        
        AICoach -->|1. Draft Logic| ResponseAgent[RESPONSE AGENT<br/>The Instructor]
        
        ResponseAgent -->|2. Draft Text| CitationAgent[CITATION AGENT<br/>The Librarian]
        
        CitationAgent -->|3. Grounded Text with V#| Linkifier[UI LINKIFIER<br/>Visual Layer]
        
        Linkifier -->|4. Final Output with Links| Display[User Interface]
        
        Display -->|Feedback Loop| User
    end
    
    subgraph Context
        History(Chat History) -.-> AICoach
        History -.-> ResponseAgent
    end
    
    style User fill:#f9f,stroke:#333
    style AICoach fill:#bbf,stroke:#333
    style CitationAgent fill:#bfb,stroke:#333
```

<details>
<summary><b>Click here for a text-only architecture diagram</b> (If the graph above doesn't render)</summary>

```text
      User Input (Chat)
           │
           ▼
    +-------------------+      +-------------------------+
    |     AI COACH      | <--> |     Knowledge Base      |
    |   (Orchestrator)  |      | (Cleaned Transcripts)   |
    +--------+----------+      +-------------------------+
             ^   │                         ^
             |   │ 1. "Draft"              |
      (History)  ▼                         |
    +-------------------+                  |
    |   RESPONSE AGENT  | -----------------+
    |  (The Instructor) |
    +--------+----------+
             │
             │ 2. "Draft + Transcripts"
             ▼
    +-------------------+
    |   CITATION AGENT  |  👉 Inserts [V# - MM:SS] tags
    |  (The Librarian)  |     (Strict Grounding)
    +--------+----------+
             │
             │ 3. "Grounded Text"
             ▼
    +-------------------+
    |    UI LINKIFIER   |  👉 Resequences to [1], [2]...
    |   (Visual Layer)  |  👉 Builds "Sources" Sidebar
    +--------+----------+
             │
             ▼
      Final Output 🖥️
             │
             │ (User Reads & Replies)
             └───────────────────────────┐
                                         │
                                         ▼
                                  (Repeat Loop) 🔄
```
</details>

*   **Response Agent**: "Here is how you do X..." (Focuses on pedagogy).
*   **Citation Agent**: "Here is how you do X [V1 - 02:30]..." (Focuses on truth).
*   **UI Linkifier**: Converts `[V1 - 02:30]` -> `[1]` and adds the link to the sidebar.

---

## 🤖 Agent Design

We utilize a **Separation of Concerns** principle to prevent hallucinations:

1.  **The Instructor (Response Agent)**
    *   *Goal*: Be helpful, encourage the user, and explain concepts simply.
    *   *Constraint*: Has access to transcripts but is told NOT to worry about specific timestamps to avoid breaking flow.
2.  **The Librarian (Citation Agent)**
    *   *Goal*: Prove every claim.
    *   *Constraint*: Cannot add new advice. Can only insert `[V# - MM:SS]` tags where the text matches the source truth.
3.  **The Referee (Synthesis Agent)**
    *   *Goal*: Ensure the 10-step guide is chronological and logical.
    *   *Constraint*: Must reject non-beginner content (e.g., advanced API usage) if it breaks the "Zero to One" flow.

---

## ✅ Addressing Task Requirements

| Requirement | Implementation |
| :--- | :--- |
| **Complete Beginner Focus** | The `Synthesis Agent` is strictly prompted to create "Zero to Hero" paths, verified by "beginner" persona checks. |
| **Chronological Order** | The system enforces a strict 1-10 step sequence. The `AICoach` will not advance to Step 2 until the user is ready. |
| **YouTube Source** | We use `yt-dlp` to fetch real-time data, ensuring the manual is "latest" and captures evolving features (unlike static training data). |
| **Verification** | **Solved via Citations.** Every instruction is linked to a video timestamp. If the link doesn't match the text, the user can instantly verify it (Hallucination Proofing). |
| **Tech Stack** | Python, LangChain, Google Gemini 3.0 Flash Preview, Gradio (Web UI). |

---

## 🛠️ How to Run

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Set Environment**:
    Create a `.env` file with your keys:
    ```env
    GOOGLE_API_KEY=your_gemini_key
    YOUTUBE_API_KEY=your_youtube_key
    ```
3.  **Launch App**:
    ```bash
    python app.py
    ```

---

> **Note**: Portions of this README and the underlying codebase were generated with the assistance of Large Language Models.
