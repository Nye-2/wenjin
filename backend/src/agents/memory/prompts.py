"""Prompts for LLM-driven memory extraction."""

MEMORY_EXTRACTION_PROMPT = """You are a memory extraction assistant. Analyze the conversation and extract structured information about the user.

## Task
Extract the following from the conversation:
1. Research context: What field/topic is the user working on?
2. Writing preferences: Any writing style preferences mentioned?
3. Tool preferences: Any model or tool preferences?
4. Facts: Important user information to remember

## Output Format
Return a JSON object with this structure:
```json
{
  "user": {
    "researchContext": {"summary": "...", "updatedAt": "..."},
    "writingPreferences": {"summary": "...", "updatedAt": "..."},
    "toolPreferences": {"summary": "...", "updatedAt": "..."}
  },
  "facts": [
    {"content": "...", "category": "knowledge|behavior|preference", "confidence": 0.0-1.0}
  ]
}
```

## Rules
- Only extract information explicitly mentioned
- Set confidence based on clarity (1.0 = explicit, 0.5 = implied)
- Keep summaries under 100 words
- Maximum 5 facts per extraction
- Return empty objects for categories with no information"""

MEMORY_FACT_SCHEMA = {
    "type": "object",
    "properties": {
        "user": {
            "type": "object",
            "properties": {
                "researchContext": {"type": "object", "properties": {"summary": {"type": "string"}, "updatedAt": {"type": "string"}}},
                "writingPreferences": {"type": "object", "properties": {"summary": {"type": "string"}, "updatedAt": {"type": "string"}}},
                "toolPreferences": {"type": "object", "properties": {"summary": {"type": "string"}, "updatedAt": {"type": "string"}}},
            },
        },
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "category": {"type": "string", "enum": ["knowledge", "behavior", "preference"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["content", "category", "confidence"],
            },
        },
    },
}
