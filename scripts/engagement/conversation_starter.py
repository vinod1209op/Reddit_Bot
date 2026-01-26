#!/usr/bin/env python3
"""
Conversation Starter for MCRDSE Reddit Strategy
Posts engaging content in target subreddits to drive traffic
"""
import json
import random
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import praw  # Reddit API wrapper - free

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConversationStarter:
    """Starts and manages conversations in target subreddits"""
    
    def __init__(self):
        self.config = self.load_config()
        self.reddit = self.setup_reddit_api()
        self.engagement_log = []
        
    def load_config(self) -> Dict:
        """Load configuration"""
        config_path = Path("config/engagement_strategy.json")
        if not config_path.exists():
            return self.get_default_config()
        return json.loads(config_path.read_text())
    
    def get_default_config(self) -> Dict:
        """Default engagement strategy"""
        return {
            "target_subreddits": [
                "microdosing",
                "psilocybin",
                "psychonaut",
                "rationalpsychonaut",
                "nootropics",
                "depression",
                "anxiety",
                "mentalhealth",
                "ADHD",
                "PTSD",
                "CPTSD",
                "neurodiversity",
                "mindfulness",
                "meditation",
                "supplements",
                "biohackers",
                "selfimprovement",
                "therapy",
                "cognitiveload",
                "GetMotivated"
            ],
            "post_categories": {
                "question": {
                    "weight": 0.4,
                    "templates": [
                        "For those with experience, what's your take on {topic}?",
                        "Curious newcomer here - how does {topic} actually work?",
                        "What's the most surprising thing you've learned about {topic}?",
                        "How do you approach {topic} safely and effectively?"
                    ]
                },
                "discussion": {
                    "weight": 0.3,
                    "templates": [
                        "Let's discuss the future of {topic}",
                        "What's missing from the conversation about {topic}?",
                        "The most underrated aspect of {topic} is...",
                        "How has your perspective on {topic} evolved?"
                    ]
                },
                "resource": {
                    "weight": 0.2,
                    "templates": [
                        "Found this helpful resource about {topic}",
                        "What are your go-to resources for learning about {topic}?",
                        "Sharing a comprehensive guide to {topic}",
                        "Educational materials that changed my understanding of {topic}"
                    ]
                },
                "experience": {
                    "weight": 0.1,
                    "templates": [
                        "My personal journey with {topic} - what I wish I knew",
                        "What I've learned after one year of exploring {topic}",
                        "The biggest misconception I had about {topic}",
                        "How {topic} helped me overcome a specific challenge"
                    ]
                }
            },
            "topics": [
                "microdosing protocols",
                "psychedelic therapy",
                "neuroplasticity",
                "mental health alternatives",
                "holistic wellness",
                "consciousness exploration",
                "trauma-informed healing",
                "science vs spirituality",
                "integration practices",
                "community support systems"
            ],
            "engagement_tactics": {
                "reply_to_comments": True,
                "upvote_engagement": True,
                "follow_up_questions": True,
                "thank_responders": True,
                "share_resources": True,
                "acknowledge_dissent": True
            },
            "posting_schedule": {
                "max_posts_per_day": 2,
                "min_hours_between_posts": 4,
                "optimal_times": ["09:00-11:00", "14:00-16:00", "19:00-21:00"],
                "avoid_days": ["Sunday", "Monday"]  # Heavy moderation days
            },
            "safety_limits": {
                "max_comments_per_post": 10,
                "max_posts_per_subreddit_per_week": 2,
                "avoid_controversial_topics": True,
                "disclaimer_required": True
            }
        }
    
    def setup_reddit_api(self):
        """Setup Reddit API connection"""
        try:
            # Using PRAW - Reddit's Python API wrapper
            # You need to create a Reddit app at https://www.reddit.com/prefs/apps
            reddit = praw.Reddit(
                client_id="YOUR_CLIENT_ID",  # From Reddit app
                client_secret="YOUR_CLIENT_SECRET",  # From Reddit app
                user_agent="MCRDSE-Community-Bot/1.0 by YourUsername",
                username="YOUR_REDDIT_USERNAME",
                password="YOUR_REDDIT_PASSWORD"
            )
            return reddit
        except Exception as e:
            logger.error(f"Failed to setup Reddit API: {e}")
            return None
    
    def generate_post_content(self, subreddit: str) -> Dict:
        """Generate content tailored for specific subreddit"""
        category = self.select_category()
        topic = random.choice(self.config["topics"])
        
        templates = self.config["post_categories"][category]["templates"]
        title_template = random.choice(templates)
        title = title_template.replace("{topic}", topic)
        
        # Customize content based on subreddit
        content = self._customize_content(subreddit, category, topic)
        
        # Add disclaimer if required
        if self.config["safety_limits"]["disclaimer_required"]:
            content += "\n\n---\n*Disclaimer: This is for discussion purposes only. Not medical advice.*"
        
        return {
            "title": title,
            "content": content,
            "subreddit": subreddit,
            "category": category,
            "topic": topic,
            "timestamp": datetime.now().isoformat()
        }
    
    def _customize_content(self, subreddit: str, category: str, topic: str) -> str:
        """Customize content for specific subreddit"""
        
        # Subreddit-specific openings
        openings = {
            "microdosing": "As this community understands...",
            "psychonaut": "For fellow explorers of consciousness...",
            "mentalhealth": "In the context of mental wellness...",
            "ADHD": "From a neurodiversity perspective...",
            "meditation": "Connecting mindfulness practices with...",
            "nootropics": "Looking at this through a nootropic lens..."
        }
        
        opening = openings.get(subreddit, "I've been thinking about this recently...")
        
        # Build content sections
        sections = []
        sections.append(opening)
        
        # Add discussion points
        discussion_points = [
            f"What approaches have you found most effective for {topic}?",
            f"How do you balance the potential benefits with safety considerations?",
            f"What resources or studies have shaped your understanding?",
            f"Where do you see the most promising developments happening?",
            f"How does personal experience align with scientific research in this area?"
        ]
        
        # Select 2-3 discussion points
        selected_points = random.sample(discussion_points, random.randint(2, 3))
        sections.extend(selected_points)
        
        # Add engagement prompt
        engagement_prompts = [
            "\nI'd love to hear this community's diverse perspectives.",
            "\nWhat's been your experience or what questions do you have?",
            "\nLet's share our collective wisdom on this.",
            "\nLooking forward to an insightful discussion."
        ]
        
        sections.append(random.choice(engagement_prompts))
        
        # Add subtle MCRDSE reference (only sometimes)
        if random.random() > 0.7:
            sections.append("\n*P.S. For those interested in research-based resources, there's some interesting work being done in this field.*")
        
        return "\n\n".join(sections)
    
    def select_category(self) -> str:
        """Select post category based on weights"""
        categories = list(self.config["post_categories"].keys())
        weights = [self.config["post_categories"][c]["weight"] for c in categories]
        return random.choices(categories, weights=weights, k=1)[0]
    
    def select_subreddit(self) -> str:
        """Select target subreddit"""
        # Weight newer/larger subreddits differently
        target_subs = self.config["target_subreddits"]
        return random.choice(target_subs)
    
    def post_to_reddit(self, post_data: Dict) -> bool:
        """Actually post to Reddit using API"""
        try:
            if not self.reddit:
                logger.error("Reddit API not initialized")
                return False
            
            subreddit = self.reddit.subreddit(post_data["subreddit"])
            
            # Check if we've posted here recently
            if self._check_recent_posts(post_data["subreddit"]):
                logger.warning(f"Recently posted in r/{post_data['subreddit']}, skipping")
                return False
            
            # Submit post
            submission = subreddit.submit(
                title=post_data["title"],
                selftext=post_data["content"]
            )
            
            logger.info(f"Posted: {submission.title} to r/{post_data['subreddit']}")
            logger.info(f"URL: https://reddit.com{submission.permalink}")
            
            # Log engagement
            self.log_engagement(post_data, submission.id)
            
            # Schedule follow-up engagement
            if self.config["engagement_tactics"]["reply_to_comments"]:
                self.schedule_comment_replies(submission.id)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to post: {e}")
            return False
    
    def _check_recent_posts(self, subreddit: str) -> bool:
        """Check if we've posted here recently"""
        # Simple implementation - check log
        recent_cutoff = datetime.now().timestamp() - (7 * 24 * 3600)  # 7 days
        
        for engagement in self.engagement_log[-20:]:  # Check last 20 engagements
            if engagement.get("subreddit") == subreddit:
                if engagement.get("timestamp", 0) > recent_cutoff:
                    return True
        return False
    
    def schedule_comment_replies(self, submission_id: str):
        """Schedule replies to comments on our post"""
        # This would be implemented to check comments later and reply
        logger.info(f"Scheduled comment monitoring for post {submission_id}")
        
        # In a full implementation, this would:
        # 1. Check comments after 1 hour
        # 2. Reply to top comments with thoughtful responses
        # 3. Engage with questioners
        # 4. Share resources when appropriate
    
    def log_engagement(self, post_data: Dict, submission_id: str):
        """Log engagement activity"""
        engagement = {
            "subreddit": post_data["subreddit"],
            "title": post_data["title"],
            "submission_id": submission_id,
            "category": post_data["category"],
            "topic": post_data["topic"],
            "timestamp": datetime.now().timestamp(),
            "date": datetime.now().isoformat()
        }
        
        self.engagement_log.append(engagement)
        
        # Save to file
        log_path = Path("data/engagement_log.json")
        if log_path.exists():
            existing = json.loads(log_path.read_text())
        else:
            existing = []
        
        existing.append(engagement)
        log_path.write_text(json.dumps(existing, indent=2))
    
    def run_engagement_campaign(self, duration_days: int = 7, posts_per_day: int = 2):
        """Run an engagement campaign"""
        logger.info(f"Starting {duration_days}-day engagement campaign")
        
        total_posts = duration_days * posts_per_day
        
        for day in range(duration_days):
            logger.info(f"Day {day + 1} of {duration_days}")
            
            for post_num in range(posts_per_day):
                # Select subreddit
                subreddit = self.select_subreddit()
                
                # Generate content
                post_data = self.generate_post_content(subreddit)
                
                # Post to Reddit
                success = self.post_to_reddit(post_data)
                
                if success:
                    logger.info(f"Successfully posted ({post_num + 1}/{posts_per_day})")
                else:
                    logger.warning(f"Failed to post ({post_num + 1}/{posts_per_day})")
                
                # Wait between posts
                if post_num < posts_per_day - 1:
                    delay_hours = random.randint(3, 6)
                    logger.info(f"Waiting {delay_hours} hours before next post")
                    time.sleep(delay_hours * 3600)
            
            # Wait until next day
            if day < duration_days - 1:
                logger.info("Waiting until tomorrow...")
                time.sleep(24 * 3600)
        
        logger.info("Engagement campaign complete")
        
        # Generate report
        self.generate_campaign_report()
    
    def generate_campaign_report(self):
        """Generate campaign performance report"""
        report = {
            "campaign_summary": {
                "total_posts": len(self.engagement_log),
                "subreddits_targeted": list(set([e["subreddit"] for e in self.engagement_log])),
                "categories_used": list(set([e["category"] for e in self.engagement_log])),
                "start_date": min([e["date"] for e in self.engagement_log]) if self.engagement_log else None,
                "end_date": max([e["date"] for e in self.engagement_log]) if self.engagement_log else None
            },
            "engagement_metrics": {
                "posts_per_subreddit": {},
                "topics_coverage": {},
                "category_distribution": {}
            },
            "recommendations": self.generate_recommendations()
        }
        
        # Calculate metrics
        for engagement in self.engagement_log:
            sub = engagement["subreddit"]
            topic = engagement["topic"]
            cat = engagement["category"]
            
            report["engagement_metrics"]["posts_per_subreddit"][sub] = \
                report["engagement_metrics"]["posts_per_subreddit"].get(sub, 0) + 1
            
            report["engagement_metrics"]["topics_coverage"][topic] = \
                report["engagement_metrics"]["topics_coverage"].get(topic, 0) + 1
            
            report["engagement_metrics"]["category_distribution"][cat] = \
                report["engagement_metrics"]["category_distribution"].get(cat, 0) + 1
        
        # Save report
        report_path = Path("data/campaign_reports")
        report_path.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_path / f"campaign_report_{timestamp}.json"
        
        report_file.write_text(json.dumps(report, indent=2))
        logger.info(f"Campaign report saved to {report_file}")
        
        return report
    
    def generate_recommendations(self) -> List[str]:
        """Generate recommendations based on engagement"""
        recommendations = [
            "Continue focusing on r/microdosing and r/psychonaut as primary targets",
            "Increase resource-sharing posts in science-focused communities",
            "Develop more personal experience stories for human connection",
            "Create follow-up posts based on successful discussions",
            "Cross-reference discussions between related subreddits",
            "Build a FAQ from common questions in discussions",
            "Schedule AMAs (Ask Me Anything) with research-focused accounts",
            "Create visual content (infographics) for complex topics",
            "Partner with mods of target subreddits for community events",
            "Track which topics generate the most engagement for future focus"
        ]
        
        return random.sample(recommendations, 5)  # Return 5 random recommendations

if __name__ == "__main__":
    starter = ConversationStarter()
    
    # Test with one post
    test_subreddit = "microdosing"
    post_data = starter.generate_post_content(test_subreddit)
    
    print("="*60)
    print("TEST POST GENERATED")
    print("="*60)
    print(f"Title: {post_data['title']}")
    print(f"Subreddit: r/{post_data['subreddit']}")
    print(f"Category: {post_data['category']}")
    print(f"Topic: {post_data['topic']}")
    print("\nContent Preview:")
    print("-"*40)
    print(post_data['content'][:300] + "...")
    print("="*60)
    
    # Uncomment to actually post
    # starter.post_to_reddit(post_data)
    
    # Uncomment to run a campaign
    # starter.run_engagement_campaign(duration_days=3, posts_per_day=1)