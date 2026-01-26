#!/usr/bin/env python3
"""
Free Content Generator for MCRDSE Reddit Posts
Uses templates and OpenAI API (free tier) or local LLM alternatives
"""
import json
import random
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
import requests
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PostGenerator:
    """Generates human-like Reddit posts for MCRDSE communities"""
    
    def __init__(self, use_free_ai=True):
        self.use_free_ai = use_free_ai
        self.templates = self.load_templates()
        self.seo_keywords = self.load_seo_keywords()
        
    def load_templates(self) -> Dict:
        """Load post templates"""
        template_path = Path("config/content_templates.json")
        if not template_path.exists():
            return self.get_default_templates()
        return json.loads(template_path.read_text())
    
    def get_default_templates(self) -> Dict:
        """Default content templates"""
        return {
            "post_types": {
                "discussion": {
                    "templates": [
                        "What are your thoughts on {topic}?",
                        "Discussion: {topic}",
                        "Let's talk about {topic}",
                        "What does the community think about {topic}?"
                    ],
                    "prompts": [
                        "Start a thoughtful discussion about {topic}. Include specific questions to engage readers.",
                        "Create a discussion post about {topic} that encourages community sharing."
                    ]
                },
                "question": {
                    "templates": [
                        "Question about {topic}",
                        "Need advice: {topic}",
                        "Help understanding {topic}",
                        "Curious about {topic}"
                    ],
                    "prompts": [
                        "Write a genuine question about {topic} that shows curiosity and openness to learning.",
                        "Create a question post seeking community advice about {topic}."
                    ]
                },
                "experience": {
                    "templates": [
                        "My experience with {topic}",
                        "Sharing my journey with {topic}",
                        "Personal story: {topic}",
                        "What I learned from {topic}"
                    ],
                    "prompts": [
                        "Share a personal experience about {topic} in a vulnerable, authentic way.",
                        "Write about a personal journey with {topic} including challenges and insights."
                    ]
                },
                "research": {
                    "templates": [
                        "Research update: {topic}",
                        "New study about {topic}",
                        "Scientific perspective on {topic}",
                        "Evidence-based look at {topic}"
                    ],
                    "prompts": [
                        "Summarize research about {topic} in an accessible way for the community.",
                        "Discuss scientific findings about {topic} and their implications."
                    ]
                },
                "resource": {
                    "templates": [
                        "Resource: {topic}",
                        "Helpful guide for {topic}",
                        "Collection of resources about {topic}",
                        "Learning materials: {topic}"
                    ],
                    "prompts": [
                        "Create a helpful resource post about {topic} with practical information.",
                        "Share educational resources about {topic} that the community will find useful."
                    ]
                }
            },
            "topics": [
                "microdosing protocols",
                "psilocybin therapy",
                "harm reduction",
                "integration practices",
                "neuroplasticity",
                "mental health benefits",
                "safety considerations",
                "community support",
                "legal developments",
                "scientific research",
                "personal growth",
                "creativity enhancement",
                "therapy alternatives",
                "meditation and mindfulness",
                "trauma healing"
            ],
            "tone_variants": ["casual", "thoughtful", "curious", "informative", "personal", "scientific"],
            "length_variants": ["short", "medium", "detailed"],
            "engagement_boosters": [
                "What has your experience been?",
                "Would love to hear different perspectives.",
                "Has anyone else encountered this?",
                "What resources have you found helpful?",
                "How do you approach this in your practice?",
                "Let's share our collective wisdom.",
                "I'm curious about the community's thoughts.",
                "What questions do you still have about this?"
            ]
        }
    
    def load_seo_keywords(self) -> List[str]:
        """Load SEO keywords"""
        seo_path = Path("config/seo/seo_keywords.json")
        if seo_path.exists():
            data = json.loads(seo_path.read_text())
            # Combine all keywords
            all_keywords = []
            for key in ["primary_keywords", "longtail_keywords", "question_keywords"]:
                all_keywords.extend(data.get(key, []))
            return all_keywords
        return []
    
    def generate_with_free_ai(self, prompt: str) -> Optional[str]:
        """
        Use free AI APIs (Hugging Face, OpenAI free tier alternatives)
        Returns generated text or None if failed
        """
        try:
            # Option 1: Hugging Face Inference API (free tier)
            # You need to create a free account at huggingface.co and get an API token
            API_TOKEN = ""  # Add your token in config
            
            if not API_TOKEN:
                # Fall back to template-based generation
                return None
            
            API_URL = "https://api-inference.huggingface.co/models/gpt2"
            headers = {"Authorization": f"Bearer {API_TOKEN}"}
            
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_length": 500,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "do_sample": True
                }
            }
            
            response = requests.post(API_URL, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    return result[0].get("generated_text", "")
            
            return None
            
        except Exception as e:
            logger.error(f"AI generation failed: {e}")
            return None
    
    def generate_with_template(self, post_type: str, topic: str) -> Dict:
        """Generate post using template system"""
        templates = self.templates["post_types"].get(post_type, {})
        
        # Select template
        title_template = random.choice(templates.get("templates", ["{topic}"]))
        title = title_template.replace("{topic}", topic)
        
        # Add SEO keywords if available
        if self.seo_keywords and random.random() > 0.7:
            keyword = random.choice(self.seo_keywords)
            title = f"{title} - {keyword}"
        
        # Generate content using template patterns
        content_patterns = [
            f"I've been thinking about {topic} recently and wanted to share some thoughts.",
            f"Hey everyone, I wanted to start a discussion about {topic}.",
            f"After researching {topic}, here's what I've learned...",
            f"My personal journey with {topic} has been...",
            f"From a scientific perspective, {topic} is interesting because...",
            f"I'm curious how others approach {topic} in their practice.",
            f"Let's talk about the practical aspects of {topic}.",
            f"There's been some interesting research lately about {topic}.",
            f"I've found that {topic} can be particularly helpful for...",
            f"What does the community think about the future of {topic}?"
        ]
        
        # Build content
        paragraphs = []
        
        # Introduction
        intro = random.choice(content_patterns)
        paragraphs.append(intro)
        
        # Main content (1-3 paragraphs)
        for _ in range(random.randint(1, 3)):
            paragraph = self._generate_paragraph(topic)
            paragraphs.append(paragraph)
        
        # Add engagement questions
        if random.random() > 0.3:
            booster = random.choice(self.templates["engagement_boosters"])
            paragraphs.append(f"\n{booster}")
        
        # Add MCRDSE reference (subtle)
        if random.random() > 0.5:
            paragraphs.append("\n*Note: This is for discussion purposes only. For research-based information, check out MCRDSE's resource portal.*")
        
        content = "\n\n".join(paragraphs)
        
        # Select subreddit
        subreddits = [
            "MicrodosingResearch",
            "PsychedelicTherapy",
            "MicrodosingSupport",
            "Psychonaut",
            "MCRDSE_Community"
        ]
        
        return {
            "title": title,
            "content": content,
            "subreddit": random.choice(subreddits),
            "type": post_type,
            "topic": topic,
            "length": len(content),
            "generated_at": datetime.now().isoformat(),
            "seo_optimized": bool(self.seo_keywords)
        }
    
    def _generate_paragraph(self, topic: str) -> str:
        """Generate a single paragraph about a topic"""
        structures = [
            "Many people find that {topic} helps with {benefit}. For example, {example}.",
            "The research on {topic} suggests {finding}. However, {caveat}.",
            "In my experience, {topic} requires {requirement}. It's important to {advice}.",
            "When considering {topic}, it's crucial to think about {aspect}. This is because {reason}.",
            "One approach to {topic} is {approach}. This involves {steps} and can lead to {outcome}.",
            "There's growing interest in {topic} due to {reason}. Studies show {evidence}.",
            "Practicing {topic} safely means {safety}. Always remember {warning}.",
            "The community has diverse perspectives on {topic}. Some believe {view1}, while others {view2}."
        ]
        
        # Fill in placeholders
        structure = random.choice(structures)
        
        # Available fillers
        benefits = ["mental clarity", "emotional balance", "creativity", "focus", "well-being"]
        examples = ["improved mood regulation", "enhanced problem-solving", "deeper self-awareness"]
        findings = ["promising results", "mixed evidence", "preliminary but encouraging data"]
        caveats = ["more research is needed", "individual responses vary", "safety comes first"]
        requirements = ["patience", "careful observation", "proper guidance", "self-reflection"]
        advice = ["start low and go slow", "keep a journal", "consult professionals", "listen to your body"]
        aspects = ["set and setting", "intention", "integration", "community support"]
        reasons = ["mental health crisis", "pharmaceutical limitations", "personal growth trends"]
        evidence = ["reduced symptoms", "improved quality of life", "lasting changes"]
        safety = ["proper dosing", "medical screening", "having a sitter", "integration support"]
        warnings = ["this is not medical advice", "consult healthcare providers", "know the legal status"]
        views = ["it's revolutionary", "it requires caution", "more research is essential"]
        
        # Replace placeholders
        replacements = {
            "{benefit}": random.choice(benefits),
            "{example}": random.choice(examples),
            "{finding}": random.choice(findings),
            "{caveat}": random.choice(caveats),
            "{requirement}": random.choice(requirements),
            "{advice}": random.choice(advice),
            "{aspect}": random.choice(aspects),
            "{reason}": random.choice(reasons),
            "{evidence}": random.choice(evidence),
            "{safety}": random.choice(safety),
            "{warning}": random.choice(warnings),
            "{view1}": random.choice(views),
            "{view2}": random.choice(views),
            "{approach}": f"the {random.choice(['Fadiman', 'Stadman', 'custom'])} protocol",
            "{steps}": random.choice(["starting with minimal doses", "keeping detailed notes", "regular breaks"]),
            "{outcome}": random.choice(["personal insights", "symptom relief", "enhanced creativity"])
        }
        
        for placeholder, replacement in replacements.items():
            structure = structure.replace(placeholder, replacement)
        
        return structure
    
    def generate_batch(self, count: int = 5, post_types: List[str] = None) -> List[Dict]:
        """Generate multiple posts"""
        if post_types is None:
            post_types = list(self.templates["post_types"].keys())
        
        posts = []
        topics = self.templates["topics"]
        
        for i in range(count):
            post_type = random.choice(post_types)
            topic = random.choice(topics)
            
            post = self.generate_with_template(post_type, topic)
            posts.append(post)
            
            # Small delay to vary generation
            time.sleep(0.1)
        
        return posts
    
    def save_posts(self, posts: List[Dict], filename: str = None):
        """Save generated posts to file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"generated_posts_{timestamp}.json"
        
        output_path = Path("data/generated_content") / filename
        output_path.parent.mkdir(exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(posts, f, indent=2)
        
        logger.info(f"Saved {len(posts)} posts to {output_path}")
        return output_path
    
    def schedule_posts(self, posts: List[Dict], hours_apart: int = 4):
        """Add scheduling information to posts"""
        now = datetime.now()
        
        for i, post in enumerate(posts):
            post_time = now + timedelta(hours=i * hours_apart)
            post["scheduled_time"] = post_time.isoformat()
            post["scheduled_for_submission"] = True
        
        return posts

if __name__ == "__main__":
    generator = PostGenerator(use_free_ai=False)  # Use templates for now
    
    # Generate posts
    posts = generator.generate_batch(count=3)
    
    # Schedule them
    scheduled_posts = generator.schedule_posts(posts, hours_apart=6)
    
    # Save
    generator.save_posts(scheduled_posts)
    
    # Preview
    for i, post in enumerate(posts):
        print(f"\n{'='*50}")
        print(f"Post {i+1}: {post['title']}")
        print(f"Subreddit: r/{post['subreddit']}")
        print(f"Type: {post['type']}")
        print(f"Content preview: {post['content'][:200]}...")