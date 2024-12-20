import os
import requests
from typing import Dict, List
import time
from datetime import datetime, timedelta
import logging
import json
import hashlib
from pathlib import Path
import streamlit as st
try:
    import google.generativeai as genai
except ImportError:
    st.error("请安装 google-generativeai: pip install google-generativeai")
    raise

class TwitterCache:
    """Twitter 数据缓存系统"""
    
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_duration = timedelta(hours=1)  # 缓存1小时

    def _get_cache_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        hashed_key = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{hashed_key}.json"

    def get(self, key: str) -> Dict:
        """获取缓存数据"""
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            with cache_path.open('r') as f:
                cached_data = json.load(f)
                cache_time = datetime.fromisoformat(cached_data['timestamp'])
                if datetime.now() - cache_time < self.cache_duration:
                    return cached_data['data']
        return None

    def set(self, key: str, data: Dict):
        """设置缓存数据"""
        cache_path = self._get_cache_path(key)
        cache_data = {
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        with cache_path.open('w') as f:
            json.dump(cache_data, f)

class TwitterAPIv2:
    """Twitter API v2 访问实现"""
    
    def __init__(self):
        self.API_BASE = "https://api.twitter.com/2"
        
        # 尝试多种方式获取凭据
        self.CLIENT_ID = None
        self.CLIENT_SECRET = None
        
        # 1. 首先尝试从环境变量获取
        if os.getenv('TWITTER_CLIENT_ID') and os.getenv('TWITTER_CLIENT_SECRET'):
            self.CLIENT_ID = os.getenv('TWITTER_CLIENT_ID')
            self.CLIENT_SECRET = os.getenv('TWITTER_CLIENT_SECRET')
        
        # 2. 尝试从Streamlit secrets获取
        if not self.CLIENT_ID:
            try:
                self.CLIENT_ID = st.secrets.get("TWITTER_CLIENT_ID")
                self.CLIENT_SECRET = st.secrets.get("TWITTER_CLIENT_SECRET")
            except Exception:
                pass
        
        # 3. 如果以上都失败，使用默认值
        if not self.CLIENT_ID:
            self.CLIENT_ID = 'QTRWV3pQSVlBVEVJeXB6RXFmbDI6MTpjaQ'
            self.CLIENT_SECRET = 'sdyzT0lYa5ThsQfSbl5A9Rw1XUfD1lGkQ5ViJivHGdQh45dUv9'
        
        # 获取Bearer Token
        self.BEARER_TOKEN = self._get_bearer_token()
        
        # 初始化其他配置
        self.cache = TwitterCache()
        self.headers = {
            "Authorization": f"Bearer {self.BEARER_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "v2UserLookupPython"
        }
        self.rate_limit = {
            "remaining": 25,  # Free Plan每15分钟允许25次请求
            "reset_time": datetime.now() + timedelta(minutes=15),
            "requests_per_window": 25,
            "window_size": 15
        }
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def _get_bearer_token(self) -> str:
        """获取OAuth 2.0 Bearer Token"""
        # 使用新的Bearer Token
        return "AAAAAAAAAAAAAAAAAAAAANnAxAEAAAAAZPAUnhptfF8XZOqZ4ZSoPgm4PEc%3DQQO7FmG2IjsivpHOORNHIOx9Oyfl7kskEluZWK8OHqTr5Wa9VY"
        
        # 以下是OAuth 2.0的方式，暂时注释掉
        """
        if token := os.getenv('TWITTER_BEARER_TOKEN'):
            return token
            
        auth_url = "https://api.twitter.com/oauth2/token"
        auth_data = {
            'grant_type': 'client_credentials'
        }
        auth_headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        # 使用Basic认证
        response = requests.post(
            auth_url,
            auth=(self.CLIENT_ID, self.CLIENT_SECRET),
            data=auth_data,
            headers=auth_headers
        )
        
        if response.status_code == 200:
            return response.json()['access_token']
        else:
            raise ValueError(f"获取Bearer Token失: {response.text}")
        """

    def get_user_by_username(self, username: str) -> Dict:
        """获取用户信息"""
        try:
            # 先检查缓存
            cache_key = f"user_{username}"
            if cached_data := self.cache.get(cache_key):
                st.info("使用缓存的用户数据")
                return cached_data
            
            # 检查速率限制
            self._check_rate_limit()
            
            endpoint = f"{self.API_BASE}/users/by/username/{username}"
            params = {
                "user.fields": "id,name,username"  # 最小化请求字段
            }
            
            response = requests.get(
                endpoint,
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.cache.set(cache_key, data)
                return data
            elif response.status_code == 429:
                if cached_data := self.cache.get(cache_key):
                    st.warning("达到API限制，使用缓存数据")
                    return cached_data
                raise Exception("达到API速率限制")
            else:
                raise Exception(f"API请求失败: {response.status_code}")
                
        except Exception as e:
            if cached_data := self.cache.get(cache_key):
                st.warning(f"API请求失败({str(e)})，使用缓存数据")
                return cached_data
            raise

    def get_user_tweets(self, user_id: str) -> Dict:
        """获取用户最近7天的推文"""
        try:
            # 先检查缓存
            cache_key = f"tweets_{user_id}"
            if cached_data := self.cache.get(cache_key):
                st.info("使用缓存的推文数据")
                return cached_data
            
            # 检查速率限制
            self._check_rate_limit()
            
            endpoint = f"{self.API_BASE}/users/{user_id}/tweets"
            params = {
                "max_results": 5,  # Free Plan限制每次最多5条
                "tweet.fields": "created_at,text",  # 最小化请求字段
                "exclude": "retweets,replies",
                "start_time": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            }
            
            response = requests.get(
                endpoint,
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.cache.set(cache_key, data)
                return data
            elif response.status_code == 429:
                if cached_data := self.cache.get(cache_key):
                    st.warning("达到API限制，使用缓存数据")
                    return cached_data
                raise Exception("达到API速率限制")
            else:
                raise Exception(f"API请求失败: {response.status_code}")
                
        except Exception as e:
            st.warning(f"获取推文失败: {str(e)}")
            return {"data": []}

    def _check_rate_limit(self):
        """检查并处理速率限制"""
        current_time = datetime.now()
        
        # 如果超过时间窗口，重置限制
        if current_time >= self.rate_limit["reset_time"]:
            self.rate_limit["remaining"] = 15  # Free Plan实际限制
            self.rate_limit["reset_time"] = current_time + timedelta(minutes=15)
        
        # 如果剩余请求数不足，直接使用缓存
        if self.rate_limit["remaining"] <= 1:
            wait_time = (self.rate_limit["reset_time"] - current_time).total_seconds()
            if wait_time > 0:
                raise Exception("达到API速率限制")

    def _make_request(self, endpoint: str, params: Dict) -> Dict:
        """发送API请求"""
        try:
            # 检查缓存
            cache_key = hashlib.md5(f"{endpoint}_{str(params)}".encode()).hexdigest()
            if cached_data := self.cache.get(cache_key):
                st.info("使用缓存数据")
                return cached_data

            # 检查速率限制
            current_time = datetime.now()
            if current_time >= self.rate_limit["reset_time"]:
                self.rate_limit["remaining"] = self.rate_limit["requests_per_window"]
                self.rate_limit["reset_time"] = current_time + timedelta(minutes=self.rate_limit["window_size"])
            
            if self.rate_limit["remaining"] <= 0:
                wait_time = (self.rate_limit["reset_time"] - current_time).total_seconds()
                if wait_time > 0:
                    raise Exception(f"达到API速率限制，请等待{int(wait_time/60)}分{int(wait_time%60)}秒")

            # 发送请求
            response = requests.get(
                endpoint,
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            # 更新速率限制信息
            if 'x-rate-limit-remaining' in response.headers:
                self.rate_limit["remaining"] = int(response.headers['x-rate-limit-remaining'])
            if 'x-rate-limit-reset' in response.headers:
                self.rate_limit["reset_time"] = datetime.fromtimestamp(int(response.headers['x-rate-limit-reset']))
            
            # 处理响应
            if response.status_code == 200:
                data = response.json()
                self.cache.set(cache_key, data)
                return data
            elif response.status_code == 429:  # Rate limit exceeded
                reset_time = datetime.fromtimestamp(int(response.headers.get('x-rate-limit-reset', 0)))
                wait_time = (reset_time - current_time).total_seconds()
                raise Exception(f"达到API速率限制，请等待{int(wait_time/60)}分{int(wait_time%60)}秒")
            else:
                raise Exception(f"API请求失败: {response.status_code}")
                
        except Exception as e:
            st.error(f"API请求错误: {str(e)}")
            if cached_data := self.cache.get(cache_key):
                st.warning("使用缓存数据作为备选")
                return cached_data
            raise

class TweetAnalyzer:
    """使用Gemini进行推文分析"""
    
    def __init__(self):
        try:
            # 尝试多种方式获取Gemini API密钥
            api_key = None
            
            # 1. 首先尝试从Streamlit secrets获取
            try:
                api_key = st.secrets["GEMINI_API_KEY"]
            except Exception:
                st.warning("无法从Streamlit secrets获取Gemini API密钥")
            
            # 2. 尝试从环境变量获取
            if not api_key:
                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    st.success("从环境变量获取到Gemini API密钥")
            
            # 3. 使用硬编码的备用密钥
            if not api_key:
                api_key = "AIzaSyAE0zCw2RgQfeMAuLWSMUZnoPakTV2uaIY"
                st.warning("使用备用Gemini API密钥")
            
            # 配置Gemini
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-pro')
            st.success("Gemini配置成功")
            
        except Exception as e:
            st.error(f"Gemini配置失败: {str(e)}")
            self.model = None
    
    def analyze_tweets(self, tweets: List[Dict]) -> Dict:
        """分析推文"""
        if not tweets:
            return {
                "topics": [],
                "keywords": [],
                "analysis": "无推文数据可供分析",
                "gift_suggestions": ["通用礼品卡", "精美礼品盒", "手工巧克力"]
            }
        
        # 如果Gemini不可用，使用备用分析方法
        if not self.model:
            return self._fallback_analysis(tweets)
            
        # 准备推文文本
        tweet_texts = [tweet.get('text', '') for tweet in tweets]
        prompt = f"""
分析以下最近7天的推文内容：

{tweet_texts}

请提供：
1. 主要话题（最多3个）
2. 关键词（最多5个）
3. 内容分析（用户兴趣和偏好）
4. 基于分析的礼物建议（最多5个）

以JSON格式返回结果。
"""
        
        try:
            response = self.model.generate_content(prompt)
            result = json.loads(response.text)
            return result
        except Exception as e:
            st.warning(f"Gemini分析失败，使用备用分析方法: {str(e)}")
            return self._fallback_analysis(tweets)
            
    def _fallback_analysis(self, tweets: List[Dict]) -> Dict:
        """备用分析方法"""
        # 简单的文本分析
        topics = set()
        keywords = {}
        
        for tweet in tweets:
            text = tweet.get('text', '').lower()
            words = text.split()
            
            # 统计关键词
            for word in words:
                if len(word) > 3:  # 只统计长度大于3的词
                    keywords[word] = keywords.get(word, 0) + 1
        
        # 获取最常见的关键词
        top_keywords = sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            "topics": list(topics)[:3],
            "keywords": [word for word, _ in top_keywords],
            "analysis": "使用基础文本分析方法",
            "gift_suggestions": [
                "通用礼品卡",
                "精美礼品盒",
                "数码产品",
                "书籍",
                "手工艺品"
            ]
        }

def analyze_twitter_profile(username: str) -> str:
    """主分析函数"""
    api = None
    try:
        api = TwitterAPIv2()
        tweet_analyzer = TweetAnalyzer()
        
        # 验证用户名
        if not username or not username.strip():
            return "# ⚠️ 无效的用户名\n\n请输入有效的X用户名（不需要包含@符号）"
        
        username = username.strip().lstrip('@')
        
        try:
            # 获取用户信息
            st.info("正在获取用户信息...")
            user_data = api.get_user_by_username(username)
            
            if not user_data or 'data' not in user_data:
                return "# ❌ 无效的用户数据\n\n无法获取用户信息，请稍后重试"
                
            user_id = user_data['data']['id']
            
            # 获取最近7天的推文
            st.info("正在获取最近7天的推文...")
            tweets_data = {"data": []}
            
            if api.rate_limit["remaining"] > 1:
                try:
                    tweets_data = api.get_user_tweets(user_id)
                except Exception as e:
                    st.warning(f"获取推文失败: {str(e)}")
            
            # 用Gemini分析推文
            st.info("正在分析推文内容...")
            analysis_result = tweet_analyzer.analyze_tweets(tweets_data.get('data', []))
            
            return f"""
# X用户推文分析报告

## 推文分析
- 分析时间范围：最近7
- 分析推文数量：{len(tweets_data.get('data', []))}条

### 主要话题
{_format_topics(analysis_result.get('topics', []))}

### 高频关键词
{_format_keywords(analysis_result.get('keywords', []))}

## 分析结果
{analysis_result.get('analysis', '无法生成分析结果')}

## 礼物推荐
基于以上分析，为您推荐以下礼物：
{_format_recommendations(analysis_result.get('gift_suggestions', []))}
"""
            
        except Exception as e:
            st.error(f"错误详情: {str(e)}")
            if "用户不存在" in str(e):
                return "# ❌ 用户不存在\n\n该用户名不存在，请检查拼写是否正确"
            elif "认证失败" in str(e):
                return "# ❌ 认证失败\n\n请检查API Token是否有效"
            raise
            
    except Exception as e:
        st.error(f"发生错误: {str(e)}")
        return f"""
# ❌ 分析失败

错误信息: {str(e)}

请确保：
1. 输入的用户名正确
2. 该用户存在且未被限制访问
3. 网络连接正常

建议稍后重试。
"""

def _format_topics(topics: list) -> str:
    """格式化主题输出"""
    if not topics:
        return "暂无明显主题"
    return "\n".join([f"- {topic}" for topic in topics])

def _format_keywords(keywords: list) -> str:
    """格式化关键词输出"""
    if not keywords:
        return "暂无高频关键词"
    return "\n".join([f"- {keyword}" for keyword in keywords])

def _format_recommendations(recommendations: list) -> str:
    """格式化推荐礼物输出"""
    if not recommendations:
        return "- 通用礼品卡\n- 精美礼品盒"
    return "\n".join([f"- {gift}" for gift in recommendations])
        