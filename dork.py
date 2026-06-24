# enhanced_api.py - Enhanced FastAPI with CLI functionality and Self-Learning User Agents

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict
import requests
from bs4 import BeautifulSoup
import urllib3
import uvicorn
import json
import re
import os
import random
import asyncio
from datetime import datetime
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor

# Import the CLI's core detection logic
from wooc import (
    perform_website_scan,
    detect_woocommerce,
    scan_for_gateways,
    find_product_id,
    add_product_to_cart,
    ResilientSession,
    load_signatures
)

# ─── USER AGENT MODULE (Self-Learning) ──────────────────────────────

USER_AGENTS_FILE = 'user_agents.txt'
USAGE_LOG_FILE = 'user_agent_usage.json'

# Default user agents (the most common ones)
DEFAULT_USER_AGENTS = [
    # Chrome Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
    
    # Chrome Mac
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
    
    # Firefox Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
    
    # Firefox Mac
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; rv:109.0) Gecko/20100101 Firefox/120.0',
    
    # Safari
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    
    # Edge
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.76',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.60',
    
    # Mobile
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPad; CPU OS 17_1_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.163 Mobile Safari/537.36',
    
    # Bots
    'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'Mozilla/5.0 (compatible; Bingbot/2.0; +http://www.bing.com/bingbot.htm)',
    'Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)',
    'Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)',
    
    # Opera
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 OPR/105.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 OPR/105.0.0.0',
    
    # Linux
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/120.0',
    
    # Samsung Internet
    'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/119.0.6045.163 Mobile Safari/537.36',
    
    # UC Browser
    'Mozilla/5.0 (Linux; U; Android 13; en-US; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.163 UCBrowser/15.0.3.1309 Mobile Safari/537.36',
]

# Load user agents from file
def load_user_agents():
    """Load user agents from txt file or create default"""
    try:
        if os.path.exists(USER_AGENTS_FILE):
            with open(USER_AGENTS_FILE, 'r', encoding='utf-8') as f:
                agents = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                if agents:
                    return agents
    except Exception as e:
        print(f"Error loading user agents: {e}")
    
    # Create default file
    save_user_agents(DEFAULT_USER_AGENTS)
    return DEFAULT_USER_AGENTS

def save_user_agents(agents):
    """Save user agents to file"""
    try:
        with open(USER_AGENTS_FILE, 'w', encoding='utf-8') as f:
            f.write("# User Agents List - Auto-generated\n")
            f.write(f"# Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total: {len(agents)}\n\n")
            for agent in sorted(set(agents)):
                if agent.strip():
                    f.write(f"{agent.strip()}\n")
        return True
    except Exception as e:
        print(f"Error saving user agents: {e}")
        return False

def load_usage_stats():
    """Load usage statistics"""
    try:
        if os.path.exists(USAGE_LOG_FILE):
            with open(USAGE_LOG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {"usage_count": {}, "last_used": {}}

def save_usage_stats(stats):
    """Save usage statistics"""
    try:
        with open(USAGE_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)
        return True
    except:
        return False

def add_user_agent(agent, auto_save=True):
    """Add a new user agent to the list if not already present"""
    global USER_AGENTS
    if agent and agent not in USER_AGENTS:
        USER_AGENTS.append(agent)
        if auto_save:
            save_user_agents(USER_AGENTS)
        return True
    return False

def get_random_user_agent():
    """Get a random user agent, weighted by popularity"""
    global USER_AGENTS
    if not USER_AGENTS:
        USER_AGENTS = load_user_agents()
    
    # Try to use weighted selection based on usage
    try:
        stats = load_usage_stats()
        if stats['usage_count']:
            # Get top used agents
            sorted_agents = sorted(
                stats['usage_count'].items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            total_uses = sum(count for _, count in sorted_agents)
            if total_uses > 0:
                # 70% chance to use top agents, 30% random
                if random.random() < 0.7 and len(sorted_agents) > 5:
                    top_agents = [agent for agent, _ in sorted_agents[:10]]
                    return random.choice(top_agents)
    except:
        pass
    
    return random.choice(USER_AGENTS)

def get_user_agent_count():
    """Get total number of loaded user agents"""
    return len(USER_AGENTS)

def get_all_user_agents():
    """Get all loaded user agents"""
    return USER_AGENTS.copy()

def get_most_popular_agents(limit=10):
    """Get most popular user agents"""
    stats = load_usage_stats()
    sorted_agents = sorted(
        stats['usage_count'].items(),
        key=lambda x: x[1],
        reverse=True
    )
    return sorted_agents[:limit]

def extract_user_agent_from_request(request_headers):
    """Extract and log user agent from request headers"""
    ua = request_headers.get('user-agent', '')
    if ua:
        # Log usage
        stats = load_usage_stats()
        stats['usage_count'][ua] = stats['usage_count'].get(ua, 0) + 1
        stats['last_used'][ua] = datetime.now().isoformat()
        save_usage_stats(stats)
        
        # Add to list if new
        return add_user_agent(ua)
    return False

# Initialize user agents
USER_AGENTS = load_user_agents()

# ─── FASTAPI APP ─────────────────────────────────────────────────────

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(
    title="Enhanced Technology & Payment Gateway Profiler",
    description="Detects e-commerce platforms and payment gateways with cart simulation",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── MIDDLEWARE ──────────────────────────────────────────────────────

@app.middleware("http")
async def extract_user_agent_middleware(request: Request, call_next):
    """Extract user agent from incoming requests and add to collection"""
    extract_user_agent_from_request(request.headers)
    response = await call_next(request)
    return response

# ─── MODELS ──────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    urls: List[HttpUrl]
    timeout: Optional[int] = 15
    include_gateways: Optional[bool] = True
    simulate_cart: Optional[bool] = True

class GatewayInfo(BaseModel):
    slug: str
    name: str

class DetailedScanResult(BaseModel):
    url: str
    status_code: Optional[int] = None
    platform: str  # "WordPress", "WooCommerce", "Shopify", "Magento", "Unknown"
    is_woocommerce: bool
    confidence: str  # "High", "Medium", "Low"
    detected_gateways: List[GatewayInfo]
    cloudflare: str  # "YES" or "NO"
    captcha: str  # "YES" or "NO"
    country: str
    signatures_found: List[str]
    user_agent_used: str  # Track which UA was used
    error: Optional[str] = None

# ─── TECH DETECTOR ──────────────────────────────────────────────────

class TechDetector:
    def __init__(self, timeout: int = 15, simulate_cart: bool = True):
        self.timeout = timeout
        self.simulate_cart = simulate_cart
        # Get a random user agent for this instance
        self.user_agent = get_random_user_agent()
        self.headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }

    def detect(self, url: str) -> DetailedScanResult:
        """Enhanced detection using the CLI's advanced logic"""
        user_agent_used = self.user_agent
        
        try:
            # Use the CLI's comprehensive scan
            result = perform_website_scan(url, quiet=True)
            
            if result.get("status") == "error":
                return DetailedScanResult(
                    url=url,
                    status_code=None,
                    platform="Unknown",
                    is_woocommerce=False,
                    confidence="Low",
                    detected_gateways=[],
                    cloudflare="NO",
                    captcha="NO",
                    country="US",
                    signatures_found=[],
                    user_agent_used=user_agent_used,
                    error=result.get("error")
                )
            
            # Map results to our API format
            is_woo = result.get("platform") == "WooCommerce"
            gateways = [
                GatewayInfo(slug=gw["slug"], name=gw["name"])
                for gw in result.get("detected_gateways", [])
            ]
            
            return DetailedScanResult(
                url=result.get("url", url),
                status_code=200,
                platform=result.get("platform", "Unknown"),
                is_woocommerce=is_woo,
                confidence=result.get("confidence", "Low"),
                detected_gateways=gateways,
                cloudflare=result.get("cloudflare", "NO"),
                captcha=result.get("captcha", "NO"),
                country=result.get("country", "US"),
                signatures_found=result.get("reasons", []),
                user_agent_used=user_agent_used,
                error=None
            )
            
        except Exception as e:
            return DetailedScanResult(
                url=url,
                status_code=None,
                platform="Unknown",
                is_woocommerce=False,
                confidence="Low",
                detected_gateways=[],
                cloudflare="NO",
                captcha="NO",
                country="US",
                signatures_found=[],
                user_agent_used=user_agent_used,
                error=str(e)
            )

# ─── ENDPOINTS ──────────────────────────────────────────────────────

@app.get("/")
def index():
    return {
        "status": "healthy",
        "service": "Enhanced Technology & Payment Gateway Profiler",
        "version": "2.0.0",
        "capabilities": [
            "Platform detection (WordPress, WooCommerce, Shopify, Magento)",
            "Payment gateway detection with cart simulation",
            "Cloudflare detection",
            "Captcha detection",
            "Country detection",
            "Self-learning user agents"
        ],
        "supported_gateways": list(load_signatures().keys()),
        "user_agents_loaded": get_user_agent_count()
    }

@app.post("/kaido", response_model=List[DetailedScanResult])
def scan_urls(request: ScanRequest):
    """Scan multiple URLs for e-commerce platforms and payment gateways"""
    detector = TechDetector(
        timeout=request.timeout,
        simulate_cart=request.simulate_cart
    )
    
    # Parallel processing for multiple URLs
    if len(request.urls) > 1:
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(
                detector.detect, 
                [str(url) for url in request.urls]
            ))
    else:
        results = [detector.detect(str(request.urls[0]))]
    
    return results

@app.post("/rocks", response_model=DetailedScanResult)
def scan_single_url(request: ScanRequest):
    """Scan a single URL with detailed results"""
    if not request.urls:
        raise HTTPException(status_code=400, detail="At least one URL required")
    
    detector = TechDetector(
        timeout=request.timeout,
        simulate_cart=request.simulate_cart
    )
    return detector.detect(str(request.urls[0]))

@app.post("/kaido-live")
async def scan_urls_live(request: ScanRequest):
    """Scan multiple URLs with real-time progress updates (Server-Sent Events)"""
    
    async def generate():
        detector = TechDetector(
            timeout=request.timeout,
            simulate_cart=request.simulate_cart
        )
        total = len(request.urls)
        
        # Send initial status
        yield f"data: {json.dumps({'type': 'start', 'total': total, 'message': f'Starting scan of {total} URLs...'})}\n\n"
        
        for idx, url in enumerate(request.urls, 1):
            # Scan the URL
            result = detector.detect(str(url))
            
            # Send progress update with result
            yield f"data: {json.dumps({
                'type': 'progress',
                'current': idx,
                'total': total,
                'url': str(url),
                'platform': result.platform,
                'is_woocommerce': result.is_woocommerce,
                'confidence': result.confidence,
                'detected_gateways': [g.dict() for g in result.detected_gateways],
                'cloudflare': result.cloudflare,
                'captcha': result.captcha,
                'country': result.country,
                'signatures_found': result.signatures_found[:5],  # First 5 signatures
                'error': result.error
            })}\n\n"
            
            # Small delay to avoid flooding
            await asyncio.sleep(0.1)
        
        # Send completion message
        yield f"data: {json.dumps({'type': 'complete', 'message': 'All scans completed!'})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

@app.get("/gateways")
def list_gateways():
    """List all supported payment gateways"""
    signatures = load_signatures()
    return {
        "gateways": [
            {"slug": slug, "name": info.get("name", slug)}
            for slug, info in signatures.items()
        ],
        "count": len(signatures)
    }

@app.get("/user-agents")
def list_user_agents():
    """Show available user agents"""
    return {
        "total": get_user_agent_count(),
        "agents": get_all_user_agents()[:20],
        "random_example": get_random_user_agent()
    }

@app.get("/user-agents/stats")
def user_agent_stats():
    """Show user agent usage statistics"""
    return {
        "total": get_user_agent_count(),
        "most_popular": get_most_popular_agents(10),
        "usage_stats": load_usage_stats()
    }

@app.post("/user-agents/add")
def add_agent(agent_data: dict):
    """Add a user agent manually"""
    ua = agent_data.get('user_agent', '')
    if not ua:
        raise HTTPException(status_code=400, detail="user_agent field required")
    
    added = add_user_agent(ua)
    return {
        "status": "success" if added else "already_exists",
        "user_agent": ua,
        "total": get_user_agent_count()
    }

# ─── MAIN ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("="*60)
    print("🚀 Enhanced Technology & Payment Gateway Profiler")
    print("="*60)
    print(f"📱 User Agents Loaded: {get_user_agent_count()}")
    print(f"🎲 Random UA Example: {get_random_user_agent()}")
    print("="*60)
    uvicorn.run("dork:app", host="0.0.0.0", port=8000, reload=True)