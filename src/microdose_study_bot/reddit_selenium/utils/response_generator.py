"""
Purpose: Generate research-focused responses for Selenium workflows.
"""

# Imports
import re
import random
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from microdose_study_bot.core.safety.policies import DEFAULT_REPLY_RULES

# Constants

# Public API
class ResponseGenerator:
    """Generates safe, ethical responses about psychedelic research"""
    
    def __init__(self, config=None):
        self.config = config
        self.research_sources = [
            "Johns Hopkins Center for Psychedelic and Consciousness Research",
            "Imperial College London's Centre for Psychedelic Research",
            "UC Berkeley Center for the Science of Psychedelics",
            "MAPS (Multidisciplinary Association for Psychedelic Studies)",
            "Nature Reviews Neuroscience",
            "Journal of Psychopharmacology"
        ]
        
        # Ethical disclaimer that must be included in all responses
        self.ethical_disclaimer = (
            "\n\n---\n"
            "*Disclaimer: I am a research bot studying discussions about microdosing. "
            "This is not medical advice. Always consult qualified healthcare professionals "
            "and consider legal implications. Research participation should be through "
            "approved clinical trials.*"
        )
        
        # Response templates by topic
        self.templates = {
            "microdosing": [
                "Current research on {topic} shows mixed results. {source} published a study finding {finding}. However, more research is needed to confirm these effects.",
                "A {year} study from {source} examined {topic}. Their findings suggested {finding}, but the authors noted limitations including {limitation}.",
                "The scientific literature on {topic} is growing. While anecdotal reports are common, controlled studies like those from {source} emphasize the importance of {key_point}."
            ],
            "safety": [
                "Safety considerations for {topic} include {safety1}, {safety2}, and {safety3}. {source} provides guidelines for harm reduction in psychedelic use.",
                "When discussing {topic}, it's important to consider {safety1} and {safety2}. Research from {source} highlights the risks of {risk} without proper precautions.",
                "Harm reduction principles apply to {topic}. Key practices include {safety1}, {safety2}, and having {safety3}. The {source} offers resources for safe practices."
            ],
            "research": [
                "The current state of research on {topic} includes {study1} and {study2}. {source} is conducting ongoing trials to better understand {aspect}.",
                "Recent studies from {source} have explored {topic}. Preliminary results show {result}, but larger trials are needed to establish efficacy.",
                "Research methodologies for studying {topic} vary. {source} uses {method} to investigate {aspect}, contributing to the growing evidence base."
            ]
        }
        
        # Facts database (simplified - in reality would be more comprehensive)
        self.research_facts = {
            "microdosing": [
                {"finding": "placebo effects may account for many reported benefits", "year": "2021", "source": "Imperial College London"},
                {"finding": "improvements in mood and creativity were reported but not consistently measured", "year": "2022", "source": "Johns Hopkins"},
                {"finding": "individual responses vary significantly based on expectation and context", "year": "2020", "source": "University of Toronto"}
            ],
            "psilocybin": [
                {"finding": "rapid antidepressant effects in treatment-resistant depression", "year": "2021", "source": "New England Journal of Medicine"},
                {"finding": "significant reductions in anxiety for patients with life-threatening illness", "year": "2020", "source": "JAMA Psychiatry"},
                {"finding": "long-lasting changes in personality and outlook in some participants", "year": "2018", "source": "Psychopharmacology"}
            ],
            "safety": [
                {"safety1": "proper screening for contraindications", "safety2": "careful attention to set and setting", "safety3": "professional supervision for higher doses"},
                {"safety1": "starting with very low doses", "safety2": "having trusted support present", "safety3": "integration practices after the experience"}
            ]
        }
    
    def analyze_post(self, post_text: str, title: str = "") -> Dict[str, any]:
        """
        Analyze a post to determine appropriate response
        
        Returns:
            Dict with analysis including topic, sentiment, keywords, etc.
        """
        analysis = {
            "topic": "general",
            "sentiment": "neutral",
            "keywords_found": [],
            "is_question": False,
            "requests_advice": False,
            "mentions_safety": False
        }
        
        text = f"{title} {post_text}".lower()
        
        # Determine topic
        topics = {
            "microdosing": ["microdos", "sub-perceptual", "fadiman", "stadman"],
            "psilocybin": ["psilocybin", "shroom", "magic mushroom"],
            "lsd": ["lsd", "acid", "lysergic"],
            "depression": ["depress", "hopeless", "suicid"],
            "anxiety": ["anxiet", "panic", "worry", "stress"],
            "safety": ["safe", "risk", "harm", "danger", "side effect"],
            "research": ["study", "research", "trial", "evidence", "science"]
        }
        
        for topic, indicators in topics.items():
            if any(indicator in text for indicator in indicators):
                analysis["topic"] = topic
                analysis["keywords_found"].extend(indicators)
        
        # Check if it's a question
        analysis["is_question"] = any(marker in text for marker in ["?", "how", "what", "why", "when", "where", "can", "should"])
        
        # Check for advice requests
        analysis["requests_advice"] = any(phrase in text for phrase in [
            "should i", "can i", "is it safe to", "what do you think", "advice", "recommend"
        ])
        
        # Check for safety mentions
        analysis["mentions_safety"] = any(term in text for term in ["safe", "danger", "risk", "harm", "side effect", "bad trip"])
        
        # Determine sentiment (simplified)
        positive_words = ["good", "great", "help", "benefit", "improve", "positive", "amazing"]
        negative_words = ["bad", "terrible", "harm", "danger", "scary", "negative", "awful"]
        
        pos_count = sum(1 for word in positive_words if word in text)
        neg_count = sum(1 for word in negative_words if word in text)
        
        if pos_count > neg_count:
            analysis["sentiment"] = "positive"
        elif neg_count > pos_count:
            analysis["sentiment"] = "negative"
        
        return analysis
    
    def generate_response(self, post_analysis: Dict, original_post: str = "") -> Tuple[str, bool]:
        """
        Generate an appropriate response based on analysis
        
        Returns:
            (response_text: str, needs_human_approval: bool)
        """
        topic = post_analysis["topic"]
        is_question = post_analysis["is_question"]
        requests_advice = post_analysis["requests_advice"]
        
        # Always need human approval for advice requests
        if requests_advice:
            response = self._generate_cautious_response(topic)
            return self._apply_policy(response), True
        
        # Questions get informational responses
        if is_question:
            response = self._generate_informational_response(topic, post_analysis)
            return self._apply_policy(response), False  # Can auto-respond to informational questions
        
        # Otherwise generate discussion response
        response = self._generate_discussion_response(topic, post_analysis)
        return self._apply_policy(response), True  # Needs approval for discussion posts

    # Helpers
    def _apply_policy(self, text: str) -> str:
        """Enforce sentence-count policies on generated responses."""
        max_sentences = int(DEFAULT_REPLY_RULES.get("max_sentences", 5))
        min_sentences = int(DEFAULT_REPLY_RULES.get("min_sentences", 2))
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
        if len(sentences) > max_sentences:
            sentences = sentences[:max_sentences]
        if len(sentences) < min_sentences:
            sentences.append("Happy to share more if helpful.")
        return " ".join(sentences)
    
    def _generate_informational_response(self, topic: str, analysis: Dict) -> str:
        """Generate informational response for questions"""
        source = random.choice(self.research_sources)
        
        if topic in ["microdosing", "psilocybin", "lsd"]:
            if topic in self.research_facts:
                fact = random.choice(self.research_facts[topic])
                
                if "finding" in fact:
                    response = (
                        f"Research from {fact['source']} ({fact['year']}) found that "
                        f"{fact['finding']}. Other studies from {source} have contributed to "
                        "understanding this topic.\n\n"
                        "For current information, you might check:\n"
                        "• ClinicalTrials.gov for ongoing research\n"
                        "• University research center websites\n"
                        "• Peer-reviewed journals in psychopharmacology"
                    )
                else:
                    response = (
                        f"Current research emphasizes {fact.get('safety1', 'safety measures')} "
                        f"when considering {topic}. {source} provides guidelines based on "
                        "the available evidence.\n\n"
                        "Key resources for evidence-based information include "
                        "academic journals and research institution publications."
                    )
            else:
                response = (
                    f"Research on {topic} is an active area of study. {source} is one of "
                    "several institutions conducting research in this field.\n\n"
                    "For evidence-based information, consider reviewing:\n"
                    "• Systematic reviews and meta-analyses\n"
                    "• Randomized controlled trial results\n"
                    "• Research from academic medical centers"
                )
        else:
            response = (
                f"Your question relates to {topic}. Research in this area includes studies "
                f"from institutions like {source}. The evidence base is growing but still "
                "developing for many applications.\n\n"
                "For reliable information, look for:\n"
                "• Peer-reviewed publications\n"
                "• Research with clear methodology sections\n"
                "• Studies that acknowledge limitations"
            )
        
        return response + self.ethical_disclaimer
    
    def _generate_discussion_response(self, topic: str, analysis: Dict) -> str:
        """Generate response for discussion posts"""
        source = random.choice(self.research_sources)
        
        if analysis["sentiment"] == "positive":
            opening = (
                f"Thanks for sharing your perspective on {topic}. "
                f"It's interesting to hear about different experiences. "
            )
        elif analysis["sentiment"] == "negative":
            opening = (
                f"Your points about {topic} raise important considerations. "
                f"Research often examines both potential benefits and risks. "
            )
        else:
            opening = (
                f"Your discussion of {topic} touches on an important research area. "
            )
        
        if topic in self.research_facts and len(self.research_facts[topic]) > 0:
            fact = random.choice(self.research_facts[topic])
            
            if "finding" in fact:
                research_note = (
                    f"Research from {fact['source']} ({fact['year']}) found that "
                    f"{fact['finding']}. Studies from {source} also contribute to "
                    "our understanding of this topic."
                )
            else:
                research_note = (
                    f"Research emphasizes {fact.get('safety1', 'important considerations')} "
                    f"in this area. {source} provides evidence-based guidelines."
                )
        else:
            research_note = (
                f"Research from {source} and other institutions continues to explore {topic}. "
                "The scientific approach helps distinguish evidence from anecdote."
            )
        
        discussion_prompt = (
            "\n\nWhat do others think about the research findings in this area? "
            "Have you encountered particular studies that informed your perspective?"
        )
        
        return opening + research_note + discussion_prompt + self.ethical_disclaimer
    
    def _generate_cautious_response(self, topic: str) -> str:
        """Generate response for posts requesting advice"""
        response = (
            f"I notice your post mentions {topic} and seems to ask for advice. "
            "As a research bot, I focus on sharing information about studies and evidence "
            "rather than giving personal advice.\n\n"
            "For questions about personal situations, it's important to consult with "
            "qualified healthcare professionals who can consider your specific circumstances. "
            "They can provide guidance based on both current research and clinical expertise.\n\n"
            "If you're interested in research participation, you might explore:\n"
            "• Clinical trials listed on ClinicalTrials.gov\n"
            "• Research studies at university medical centers\n"
            "• Legally-sanctioned therapeutic programs where available"
        )
        
        return response + self.ethical_disclaimer
    
    def is_response_appropriate(self, response: str, original_post: str) -> bool:
        """
        Basic check if response is appropriate
        
        This could be expanded with more sophisticated checks
        """
        # Check length
        if len(response) < 50 or len(response) > 2000:
            return False
        
        # Check for problematic content
        problematic_phrases = [
            "you should", "you must", "take my advice", "trust me",
            "guaranteed", "100% effective", "no risk", "completely safe"
        ]
        
        response_lower = response.lower()
        for phrase in problematic_phrases:
            if phrase in response_lower:
                return False
        
        # Check that ethical disclaimer is included
        if "disclaimer" not in response_lower and "not medical advice" not in response_lower:
            return False
        
        return True

# Example usage
if __name__ == "__main__":
    generator = ResponseGenerator()
    
    test_post = "Has anyone tried microdosing for depression? What was your experience?"
    analysis = generator.analyze_post(test_post)
    print("Analysis:", analysis)
    
    response, needs_approval = generator.generate_response(analysis, test_post)
    print("\nGenerated Response:")
    print(response)
    print(f"\nNeeds human approval: {needs_approval}")
