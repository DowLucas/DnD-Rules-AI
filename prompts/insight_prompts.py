"""
Insight generation prompts for D&D transcriptions.
"""

def get_regular_insight_prompt(combined_text, previous_insight=None):
    """
    Returns the prompt for generating regular insights from transcriptions.
    
    Args:
        combined_text (str): The combined transcription text to analyze
        previous_insight (str, optional): The previous insight text
        
    Returns:
        str: The formatted prompt
    """
    prompt = (
        "Analyze the following D&D discussion snippets. Identify if any specific D&D 5e rule is being discussed, "
        "implied, or might be relevant. "
        "Use the search_rules_tool to search the ChromaDB vector database for relevant rules first. "
        "Prioritize information from the vector database over your general knowledge. "
        "If a rule is relevant, respond ONLY with a concise explanation or application of that rule, focusing strictly on mechanics or outcome. Start the response directly with the rule explanation. "
        "Avoid mentioning the snippets, searching, or conversational filler. "
        "If providing a rule insight, conclude your response with a one-sentence summary labeled 'TL;DR:'. "
        "If you determine that no specific rule is relevant to the discussion, respond ONLY with the exact phrase: No Insight right now "
    )
    
    if previous_insight:
        prompt += (
            f"Previously, you identified this insight: \"{previous_insight}\"\n"
            "Only provide a new insight if the discussion has moved to a different rule or aspect. "
            "If there's nothing significantly new to add, respond with 'No Insight right now'.\n\n"
        )
    
    prompt += f"Discussion Snippets:\n\n{combined_text}"
    
    return prompt


def get_forced_insight_prompt(combined_text, previous_insight=None):
    """
    Returns the prompt for generating forced insights from transcriptions.
    
    Args:
        combined_text (str): The combined transcription text to analyze
        previous_insight (str, optional): The previous insight text
        
    Returns:
        str: The formatted prompt
    """
    prompt = (
        "Analyze the following D&D discussion snippets. Identify the MOST relevant D&D 5e rule, even if the connection is weak. "
        "Use the search_rules_tool to search the ChromaDB vector database for relevant rules first. "
        "Prioritize information from the vector database over your general knowledge. "
        "Respond ONLY with a concise explanation or application of that rule, focusing strictly on mechanics or outcome. "
        "Do NOT mention the snippets, searching, or conversational filler. Start your response directly with the rule explanation. "
        "Conclude your response with a one-sentence summary labeled 'TL;DR:'. "
    )
    
    if previous_insight:
        prompt += (
            f"Previously, you identified this insight: \"{previous_insight}\"\n"
            "If the same rule is still relevant, elaborate on it rather than repeating information. "
            "If a completely different rule is now more relevant, focus on that instead.\n\n"
        )
    
    prompt += f"Discussion Snippets:\n\n{combined_text}"
    
    return prompt 