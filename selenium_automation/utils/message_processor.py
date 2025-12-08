import re
import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple

class MessageProcessor:
    def __init__(self, config=None):
        self.config = config
        
        # Load keywords from config or use defaults
        if config and hasattr(config, 'bot_settings'):
            self.keywords = config.bot_settings.get("keywords", [])
        else:
            self.keywords = [
                "microdosing", "microdose", "psilocybin", "mushroom",
                "psychedelic", "mental health", "depression", "anxiety",
                "LSD", "therapeutic", "harm reduction"
            ]
        
        # Setup paths
        self.project_root = Path(__file__).parent.parent.parent
        self.logs_dir = self.project_root / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        self.processed_file = self.logs_dir / "processed_messages.json"
        self.processed_messages = self.load_processed_messages()
    
    def load_processed_messages(self) -> List[str]:
        """Load already processed messages from file"""
        try:
            if self.processed_file.exists():
                with open(self.processed_file, 'r') as f:
                    return json.load(f)
            else:
                return []
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load processed messages: {e}")
            return []
    
    def save_processed_message(self, message_id: str) -> None:
        """Save processed message ID"""
        if message_id not in self.processed_messages:
            self.processed_messages.append(message_id)
            # Keep only last 1000 to prevent file from growing indefinitely
            self.processed_messages = self.processed_messages[-1000:]
            
            try:
                with open(self.processed_file, 'w') as f:
                    json.dump(self.processed_messages, f, indent=2)
            except IOError as e:
                print(f"Warning: Could not save processed messages: {e}")
    
    def is_already_processed(self, message_id: str) -> bool:
        """Check if message has already been processed"""
        return message_id in self.processed_messages
    
    def check_for_keywords(self, text: str) -> Tuple[bool, List[str]]:
        """
        Check if message contains relevant keywords
        
        Returns:
            (contains_keywords: bool, matched_keywords: List[str])
        """
        if not text:
            return False, []
        
        text_lower = text.lower()
        matched = []
        
        for keyword in self.keywords:
            # Handle multi-word keywords
            keyword_lower = keyword.lower()
            if keyword_lower in text_lower:
                matched.append(keyword)
        
        return len(matched) > 0, matched
    
    def extract_topic(self, text: str) -> str:
        """Extract main topic from text"""
        text_lower = text.lower()
        
        topic_priority = [
            "microdosing", "psilocybin", "LSD", "depression", 
            "anxiety", "therapeutic", "harm reduction", "mental health"
        ]
        
        for topic in topic_priority:
            if topic in text_lower:
                return topic
        
        # Check for related terms
        if any(term in text_lower for term in ["shroom", "magic mushroom"]):
            return "psilocybin"
        elif any(term in text_lower for term in ["acid", "lysergic"]):
            return "LSD"
        elif any(term in text_lower for term in ["sad", "low mood", "hopeless"]):
            return "depression"
        elif any(term in text_lower for term in ["worry", "panic", "stress"]):
            return "anxiety"
        
        return "general"
    
    def get_recommended_response(self, topic: str, text: str = "") -> str:
        """Get unbiased response based on topic"""
        # Base responses
        responses = {
            "microdosing": """Based on current research, microdosing involves taking sub-perceptual doses of psychedelics. Many users report benefits for mood and creativity, but scientific evidence is still emerging.

Key points from research:
• Effects vary significantly between individuals
• Placebo effects may play a significant role
• Long-term effects are not well understood

For unbiased information:
• Johns Hopkins University Center for Psychedelic and Consciousness Research
• Imperial College London's Centre for Psychedelic Research
• MAPS (Multidisciplinary Association for Psychedelic Studies)

Important: Always consult healthcare professionals and consider legal implications.""",
            
            "psilocybin": """Psilocybin is being studied for various mental health conditions. Current research suggests it may help with:
• Treatment-resistant depression
• End-of-life anxiety
• Certain addiction disorders

Research status:
• Several Phase 2/3 clinical trials underway
• Breakthrough therapy designation by FDA for depression
• Not approved for general medical use yet

Resources:
• Nature reviews on psychedelic research
• New England Journal of Medicine psilocybin studies
• ClinicalTrials.gov database""",
            
            "depression": """For depression, research on psychedelics is promising but still experimental:

Current evidence:
• Psilocybin shows rapid antidepressant effects in trials
• Effects may last weeks to months after single doses
• Works differently than traditional antidepressants

Important considerations:
• Should only be done in clinical/research settings
• Requires professional screening and support
• Not suitable for everyone (bipolar disorder, psychosis risk)

Alternatives to explore:
• Cognitive Behavioral Therapy (CBT)
• Mindfulness-Based Cognitive Therapy (MBCT)
• Conventional antidepressants with medical supervision""",
            
            "harm reduction": """Harm reduction principles for psychedelic use:

Essential practices:
• Start low, go slow (especially with microdosing)
• Ensure set (mindset) and setting (environment) are safe
• Have a sober trip sitter for full doses
• Test substances when possible (reagent kits)
• Know contraindications (certain medications, conditions)

Resources:
• DanceSafe.org for harm reduction information
• Fireside Project for peer support
• Zendo Project for community care

Remember: The goal is to minimize potential harms while respecting personal autonomy."""
        }
        
        # Get topic-specific response or default
        if topic in responses:
            return responses[topic]
        else:
            # Default research-focused response
            return """Thanks for your interest in psychedelic research. This is an active field with growing scientific interest.

For evidence-based information:
1. Look for peer-reviewed studies in journals like Nature, JAMA, or Neuropsychopharmacology
2. Check research from academic centers like Johns Hopkins, Imperial College, or UC Berkeley
3. Be cautious of anecdotal reports and commercial claims

Research ethics reminder:
• Studies should have proper ethical review
• Results should be published in peer-reviewed journals
• Conflicts of interest should be disclosed

For personalized advice, consult qualified healthcare professionals familiar with current research."""
    
    def is_spam(self, text: str) -> bool:
        """Basic spam detection"""
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Common spam indicators
        spam_indicators = [
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",  # URLs
            r"buy now", "click here", "limited time", "special offer",
            r"DM me", "message me", "contact me", "whatsapp", "telegram",
            r"\$\d+", "discount", "promo code", "cheap", "affordable"
        ]
        
        # Check for excessive capital letters (shouting)
        if len(text) > 20:
            capital_ratio = sum(1 for c in text if c.isupper()) / len(text)
            if capital_ratio > 0.5:  # More than 50% capitals
                return True
        
        # Check spam indicators
        for indicator in spam_indicators:
            if re.search(indicator, text_lower):
                return True
        
        # Check for very short or repetitive messages
        if len(text) < 10 or text.count(text[:5]) > 3:
            return True
        
        return False